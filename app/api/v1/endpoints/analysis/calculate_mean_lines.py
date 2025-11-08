from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.image import Image
from app.models.result import Results
from app.db.session import get_db
from app.service.image_processor import ImageProcessor
from app.schemas.result import ResultResponse
import cv2
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Optional, Tuple
import numpy as np

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
    rowMeans: List[Optional[float]]  # Добавляем среднее по строкам
    rowMeansAverage: Optional[float]  # Добавляем общее среднее по строкам (без None)

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

async def get_image_and_validate(image_id: int, db: AsyncSession) -> Tuple[Image, np.ndarray, int, int]:
    """Общая функция для получения и валидации изображения"""
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
    
    height, width = bgr_image.shape[:2]
    return image, bgr_image, width, height

def prepare_lines_with_bounds(lines: List[float], max_size: int, axis_name: str) -> List[int]:
    """
    Подготовка линий: добавление граничных значений, удаление дубликатов, валидация
    """

    # Конвертация в целые числа
    int_lines = [int(round(line)) for line in lines]
    
    # Добавление граничных линий (0 и max_size-1)
    int_lines = [0] + int_lines + [max_size]
    
    # Удаление дубликатов и сортировка
    unique_lines = sorted(set(int_lines))
    
    # Проверка границ
    if any(x < 0 or x > max_size for x in unique_lines):
        raise HTTPException(
            status_code=400,
            detail=f"{axis_name} lines must be within image {axis_name.lower()} (0-{max_size-1})"
        )
    
    # Проверка минимального количества уникальных линий
    if len(unique_lines) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"At least 2 unique {axis_name.lower()} lines are required after deduplication"
        )
    
    return unique_lines

def validate_and_convert_lines(lines: List[float], max_size: int, axis_name: str) -> List[int]:
    """Валидация и конвертация линий в целые числа без добавления границ"""
    if len(lines) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"At least 2 {axis_name} lines are required"
        )
    
    # Конвертация в целые числа
    int_lines = [int(round(line)) for line in lines]
    
    # Проверка границ
    if any(x < 0 or x >= max_size for x in int_lines):
        raise HTTPException(
            status_code=400,
            detail=f"{axis_name} lines must be within image {axis_name.lower()} (0-{max_size-1})"
        )
    
    # Проверка сортировки
    if int_lines != sorted(int_lines):
        raise HTTPException(
            status_code=400,
            detail=f"{axis_name} lines must be sorted in ascending order"
        )
    
    return int_lines

async def _calculate_mean_matrix(
    image_id: int,
    vertical_lines_float: List[float],
    horizontal_lines_float: List[float],
    db: AsyncSession
) -> Tuple[np.ndarray, List[int], List[int], int, int]:
    """
    Внутренняя функция для расчета матрицы средних значений яркости.
    Не управляет транзакциями и не является эндпоинтом.
    """
    # Получение и валидация изображения
    image, bgr_image, width, height = await get_image_and_validate(image_id, db)
    
    # Подготовка линий с границами и удалением дубликатов
    vertical_lines = prepare_lines_with_bounds(vertical_lines_float, width, "Vertical")
    horizontal_lines = prepare_lines_with_bounds(horizontal_lines_float, height, "Horizontal")
    
    # Создание процессора изображений
    processor = ImageProcessor(bgr_image)
    
    # Вычисление средних значений яркости для областей
    means_array = processor.calculateMeanRelativeToLines(
        vertical_lines=vertical_lines,
        horizontal_lines=horizontal_lines
    )
    
    return means_array, vertical_lines, horizontal_lines, width, height

@router.post("/calculate-mean-lines/{image_id}", response_model=MeanLinesResponse)
async def calculate_mean_relative_to_lines(
    image_id: int,
    lines_params: MeanLinesRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        # Вызов внутренней функции для расчета
        means_array, vertical_lines, horizontal_lines, width, height = await _calculate_mean_matrix(
            image_id=image_id,
            vertical_lines_float=lines_params.vertical_lines,
            horizontal_lines_float=lines_params.horizontal_lines,
            db=db
        )
        
        # Конвертация numpy array в список для JSON ответа
        means_list = means_array.tolist()
        
        result_data = {
            "means": means_list,
            "vertical_lines": vertical_lines,
            "horizontal_lines": horizontal_lines,
            "image_width": width,
            "image_height": height,
            "confirmed": False
        }
        
        # Удаление предыдущих результатов calculate_mean_lines для данного изображения
        delete_query = select(Results).where(
            Results.name_method == "calculate_mean_lines",
            Results.image_id == image_id
        )
        existing_results = await db.execute(delete_query)
        existing_records = existing_results.scalars().all()
        
        for record in existing_records:
            await db.delete(record)
        
        # Сохранение нового результата в БД
        db_result = Results(
            name_method="calculate_mean_lines",
            result=result_data,
            image_id=image_id
        )
        db.add(db_result)
        await db.commit()
        await db.refresh(db_result)
        
        logger.info(f"Calculated and saved mean luminance for image {image_id} with {len(vertical_lines)-1}x{len(horizontal_lines)-1} grid, result_id: {db_result.id}")
        
        return MeanLinesResponse(
            success=True,
            message=f"Successfully calculated mean luminance for {len(means_list)}x{len(means_list[0]) if means_list else 0} regions",
            means=means_list,
            image_id=image_id,
            result_id=db_result.id,
            vertical_lines=vertical_lines,
            horizontal_lines=horizontal_lines
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error calculating mean lines for image {image_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Error calculating mean relative to lines")

@router.post("/calculate-categorized-mean/{image_id}", response_model=CategorizedMeanResponse)
async def calculate_categorized_mean(
    image_id: int,
    request: CategorizedMeanRequest,
    db: AsyncSession = Depends(get_db)
):
    #try:
        # Проверка соответствия image_id в URL и в теле запроса
        if image_id != request.imageID:
            raise HTTPException(
                status_code=400,
                detail="Image ID in URL and request body must match"
            )
        
        # Вызываем внутреннюю функцию для расчета матрицы средних
        means_array, vertical_lines, horizontal_lines, _, _ = await _calculate_mean_matrix(
            image_id=image_id,
            vertical_lines_float=request.verticalLines,
            horizontal_lines_float=request.horizontalLines,
            db=db
        )
        
        # Проверка валидности выбранных ячеек
        max_rows = len(horizontal_lines) - 1
        max_cols = len(vertical_lines) - 1
        
        for cell in request.selectedCells:
            if cell.row < 0 or cell.row >= max_rows:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cell row {cell.row} is out of bounds (0-{max_rows-1})"
                )
            if cell.col < 0 or cell.col >= max_cols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cell col {cell.col} is out of bounds (0-{max_cols-1})"
                )
        
        # Создание словаря категорий
        categories_dict = {cat.id: cat for cat in request.selectionCategories}
        
        # Группировка ячеек по категориям
        category_cells = {}
        for cell in request.selectedCells:
            if cell.categoryId not in category_cells:
                category_cells[cell.categoryId] = []
            category_cells[cell.categoryId].append(cell)
        
        # Вычисление средних значений по категориям
        category_results = []
        all_selected_values = []
        category_means_for_overall = []  # Для расчета общего среднего по категориям
        
        for category_id, cells in category_cells.items():
            if category_id not in categories_dict:
                raise HTTPException(
                    status_code=400,
                    detail=f"Category '{category_id}' not found in selectionCategories"
                )
            
            category = categories_dict[category_id]
            category_values = []
            cell_coords = []
            
            # Группируем ячейки по строкам для данной категории
            rows_dict = {}
            
            # Собираем значения для данной категории
            for cell in cells:
                value = means_array[cell.row, cell.col]
                category_values.append(value)
                all_selected_values.append(value)
                cell_coords.append({"row": cell.row, "col": cell.col})
                
                # Группируем по строкам
                if cell.row not in rows_dict:
                    rows_dict[cell.row] = []
                rows_dict[cell.row].append(value)
            
            if category_values:  # Если есть ячейки в категории
                # Вычисляем среднее для категории (по всем ячейкам)
                category_mean = float(np.mean(category_values))
                category_means_for_overall.append(category_mean)
                
                # Вычисляем средние по строкам
                row_means = []
                row_means_values = []  # Для расчета общего среднего по строкам (без None)
                
                # Проходим по всем строкам в сетке
                for row_idx in range(max_rows):
                    if row_idx in rows_dict:
                        row_mean = float(np.mean(rows_dict[row_idx]))
                        row_means.append(row_mean)
                        row_means_values.append(row_mean)
                    else:
                        row_means.append(None)
                
                # Вычисляем общее среднее по строкам (исключая None)
                row_means_average = float(np.mean(row_means_values)) if row_means_values else None
                
                category_results.append(CategoryMeanResult(
                    categoryId=category_id,
                    categoryName=category.name,
                    color=category.color,
                    meanValue=category_mean,
                    cellCount=len(cells),
                    cells=cell_coords,
                    rowMeans=row_means,
                    rowMeansAverage=row_means_average
                ))
        
        # Общее среднее по всем выбранным ячейкам (если есть выбранные ячейки)
        overall_mean = float(np.mean(all_selected_values)) if all_selected_values else None
        
        # Общее среднее по средним значениям категорий (если есть категории с ячейками)
        category_means_average = float(np.mean(category_means_for_overall)) if category_means_for_overall else None
        
        # Подготовка данных для сохранения в БД
        result_data = {
            "verticalLines": vertical_lines,
            "horizontalLines": horizontal_lines,
            "selectedCells": [cell.dict() for cell in request.selectedCells],
            "selectionCategories": [cat.dict() for cat in request.selectionCategories],
            "overallMean": overall_mean,
            "categoryMeansAverage": category_means_average,
            "categoryResults": [result.dict() for result in category_results],
            "totalCells": means_array.size,
            "selectedCellsCount": len(request.selectedCells),
            "confirmed": True
        }
        
        # Удаление предыдущих результатов calculate_categorized_mean для данного изображения
        delete_query = select(Results).where(
            Results.name_method == "calculate_categorized_mean",
            Results.image_id == image_id
        )
        existing_results = await db.execute(delete_query)
        existing_records = existing_results.scalars().all()
        
        for record in existing_records:
            await db.delete(record)
        
        # Создание новой записи
        db_result = Results(
            name_method="calculate_categorized_mean",
            result=result_data,
            image_id=image_id
        )
        db.add(db_result)
        await db.commit()
        await db.refresh(db_result)
        
        result_id = db_result.id
        logger.info(f"Created new categorized mean calculation for image {image_id}, result_id: {result_id}")
        
        return CategorizedMeanResponse(
            success=True,
            message=f"Successfully calculated categorized means for {len(category_results)} categories",
            imageId=image_id,
            resultId=result_id,
            allCellsMean=0.0,  # Убираем, так как это не используется
            categoryResults=category_results,
            overallMean=overall_mean or 0.0,
            verticalLines=vertical_lines,
            horizontalLines=horizontal_lines,
            totalCells=means_array.size,
            selectedCellsCount=len(request.selectedCells)
        )
        
    # except HTTPException:
    #     await db.rollback()
    #     raise
    # except Exception as e:
    #     logger.error(f"Error calculating categorized mean for image {image_id}: {str(e)}")
    #     await db.rollback()
    #     raise HTTPException(status_code=500, detail="Error calculating categorized mean")

@router.get("/categorized-mean/{image_id}/result")
async def get_categorized_mean_result(image_id: int, db: AsyncSession = Depends(get_db)):
    """Получение результата категоризованного анализа"""
    try:
        result_query = select(Results).where(
            Results.name_method == "calculate_categorized_mean",
            Results.image_id == image_id
        ).order_by(Results.created_at.desc())
        
        result = await db.execute(result_query)
        categorized_result = result.scalar_one_or_none()
        
        if not categorized_result:
            raise HTTPException(
                status_code=404,
                detail=f"Categorized mean result not found for image {image_id}"
            )
        
        return {
            "success": True,
            "result_id": categorized_result.id,
            "image_id": categorized_result.image_id,
            "method": categorized_result.name_method,
            "created_at": categorized_result.created_at,
            "result": categorized_result.result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting categorized mean result for image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting result")

@router.get("/result/{image_id}")
async def get_manual_result(image_id: int, db: AsyncSession = Depends(get_db)):
    """Получение последнего результата ручного анализа для изображения"""
    print("Ищу данные")
    try:
        # Ищем последний результат calculate_mean_lines для данного изображения
        result_query = select(Results).where(
            Results.name_method == "calculate_mean_lines",
            Results.image_id == image_id
        ).order_by(Results.created_at.desc()).limit(1)
        
        result = await db.execute(result_query)
        latest_result = result.scalar_one_or_none()
        
        if not latest_result:
            raise HTTPException(
                status_code=404,
                detail=f"Manual analysis result not found for image {image_id}"
            )
        
        
        # Преобразуем в формат, ожидаемый Frontend
        return {
            "id": latest_result.id,
            "image_id": latest_result.image_id,
            "parameters": {
                "image_id": latest_result.image_id,
                "horizontal_lines": latest_result.result.get("horizontal_lines", []),
                "vertical_lines": latest_result.result.get("vertical_lines", []),
                "image_width": latest_result.result.get("image_width", 0),
                "image_height": latest_result.result.get("image_height", 0)
            },
            "brightness_data": latest_result.result.get("means", []),
            "created_at": None,
            "updated_at": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting manual result for image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting manual analysis result {str(e)}")