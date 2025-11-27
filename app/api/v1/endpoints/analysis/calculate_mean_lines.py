from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
import logging
from pydantic import BaseModel

from app.db.session import get_db
from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.service.computation.brightness_service import BrightnessService
from app.core.exceptions import (
    ResourceNotFoundError, InvalidGridError, EmptySelectionError, 
    DataMismatchError, CalculationError
)

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic Schemas ---
# (Если у вас есть отдельный файл app/schemas/analysis.py, лучше перенести их туда)

class MeanLinesRequest(BaseModel):
    vertical_lines: List[float]
    horizontal_lines: List[float]

class MeanLinesResponse(BaseModel):
    success: bool
    message: str
    means: List[List[float]]
    image_id: int
    result_id: int
    vertical_lines: List[int]
    horizontal_lines: List[int]

class SelectedCell(BaseModel):
    row: int
    col: int
    categoryId: str

class SelectionCategory(BaseModel):
    id: str
    name: str
    color: str

class CategorizedMeanRequest(BaseModel):
    verticalLines: List[float]
    horizontalLines: List[float]
    selectedCells: List[SelectedCell]
    selectionCategories: List[SelectionCategory]
    imageID: int

class CategoryMeanResult(BaseModel):
    categoryId: str
    categoryName: str
    color: str
    meanValue: float
    cellCount: int
    cells: List[Dict[str, int]]
    rowMeans: List[Optional[float]]
    rowMeansAverage: Optional[float]

class CategorizedMeanResponse(BaseModel):
    success: bool
    message: str
    imageId: int
    resultId: int
    allCellsMean: float
    categoryResults: List[CategoryMeanResult]
    overallMean: float
    verticalLines: List[int]
    horizontalLines: List[int]
    totalCells: int
    selectedCellsCount: int

# --- Endpoints ---

@router.post("/calculate-mean-lines/{image_id}", response_model=MeanLinesResponse)
async def calculate_mean_relative_to_lines(
    image_id: int,
    lines_params: MeanLinesRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        # 1. Загрузка изображения
        image_service = ImageService(db)
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise ResourceNotFoundError(f"Image {image_id} not found")
        
        file_path = image_service.get_image_file_path(image)
        # load_image_cv2 выбросит HTTPException(404), если файла нет на диске
        bgr_image = image_service.load_image_cv2(file_path)
        
        # 2. Вычисления (Чистая логика в BrightnessService)
        # Этот сервис сам проверит границы, отсортирует линии и вернет матрицу
        calc_result = BrightnessService.calculate_grid_means(
            bgr_image=bgr_image,
            vertical_lines=lines_params.vertical_lines,
            horizontal_lines=lines_params.horizontal_lines
        )
        
        # 3. Сохранение результата (ResultService)
        result_service = ResultService(db)
        means_list = calc_result["matrix"].tolist()
        
        # Упаковываем данные в новую структуру (params/data) и сохраняем
        saved_record = await result_service.save_structured_result(
            image_id=image_id,
            method_name="calculate_mean_lines",
            params={
                "vertical_lines": calc_result["vertical_lines"],
                "horizontal_lines": calc_result["horizontal_lines"],
                "image_width": calc_result["width"],
                "image_height": calc_result["height"]
            },
            data={
                "means": means_list
            },
            clear_previous=True  # Удаляем старые расчеты для этой картинки
        )
        
        logger.info(f"Calculated mean lines for image {image_id}, result_id: {saved_record.id}")
        
        return MeanLinesResponse(
            success=True,
            message=f"Successfully calculated mean for grid",
            means=means_list,
            image_id=image_id,
            result_id=saved_record.id,
            vertical_lines=calc_result["vertical_lines"],
            horizontal_lines=calc_result["horizontal_lines"]
        )

    # Централизованная обработка кастомных исключений
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidGridError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except CalculationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in calculate-mean-lines: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during analysis")


@router.post("/calculate-categorized-mean/{image_id}", response_model=CategorizedMeanResponse)
async def calculate_categorized_mean(
    image_id: int,
    request: CategorizedMeanRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        # Валидация входных данных
        if image_id != request.imageID:
            raise DataMismatchError("Image ID in URL and body must match")
            
        # 1. Загрузка изображения
        image_service = ImageService(db)
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise ResourceNotFoundError(f"Image {image_id} not found")
            
        file_path = image_service.get_image_file_path(image)
        bgr_image = image_service.load_image_cv2(file_path)

        # 2. Вычисления
        # Шаг А: Считаем базовую матрицу яркости
        grid_result = BrightnessService.calculate_grid_means(
            bgr_image=bgr_image,
            vertical_lines=request.verticalLines,
            horizontal_lines=request.horizontalLines
        )
        
        # Шаг Б: Считаем статистику по категориям
        max_rows = len(grid_result["horizontal_lines"]) - 1
        max_cols = len(grid_result["vertical_lines"]) - 1
        
        stats_result = BrightnessService.calculate_categorized_stats(
            means_matrix=grid_result["matrix"],
            selected_cells=request.selectedCells,
            categories=request.selectionCategories,
            max_rows=max_rows,
            max_cols=max_cols
        )
        
        # 3. Сохранение
        result_service = ResultService(db)
        
        saved_record = await result_service.save_structured_result(
            image_id=image_id,
            method_name="calculate_categorized_mean",
            params={
                "verticalLines": grid_result["vertical_lines"],
                "horizontalLines": grid_result["horizontal_lines"],
                "selectedCells": [cell.dict() for cell in request.selectedCells],
                "selectionCategories": [cat.dict() for cat in request.selectionCategories],
                "selectedCellsCount": stats_result["selectedCellsCount"]
            },
            data={
                "overallMean": stats_result["overallMean"],
                "categoryMeansAverage": stats_result["categoryMeansAverage"],
                "categoryResults": stats_result["categoryResults"],
                "totalCells": grid_result["matrix"].size,
                "confirmed": True
            },
            clear_previous=True
        )
        
        return CategorizedMeanResponse(
            success=True,
            message=f"Calculated stats for {len(stats_result['categoryResults'])} categories",
            imageId=image_id,
            resultId=saved_record.id,
            allCellsMean=0.0, # Поле устарело, но нужно для фронтенда
            categoryResults=stats_result["categoryResults"],
            overallMean=stats_result["overallMean"] or 0.0,
            verticalLines=grid_result["vertical_lines"],
            horizontalLines=grid_result["horizontal_lines"],
            totalCells=grid_result["matrix"].size,
            selectedCellsCount=stats_result["selectedCellsCount"]
        )

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (InvalidGridError, DataMismatchError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EmptySelectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in calculate-categorized-mean: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/categorized-mean/{image_id}/result")
async def get_categorized_mean_result(image_id: int, db: AsyncSession = Depends(get_db)):
    """Получение сохраненного результата категоризованного анализа"""
    try:
        result_service = ResultService(db)
        
        # Получаем запись для метаданных (id, created_at)
        record = await result_service.get_latest_result(image_id, "calculate_categorized_mean")
        if not record:
            raise HTTPException(status_code=404, detail=f"Categorized mean result not found for image {image_id}")
            
        # Получаем данные (params + data объединены)
        unpacked_data = await result_service.get_latest_result_data(image_id, "calculate_categorized_mean")
        
        return {
            "success": True,
            "result_id": record.id,
            "image_id": record.image_id,
            "method": record.name_method,
            "created_at": record.created_at,
            "result": unpacked_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting categorized result: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving result")


@router.get("/result/{image_id}")
async def get_manual_result(image_id: int, db: AsyncSession = Depends(get_db)):
    """Получение последнего результата calculate_mean_lines"""
    try:
        result_service = ResultService(db)
        
        record = await result_service.get_latest_result(image_id, "calculate_mean_lines")
        flat_data = await result_service.get_latest_result_data(image_id, "calculate_mean_lines")
        
        if not record or not flat_data:
            raise HTTPException(status_code=404, detail=f"Manual analysis result not found for image {image_id}")
        
        # Маппинг для соответствия ожидаемому фронтендом формату
        return {
            "id": record.id,
            "image_id": record.image_id,
            "parameters": {
                "image_id": record.image_id,
                # Данные могут быть в params (новая структура) или корне (старая), unpack это уже решил
                "horizontal_lines": flat_data.get("horizontal_lines", []),
                "vertical_lines": flat_data.get("vertical_lines", []),
                "image_width": flat_data.get("image_width", 0),
                "image_height": flat_data.get("image_height", 0)
            },
            "brightness_data": flat_data.get("means", []),
            "created_at": record.created_at,
            "updated_at": None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting manual result: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving result")