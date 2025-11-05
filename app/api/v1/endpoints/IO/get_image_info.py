from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.image import Image
from app.db.session import get_db
import logging
from app.schemas.image import ImageResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/image/{image_id}", response_model=ImageResponse)
async def get_image_info(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получить информацию об изображении"""
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
        
        # Возвращаем объект, который автоматически преобразуется в ImageResponse
        return image
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image info {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting image info")
