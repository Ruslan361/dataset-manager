from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from app.db.session import get_db
from app.service.IO.image_service import ImageService
from app.service.computation.filter_service import FilterService
from app.core.exceptions import ResourceNotFoundError, CalculationError

logger = logging.getLogger(__name__)
router = APIRouter()
from app.core.executor import get_executor # <--- Импорт
# Отдельный экзекьютор для CPU-задач (можно вынести в app.core)
executor = get_executor()

class GaussianBlurRequest(BaseModel):
    kernel_size: int = 3
    sigma_x: float = 0.0
    sigma_y: float = 0.0
    apply_viridis: bool = True

@router.post("/gaussian-blur/{image_id}")
async def apply_gaussian_blur(
    image_id: int,
    blur_params: GaussianBlurRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        # 1. Загрузка (быстро, в основном IO)
        image_service = ImageService(db)
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise ResourceNotFoundError(f"Image {image_id} not found")
            
        file_path = image_service.get_image_file_path(image)
        bgr_image = image_service.load_image_cv2(file_path)
        
        # 2. Вычисления в отдельном потоке (чтобы не блокировать async loop)
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(
            executor,
            FilterService.apply_gaussian_blur,
            bgr_image,
            blur_params.kernel_size,
            blur_params.sigma_x,
            blur_params.sigma_y,
            blur_params.apply_viridis
        )
        
        logger.info(f"Applied Gaussian blur to image {image_id}")
        
        return Response(content=image_bytes, media_type="image/png")
        
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CalculationError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing image {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")