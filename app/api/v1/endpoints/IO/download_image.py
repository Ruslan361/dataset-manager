from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.image import Image
from app.db.session import get_db
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/download-image/{image_id}")
async def download_image(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        # Поиск изображения в БД
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
        
        # Проверка существования файла
        if not file_path.exists() or not file_path.is_file():
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