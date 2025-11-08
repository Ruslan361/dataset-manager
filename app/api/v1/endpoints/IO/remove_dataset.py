from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.result import ResultResponse 
from app.service.IO.dataset_service import DatasetService
from app.service.IO.image_service import ImageService
from app.service.IO.file_services import FileService
from app.db.session import get_db
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

@router.delete("/remove-dataset/{dataset_id}", response_model=ResultResponse)
async def remove_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаление датасета со всеми изображениями и файлами"""
    dataset_service = DatasetService(db)
    image_service = ImageService(db)
    
    try:
        # Проверка существования датасета
        dataset = await dataset_service.get_dataset_by_id(dataset_id)
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset with id {dataset_id} not found"
            )
        
        # Удаление всех изображений из БД и подсчет количества
        images_count = await image_service.delete_images_by_dataset(dataset_id)
        
        # Удаление датасета из БД
        deleted_dataset = await dataset_service.delete_dataset(dataset_id)
        
        # Удаление папки с файлами
        dataset_folder = Path(f"uploads/images/{dataset_id}")
        folder_deleted = FileService.remove_directory(dataset_folder)
        
        success_message = f"Dataset '{deleted_dataset.title}' (ID: {dataset_id}) and {images_count} images deleted successfully"
        if not folder_deleted:
            success_message += " (folder was not found or already deleted)"
        
        logger.info(success_message)
        
        return ResultResponse(
            success=True,
            message=success_message
        )
        
    except HTTPException:
        # HTTPException уже обработаны в сервисах
        raise
    except Exception as e:
        logger.error(f"Unexpected error in remove_dataset endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")