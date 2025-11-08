from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.IO.image_service import ImageService
from app.db.session import get_db
from app.schemas.image import ImageResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/image/{image_id}", response_model=ImageResponse)
async def get_image_info(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получить информацию об изображении"""
    image_service = ImageService(db)
    
    try:
        # Получение изображения через сервис
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise HTTPException(
                status_code=404,
                detail=f"Image with id {image_id} not found"
            )
        
        # Возвращаем объект, который автоматически преобразуется в ImageResponse
        return image
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image info {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting image info")
