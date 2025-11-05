from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.image import Image
from app.models.result import Results
from app.db.session import get_db
from app.service.image_processor import ImageProcessor
from app.schemas.result import ResultResponse
import cv2
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List

logger = logging.getLogger(__name__)
router = APIRouter()

class MeanLinesRequest(BaseModel):
    vertical_lines: List[int]
    horizontal_lines: List[int]

class MeanLinesResponse(BaseModel):
    success: bool
    message: str
    means: List[List[float]]
    image_id: int
    result_id: int

@router.post("/calculate-mean-lines/{image_id}", response_model=MeanLinesResponse)
async def calculate_mean_relative_to_lines(
    image_id: int,
    lines_params: MeanLinesRequest,
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
        
        # Валидация линий
        if len(lines_params.vertical_lines) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 vertical lines are required"
            )
        
        if len(lines_params.horizontal_lines) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 horizontal lines are required"
            )
        
        # Проверка что линии отсортированы
        if lines_params.vertical_lines != sorted(lines_params.vertical_lines):
            raise HTTPException(
                status_code=400,
                detail="Vertical lines must be sorted in ascending order"
            )
        
        if lines_params.horizontal_lines != sorted(lines_params.horizontal_lines):
            raise HTTPException(
                status_code=400,
                detail="Horizontal lines must be sorted in ascending order"
            )
        
        # Загрузка изображения
        bgr_image = cv2.imread(str(file_path))
        if bgr_image is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to load image"
            )
        
        # Проверка границ линий относительно размеров изображения
        height, width = bgr_image.shape[:2]
        
        if any(x < 0 or x >= width for x in lines_params.vertical_lines):
            raise HTTPException(
                status_code=400,
                detail=f"Vertical lines must be within image width (0-{width-1})"
            )
        
        if any(y < 0 or y >= height for y in lines_params.horizontal_lines):
            raise HTTPException(
                status_code=400,
                detail=f"Horizontal lines must be within image height (0-{height-1})"
            )
        
        # Создание процессора изображений
        processor = ImageProcessor(bgr_image)
        
        # Вычисление средних значений яркости для областей
        means_array = processor.calculateMeanRelativeToLines(
            vertical_lines=lines_params.vertical_lines,
            horizontal_lines=lines_params.horizontal_lines
        )
        
        # Конвертация numpy array в список для JSON ответа
        means_list = means_array.tolist()
        
        # Подготовка данных для сохранения в БД
        result_data = {
            "means": means_list,
            "vertical_lines": lines_params.vertical_lines,
            "horizontal_lines": lines_params.horizontal_lines,
            "grid_size": f"{len(lines_params.vertical_lines)-1}x{len(lines_params.horizontal_lines)-1}",
            "regions_count": len(means_list) * (len(means_list[0]) if means_list else 0)
        }
        
        # Сохранение результата в БД
        db_result = Results(
            name_method="calculate_mean_lines",
            result=result_data,
            image_id=image_id
        )
        db.add(db_result)
        await db.commit()
        await db.refresh(db_result)
        
        logger.info(f"Calculated and saved mean luminance for image {image_id} with {len(lines_params.vertical_lines)-1}x{len(lines_params.horizontal_lines)-1} grid, result_id: {db_result.id}")
        
        return MeanLinesResponse(
            success=True,
            message=f"Successfully calculated mean luminance for {len(means_list)}x{len(means_list[0]) if means_list else 0} regions",
            means=means_list,
            image_id=image_id,
            result_id=db_result.id
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error calculating mean lines for image {image_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Error calculating mean relative to lines")