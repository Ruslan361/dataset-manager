from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import logging
from app.core.task_manager import task_manager, TaskStatus
from app.service.IO.archive_service import ArchiveService
from app.db.session import AsyncSessionLocal, get_db
from app.models.dataset import Dataset

logger = logging.getLogger(__name__)
router = APIRouter()

def _delete_file(path: str):
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
            logger.info(f"Deleted export file after download: {p}")
    except Exception as e:
        logger.warning(f"Could not delete export file {path}: {e}")

@router.post("/export/{dataset_id}")
async def start_export(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    task = task_manager.create_task("dataset_export")
    
    background_tasks.add_task(run_export_wrapper, task.task_id, dataset_id)
    
    return {"task_id": task.task_id, "status": "queued"}

async def run_export_wrapper(task_id: str, dataset_id: int):
    async with AsyncSessionLocal() as db:
        service = ArchiveService(db)
        await service.run_export_task(task_id, dataset_id)

@router.post("/import")
async def import_dataset_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Импорт датасета из ZIP архива.
    """
    service = ArchiveService(db)
    new_dataset = await service.import_dataset(file)
    
    return {
        "success": True, 
        "dataset_id": new_dataset.id,
        "message": f"Dataset '{new_dataset.title}' imported successfully"
    }

@router.get("/status/{task_id}")
async def get_export_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "message": task.message,
        "error": task.error
    }

@router.get("/download/{task_id}")
async def download_export(task_id: str, background_tasks: BackgroundTasks):
    task = task_manager.get_task(task_id)
    if not task or task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Export not ready or failed")

    file_path = task.result.get("file_path")
    filename = task.result.get("filename", "export.zip")

    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Export file not found or already downloaded")

    background_tasks.add_task(_delete_file, file_path)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/zip"
    )