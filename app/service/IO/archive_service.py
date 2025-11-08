import zipfile
import json
from pathlib import Path
import tempfile
import shutil
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.service.IO.dataset_service import DatasetService
from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.models.dataset import Dataset
from app.schemas.dataset import DatasetCreate
from app.service.IO.file_services import FileService


class ArchiveService:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.dataset_service = DatasetService(db_session)
        self.image_service = ImageService(db_session)
        self.result_service = ResultService(db_session)

    async def export_dataset_to_zip(self, dataset_id: int) -> Path:
        """
        Exports a dataset to a zip archive.
        The archive will contain images, results, and a manifest.json file.
        """
        dataset = await self.dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise ValueError("Dataset not found")

        images = await self.image_service.get_images_by_dataset(dataset_id)
        
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            images_dir = temp_dir / "images"
            results_dir = temp_dir / "results"
            images_dir.mkdir()
            results_dir.mkdir()

            manifest: Dict[str, Any] = {
                "dataset": {
                    "name": dataset.name,
                    "description": dataset.description,
                },
                "images": [],
            }

            for image in images:
                # Copy image file
                image_path = FileService.get_image_path(dataset.id, image.filename)
                if image_path.exists():
                    shutil.copy(image_path, images_dir / image.filename)

                image_manifest = {
                    "filename": image.filename,
                    "original_filename": image.original_filename,
                    "results": []
                }

                results = await self.result_service.get_results_by_image(image.id)
                for result in results:
                    result_path = FileService.get_result_path(dataset.id, result.filename)
                    if result_path.exists():
                        shutil.copy(result_path, results_dir / result.filename)
                        
                    image_manifest["results"].append({
                        "filename": result.filename,
                        "description": result.description,
                        "parameters": result.parameters,
                    })
                
                manifest["images"].append(image_manifest)

            # Write manifest
            with open(temp_dir / "manifest.json", "w") as f:
                json.dump(manifest, f, indent=4)

            # Create zip archive
            zip_path = Path(tempfile.gettempdir()) / f"dataset_{dataset_id}_{dataset.name}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_dir.rglob('*'):
                    zipf.write(file_path, file_path.relative_to(temp_dir))
            
            return zip_path

    async def import_dataset_from_zip(self, zip_path: Path) -> Dataset:
        """
        Imports a dataset from a zip archive.
        """
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)

            manifest_path = temp_dir / "manifest.json"
            if not manifest_path.exists():
                raise ValueError("manifest.json not found in the archive")

            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            # Create dataset
            dataset_schema = DatasetCreate(**manifest["dataset"])
            new_dataset = await self.dataset_service.create_dataset(dataset_schema)
            
            images_dir = temp_dir / "images"
            results_dir = temp_dir / "results"

            for image_manifest in manifest["images"]:
                # Create image
                original_image_path = images_dir / image_manifest["filename"]
                
                unique_filename = FileService.generate_unique_filename(image_manifest["original_filename"])
                
                upload_dir = FileService.create_upload_directory(new_dataset.id)
                new_image_path = upload_dir / unique_filename
                
                shutil.copy(original_image_path, new_image_path)

                new_image = await self.image_service.create_image(
                    filename=unique_filename,
                    original_filename=image_manifest["original_filename"],
                    dataset_id=new_dataset.id
                )

                for result_manifest in image_manifest.get("results", []):
                    original_result_path = results_dir / result_manifest["filename"]
                    
                    result_upload_dir = FileService.create_result_directory(new_dataset.id)
                    new_result_path = result_upload_dir / result_manifest["filename"]
                    
                    shutil.copy(original_result_path, new_result_path)

                    await self.result_service.create_result(
                        image_id=new_image.id,
                        filename=result_manifest["filename"],
                        description=result_manifest.get("description"),
                        parameters=result_manifest.get("parameters")
                    )
            
            return new_dataset
