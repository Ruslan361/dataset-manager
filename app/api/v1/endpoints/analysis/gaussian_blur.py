from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.image import Image
from app.db.session import get_db
from app.service.image_processor import ImageProcessor
import cv2
import numpy as np
import logging
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

class GaussianBlurRequest(BaseModel):
    kernel_size: int = 3
    sigma_x: float = 0.0
    sigma_y: float = 0.0
    apply_viridis: bool = True  # Новый параметр для раскрашивания

@router.post("/gaussian-blur/{image_id}")
async def apply_gaussian_blur(
    image_id: int,
    blur_params: GaussianBlurRequest,
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
        
        # Загрузка изображения
        bgr_image = cv2.imread(str(file_path))
        if bgr_image is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to load image"
            )
        
        # Создание процессора изображений
        processor = ImageProcessor(bgr_image)
        
        # Применение размытия по Гауссу
        kernel = (blur_params.kernel_size, blur_params.kernel_size)
        blurred_l_channel = processor.blurGaussian(
            kernel=kernel,
            sigmaX=blur_params.sigma_x,
            sigmaY=blur_params.sigma_y
        )
        
        # Применение раскрашивания viridis, если требуется
        if blur_params.apply_viridis:
            # Нормализация L-канала к диапазону 0-255
            normalized = cv2.normalize(blurred_l_channel, None, 0, 255, cv2.NORM_MINMAX)
            normalized = normalized.astype(np.uint8)
            
            # Применение colormap viridis
            viridis_colored = cv2.applyColorMap(normalized, cv2.COLORMAP_VIRIDIS)
            
            # Кодирование цветного изображения
            success, encoded_image = cv2.imencode('.png', viridis_colored)
            media_type = "image/png"
            log_message = f"Applied Gaussian blur with viridis colormap to image {image_id}"
        else:
            # Кодирование обычного L-канала (grayscale)
            success, encoded_image = cv2.imencode('.png', blurred_l_channel)
            media_type = "image/png"
            log_message = f"Applied Gaussian blur to image {image_id}"
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to encode processed image"
            )
        
        logger.info(log_message)
        
        # Возвращаем обработанное изображение
        return Response(
            content=encoded_image.tobytes(),
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing image")