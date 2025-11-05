from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas.result import ResultResponse 
from app.models.image import Image
from app.db.session import get_db
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

@router.delete("/remove-image/{image_id}", response_model=ResultResponse)
async def remove_image(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    file_path = None
    
    try:
        # Поиск изображения
        image_query = select(Image).where(Image.id == image_id)
        result = await db.execute(image_query)
        image = result.scalar_one_or_none()
        
        if not image:
            raise HTTPException(
                status_code=404,
                detail=f"Image with id {image_id} not found"
            )
        
        # Путь к файлу изображения
        file_path = Path(f"uploads/images/{image.dataset_id}/{image.filename}")
        
        # Удаление записи из БД
        await db.delete(image)
        await db.commit()
        
        # Удаление физического файла
        if file_path.exists() and file_path.is_file():
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        else:
            logger.warning(f"File not found: {file_path}")
        
        logger.info(f"Image {image_id} deleted successfully")
        
        return ResultResponse(
            success=True,
            message=f"Image {image_id} deleted successfully"
        )
        
    except HTTPException:
        await rollback_operations(db, file_path, rollback_file=False)
        raise
    except Exception as e:
        logger.error(f"Error deleting image {image_id}: {str(e)}")
        await rollback_operations(db, file_path, rollback_file=True)
        raise HTTPException(status_code=500, detail="Deletion failed")

async def rollback_operations(db: AsyncSession, file_path: Path = None, rollback_file: bool = False):
    """Откат операций при ошибке"""
    try:
        # Откат транзакции БД
        await db.rollback()
        logger.info("Database transaction rolled back")
        
        # Восстановление файла не делаем, так как это технически сложно
        # В случае ошибки после удаления файла - он уже удален
        if rollback_file and file_path:
            logger.warning(f"Cannot restore deleted file: {file_path}")
            
    except Exception as rollback_error:
        logger.error(f"Error during rollback: {str(rollback_error)}")