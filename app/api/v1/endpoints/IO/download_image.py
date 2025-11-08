from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.IO.image_service import ImageService
from app.db.session import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/download-image/{image_id}")
async def download_image(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Скачивание изображения по ID"""
    image_service = ImageService(db)
    
    try:
        # Получение изображения из БД
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise HTTPException(
                status_code=404,
                detail=f"Image with id {image_id} not found"
            )
        
        # Получение пути к файлу и проверка существования
        file_path = image_service.get_image_file_path(image)
        if not image_service.validate_file_exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise HTTPException(
                status_code=404,
                detail="Image file not found on server"
            )
        
        logger.info(f"Serving image {image_id}: {file_path}")
        
        # Возвращаем файл с оригинальным именем
        return FileResponse(
            path=str(file_path),
            filename=image.original_filename,
            media_type="image/*"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error downloading image")