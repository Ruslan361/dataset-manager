from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.schemas.result import ResultResponse 
from app.models.dataset import Dataset
from app.models.image import Image
from app.db.session import get_db
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

@router.delete("/remove-dataset/{dataset_id}", response_model=ResultResponse)
async def remove_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db)
):
    dataset_folder = None
    
    try:
        # Поиск датасета
        dataset_query = select(Dataset).where(Dataset.id == dataset_id)
        result = await db.execute(dataset_query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset with id {dataset_id} not found"
            )
        
        # Путь к папке датасета
        dataset_folder = Path(f"uploads/images/{dataset_id}")
        
        # Подсчет количества изображений
        images_count_query = select(Image).where(Image.dataset_id == dataset_id)
        images_result = await db.execute(images_count_query)
        images_count = len(images_result.scalars().all())
        
        # Удаление записей изображений из БД
        await db.execute(delete(Image).where(Image.dataset_id == dataset_id))
        
        # Удаление датасета из БД
        await db.delete(dataset)
        await db.commit()
        
        # Удаление папки с файлами
        if dataset_folder.exists() and dataset_folder.is_dir():
            shutil.rmtree(dataset_folder)  # Удаляет папку со всем содержимым
            logger.info(f"Deleted folder: {dataset_folder}")
        
        logger.info(f"Dataset {dataset_id} with {images_count} images deleted successfully")
        
        return ResultResponse(
            success=True,
            message=f"Dataset {dataset_id} and folder with {images_count} images deleted successfully"
        )
        
    except HTTPException:
        await rollback_operations(db, dataset_folder, rollback_folder=False)
        raise
    except Exception as e:
        logger.error(f"Error deleting dataset {dataset_id}: {str(e)}")
        await rollback_operations(db, dataset_folder, rollback_folder=True)
        raise HTTPException(status_code=500, detail="Deletion failed")

async def rollback_operations(db: AsyncSession, dataset_folder: Path = None, rollback_folder: bool = False):
    """Откат операций при ошибке"""
    try:
        # Откат транзакции БД
        await db.rollback()
        logger.info("Database transaction rolled back")
        
        # Восстановление папки не делаем, так как это сложно
        # В случае ошибки после удаления папки - она уже удалена
        if rollback_folder and dataset_folder:
            logger.warning(f"Cannot restore deleted folder: {dataset_folder}")
            
    except Exception as rollback_error:
        logger.error(f"Error during rollback: {str(rollback_error)}")