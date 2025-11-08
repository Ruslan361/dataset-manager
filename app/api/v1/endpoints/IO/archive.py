from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
import shutil
import tempfile
from pathlib import Path

from app.db.session import get_db
from app.service.IO.archive_service import ArchiveService
from app.schemas.result import ResultResponse

router = APIRouter()

@router.get("/datasets/{dataset_id}/export", response_class=FileResponse)
async def export_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Export a dataset as a zip archive.
    """
    archive_service = ArchiveService(db)
    try:
        zip_path = await archive_service.export_dataset_to_zip(dataset_id)
        return FileResponse(
            path=zip_path,
            filename=zip_path.name,
            media_type='application/zip'
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting dataset: {str(e)}")

@router.post("/datasets/import", response_model=ResultResponse)
async def import_dataset(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Import a dataset from a zip archive.
    """
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .zip is supported.")

    archive_service = ArchiveService(db)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        new_dataset = await archive_service.import_dataset_from_zip(tmp_path)
        return ResultResponse(
            success=True,
            message="Dataset imported successfully",
            data={"dataset_id": new_dataset.id}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing dataset: {str(e)}")
    finally:
        tmp_path.unlink() # Clean up the temporary file
