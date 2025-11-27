from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.task_manager import task_manager, TaskStatus
from app.service.IO.archive_service import ArchiveService
from app.db.session import AsyncSessionLocal, get_db
from app.models.dataset import Dataset

router = APIRouter()

# 1. ЗАПУСК ЭКСПОРТА
@router.post("/export/{dataset_id}")
async def start_export(
    dataset_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # Предварительная проверка существования датасета
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Создаем задачу
    task = task_manager.create_task("dataset_export")
    
    # Запускаем фон (используем обертку с новой сессией)
    background_tasks.add_task(run_export_wrapper, task.task_id, dataset_id)
    
    return {"task_id": task.task_id, "status": "queued"}

# Обертка для запуска сервиса в фоне с новой сессией БД
async def run_export_wrapper(task_id: str, dataset_id: int):
    async with AsyncSessionLocal() as db:
        service = ArchiveService(db)
        await service.run_export_task(task_id, dataset_id)

# 2. ИМПОРТ
@router.post("/import")
async def import_dataset_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Импорт датасета из ZIP архива.
    """
    service = ArchiveService(db)
    # Метод import_dataset сам обрабатывает ошибки и делает rollback/raise HTTPException 500
    new_dataset = await service.import_dataset(file)
    
    return {
        "success": True, 
        "dataset_id": new_dataset.id,
        "message": f"Dataset '{new_dataset.title}' imported successfully"
    }

# 3. ПРОВЕРКА СТАТУСА
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

# 4. СКАЧИВАНИЕ
@router.get("/download/{task_id}")
async def download_export(task_id: str):
    task = task_manager.get_task(task_id)
    if not task or task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Export not ready or failed")
    
    file_path = task.result.get("file_path")
    filename = task.result.get("filename", "export.zip")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/zip"
    )