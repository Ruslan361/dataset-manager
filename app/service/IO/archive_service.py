import shutil
import json
import zipfile
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import uuid
import logging
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import UploadFile, HTTPException
import aiofiles
from app.models.dataset import Dataset
from app.models.image import Image
from app.models.result import Results
from app.service.IO.base_service import BaseService
from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.schemas.archive import DatasetExportManifest, ImageExportItem, ResultExportItem
from app.core.executor import get_executor
from app.core.task_manager import task_manager, TaskStatus

logger = logging.getLogger(__name__)

class ArchiveService(BaseService):
    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.image_service = ImageService(db)
        self.result_service = ResultService(db)

    def _create_zip_sync(
        self, 
        temp_dir: Path, 
        dataset: Dataset, 
        images: List[Image], 
        results_map: Dict[int, List[Results]]
    ) -> str:
        """
        Синхронная функция создания архива. 
        Запускается в ThreadPoolExecutor.
        """
        try:
            images_dir = temp_dir / "images"
            results_dir = temp_dir / "results"
            images_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)

            manifest_images = []

            for img in images:
                # 1. Копируем изображение
                src_img_path = self.image_service.get_image_file_path(img)
                if src_img_path.exists():
                    shutil.copy2(src_img_path, images_dir / img.filename)
                
                # 2. Обрабатываем результаты
                img_results = results_map.get(img.id, [])
                export_results = []
                
                for res in img_results:
                    # Копируем JSON, чтобы не менять объект SQLAlchemy
                    res_json = json.loads(json.dumps(res.result)) if res.result else {}
                    resources = res_json.get("resources", [])
                    new_resources = []
                    
                    for r in resources:
                        if r.get("type") == "image" and "path" in r:
                            orig_path = Path(r["path"])
                            if orig_path.exists():
                                # Уникальное имя файла для архива
                                archive_res_name = f"{img.id}_{uuid.uuid4().hex[:8]}_{orig_path.name}"
                                shutil.copy2(orig_path, results_dir / archive_res_name)
                                
                                # Обновляем путь на относительный
                                r_copy = r.copy()
                                r_copy["path"] = f"results/{archive_res_name}"
                                new_resources.append(r_copy)
                        else:
                            new_resources.append(r)
                    
                    res_json["resources"] = new_resources
                    
                    export_results.append(ResultExportItem(
                        name_method=res.name_method,
                        result_data=res_json,
                        created_at=res.created_at.isoformat() if res.created_at else ""
                    ))

                manifest_images.append(ImageExportItem(
                    original_filename=img.original_filename,
                    filename=img.filename,
                    results=export_results
                ))

            # 3. Создаем манифест
            manifest = DatasetExportManifest(
                title=dataset.title,
                description=dataset.description,
                created_at=dataset.created_at.isoformat() if dataset.created_at else datetime.now().isoformat(),
                images=manifest_images
            )

            with open(temp_dir / "manifest.json", "w", encoding='utf-8') as f:
                f.write(manifest.model_dump_json(indent=2))

            # 4. Упаковываем в ZIP
            export_dir = Path("exports")
            export_dir.mkdir(exist_ok=True)
            
            # Имя итогового файла
            safe_title = "".join([c for c in dataset.title if c.isalnum() or c in (' ', '-', '_')]).strip()
            zip_filename = f"dataset_{dataset.id}_{safe_title}"
            zip_path = export_dir / zip_filename 
            
            # make_archive добавляет .zip автоматически
            shutil.make_archive(str(zip_path), 'zip', temp_dir)
            
            return str(zip_path.with_suffix('.zip'))

        except Exception as e:
            logger.error(f"Sync zip creation failed: {e}")
            raise e

    async def run_export_task(self, task_id: str, dataset_id: int):
        """
        Фоновая задача для сбора данных и запуска архивации.
        """
        try:
            task_manager.update_task(task_id, TaskStatus.PROCESSING, "Collecting data from DB...")
            
            # 1. Сбор данных (IO/DB bound)
            dataset = await self.db.get(Dataset, dataset_id)
            if not dataset:
                raise Exception("Dataset not found")
            
            images = await self.image_service.get_images_by_dataset(dataset_id)
            
            # ОПТИМИЗАЦИЯ: Загружаем все результаты одним запросом
            image_ids = [img.id for img in images]
            results_map = defaultdict(list)
            
            if image_ids:
                stmt = select(Results).where(Results.image_id.in_(image_ids))
                all_results = (await self.db.execute(stmt)).scalars().all()
                for res in all_results:
                    results_map[res.image_id].append(res)

            task_manager.update_task(task_id, TaskStatus.PROCESSING, f"Compressing {len(images)} images...")

            # 2. Создание архива (CPU/Disk IO bound -> в executor)
            temp_dir = Path(f"temp_export_{task_id}")
            
            try:
                loop = asyncio.get_running_loop()
                zip_path = await loop.run_in_executor(
                    get_executor(),
                    self._create_zip_sync,
                    temp_dir,
                    dataset,
                    images,
                    results_map
                )

                task_manager.update_task(
                    task_id, 
                    TaskStatus.COMPLETED, 
                    message="Export ready", 
                    result={"file_path": zip_path, "filename": Path(zip_path).name}
                )
            finally:
                # Очистка временной папки
                if temp_dir.exists():
                    await loop.run_in_executor(get_executor(), shutil.rmtree, temp_dir)

        except Exception as e:
            logger.error(f"Export task failed: {e}")
            task_manager.update_task(task_id, TaskStatus.FAILED, error=str(e))

    async def import_dataset(self, file: UploadFile) -> Dataset:
        """
        Импорт датасета из ZIP.
        """
        temp_dir = Path(f"temp_import_{uuid.uuid4()}")
        temp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = temp_dir / "upload.zip"

        try:
            async with aiofiles.open(zip_path, "wb") as f:
                while content := await file.read(1024 * 1024): 
                    await f.write(content)

            # 2. Распаковка (CPU/Disk IO bound -> executor)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                get_executor(), 
                shutil.unpack_archive, 
                str(zip_path), 
                str(temp_dir), 
                'zip'
            )

            # 3. Чтение манифеста
            manifest_path = temp_dir / "manifest.json"
            if not manifest_path.exists():
                raise HTTPException(status_code=400, detail="Invalid archive: manifest.json missing")

            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                manifest = DatasetExportManifest(**data)

            # 4. Создание структуры в БД
            new_dataset = Dataset(
                title=f"{manifest.title} (Imported {datetime.now().strftime('%d.%m %H:%M')})",
                description=manifest.description
            )
            self.db.add(new_dataset)
            await self.db.commit()
            await self.db.refresh(new_dataset)

            # Папки для файлов
            new_images_dir = Path(f"uploads/images/{new_dataset.id}")
            new_results_dir = Path(f"uploads/results/{new_dataset.id}")
            new_images_dir.mkdir(parents=True, exist_ok=True)
            new_results_dir.mkdir(parents=True, exist_ok=True)

            # 5. Импорт данных
            for img_item in manifest.images:
                # Новое имя файла
                ext = Path(img_item.filename).suffix
                new_filename = f"{uuid.uuid4()}{ext}"
                
                # Копирование (File IO)
                src_img = temp_dir / "images" / img_item.filename
                if src_img.exists():
                    shutil.copy2(src_img, new_images_dir / new_filename)
                
                # Запись в БД
                new_image = Image(
                    filename=new_filename,
                    original_filename=img_item.original_filename,
                    dataset_id=new_dataset.id
                )
                self.db.add(new_image)
                await self.db.commit()
                await self.db.refresh(new_image)

                # Результаты
                for res_item in img_item.results:
                    res_data = res_item.result_data
                    resources = res_data.get("resources", [])
                    new_resources = []
                    
                    for r in resources:
                        if r.get("type") == "image" and "path" in r:
                            # Относительный путь из манифеста -> Абсолютный временный путь
                            rel_path = r["path"] # "results/filename.jpg"
                            src_res_file = temp_dir / rel_path
                            
                            if src_res_file.exists():
                                new_res_filename = f"{new_image.id}_{src_res_file.name}"
                                dest_path = new_results_dir / new_res_filename
                                shutil.copy2(src_res_file, dest_path)
                                
                                # Обновляем путь на новый абсолютный
                                r_copy = r.copy()
                                r_copy["path"] = str(dest_path)
                                new_resources.append(r_copy)
                        else:
                            new_resources.append(r)
                    
                    res_data["resources"] = new_resources
                    
                    new_result = Results(
                        image_id=new_image.id,
                        name_method=res_item.name_method,
                        result=res_data
                    )
                    self.db.add(new_result)
            
            await self.db.commit()
            return new_dataset

        except Exception as e:
            await self.rollback_db()
            logger.error(f"Import failed: {e}")
            # ИСПРАВЛЕНО: сообщение об ошибке теперь начинается с "Import failed"
            raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
        finally:
            if temp_dir.exists():
                try:
                    await loop.run_in_executor(get_executor(), shutil.rmtree, temp_dir)
                except Exception:
                    pass