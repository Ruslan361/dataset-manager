import logging
from fastapi import FastAPI, BackgroundTasks, APIRouter, Depends, HTTPException
from concurrent.futures import ThreadPoolExecutor
import asyncio, time, uuid
from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.service.image_processor import ImageProcessor
from app.models.result import Results
import cv2
import numpy as np
from pathlib import Path
from fastapi.responses import FileResponse
import os

class CriteriaEnum(Enum):
    EPSILON = 'epsilon'
    MAX_ITRATIONS = 'max iterations'
    ALL = 'all'

class FlagsEnum(Enum):
    PP_CENTERS = 'pp'
    RANDOM = 'random'

class KMeansRequest(BaseModel):
    nclusters: int = 3
    criteria: CriteriaEnum = CriteriaEnum.ALL
    max_iterations: int = 100
    attempts: int = 5
    epsilon: float = 0.5
    flags: FlagsEnum = FlagsEnum.PP_CENTERS
    colors: list[tuple[int, int, int]]
    
    @field_validator('colors')
    def validate_colors_count(cls, v, values):
        if 'nclusters' in values.data and len(v) != values.data['nclusters']:
            raise ValueError(f"Number of colors ({len(v)}) must match nclusters ({values.data['nclusters']})")
        return v

logger = logging.getLogger(__name__)
router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)

def apply_kmeans_sync(
    bgr_image: np.ndarray, 
    nclusters: int,
    criteria: CriteriaEnum,
    max_iterations: int,
    attempts: int,
    epsilon: float,  # Добавляем epsilon параметр
    flags: FlagsEnum,
    colors: list[tuple[int, int, int]]
) -> dict:
    """Синхронное применение K-means кластеризации"""
    try:
        # Получаем L-канал для кластеризации
        processor = ImageProcessor(bgr_image)
        L_channel = processor.getLChanel()
        
        # Подготавливаем данные для K-means (используем только L-канал)
        data = L_channel.reshape((-1, 1)).astype(np.float32)
        
        # Настройка критериев остановки с использованием epsilon
        if criteria == CriteriaEnum.EPSILON:
            cv_criteria = (cv2.TERM_CRITERIA_EPS, max_iterations, epsilon)
        elif criteria == CriteriaEnum.MAX_ITRATIONS:
            cv_criteria = (cv2.TERM_CRITERIA_MAX_ITER, max_iterations, epsilon)
        else:  # ALL
            cv_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, max_iterations, epsilon)
        
        # Настройка флагов инициализации
        if flags == FlagsEnum.PP_CENTERS:
            cv_flags = cv2.KMEANS_PP_CENTERS
        else:  # RANDOM
            cv_flags = cv2.KMEANS_RANDOM_CENTERS
        
        # Применяем K-means
        compactness, labels, centers = cv2.kmeans(
            data, nclusters, None, cv_criteria, attempts, cv_flags
        )
        
        # Сортируем центроиды по возрастанию и получаем индексы сортировки
        centers_flat = centers.flatten()
        sorted_indices = np.argsort(centers_flat)
        sorted_centers = centers_flat[sorted_indices]
        
        # Создаем маппинг старых индексов на новые (отсортированные)
        label_mapping = np.zeros(nclusters, dtype=np.int32)
        for new_idx, old_idx in enumerate(sorted_indices):
            label_mapping[old_idx] = new_idx
        
        # Переназначаем метки согласно новой сортировке
        remapped_labels = label_mapping[labels.flatten()]
        
        # Создаем цветное изображение используя заданные цвета
        height, width = L_channel.shape
        colored_image = np.zeros((height, width, 3), dtype=np.uint8)
        
        for i in range(nclusters):
            mask = remapped_labels == i
            color_bgr = (colors[i][2], colors[i][1], colors[i][0])  # RGB -> BGR
            colored_image[mask.reshape(height, width)] = color_bgr
        
        # Подготавливаем результат - добавляем epsilon
        result_data = {
            "nclusters": nclusters,
            "criteria": criteria.value,
            "max_iterations": max_iterations,
            "attempts": attempts,
            "epsilon": epsilon,  # Добавляем epsilon в результат
            "flags": flags.value,
            "colors_rgb": colors,
            "centers_sorted": sorted_centers.tolist(),
            "compactness": float(compactness),
            "original_shape": bgr_image.shape,
            "processed_pixels": len(data)
        }
        
        return {
            "result_data": result_data,
            "colored_image": colored_image
        }
        
    except Exception as e:
        logger.error(f"K-means processing error: {str(e)}")
        raise

async def save_kmeans_result(
    db: AsyncSession,
    image_id: int,
    result_data: dict,
    colored_image: np.ndarray
) -> Results:
    """Сохранение результатов K-means в БД"""
    try:
        # Сохраняем обработанное изображение
        image_service = ImageService(db)
        original_image = await image_service.get_image_by_id(image_id)
        
        # Создаем путь для результата
        result_filename = f"{image_id}_kmeans_{result_data['nclusters']}.jpg"
        result_dir = Path(f"uploads/results/{original_image.dataset_id}")
        result_dir.mkdir(parents=True, exist_ok=True)
        result_path = result_dir / result_filename
        
        # Сохраняем изображение
        cv2.imwrite(str(result_path), colored_image)
        
        # Добавляем путь к результату
        result_data["result_image_path"] = str(result_path)
        result_data["result_filename"] = result_filename
        
        # Проверяем, есть ли уже результат K-means для этого изображения
        existing_query = select(Results).where(
            Results.name_method == "kmeans",
            Results.image_id == image_id
        )
        existing_result = await db.execute(existing_query)
        existing_record = existing_result.scalar_one_or_none()
        
        if existing_record:
            # Обновляем существующую запись
            update_stmt = update(Results).where(
                Results.id == existing_record.id
            ).values(result=result_data)
            await db.execute(update_stmt)
            await db.commit()
            
            # Получаем обновленную запись
            updated_query = select(Results).where(Results.id == existing_record.id)
            updated_result = await db.execute(updated_query)
            return updated_result.scalar_one()
        else:
            # Создаем новую запись
            result_service = ResultService(db)
            return await result_service.save_analysis_result(
                method_name="kmeans",
                result_data=result_data,
                image_id=image_id
            )
            
    except Exception as e:
        logger.error(f"Error saving K-means result: {str(e)}")
        raise

async def run_kmeans_task(
    image_id: int,
    kmeans_params: KMeansRequest,
    bgr_image: np.ndarray
):
    """Выполнение K-means в фоне"""
    from app.db.session import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        try:
            # Выполняем K-means - добавляем epsilon
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                executor,
                apply_kmeans_sync,
                bgr_image,
                kmeans_params.nclusters,
                kmeans_params.criteria,
                kmeans_params.max_iterations,
                kmeans_params.attempts,
                kmeans_params.epsilon,  # Передаем epsilon
                kmeans_params.flags,
                kmeans_params.colors
            )
            
            # Сохраняем результат
            await save_kmeans_result(
                db,
                image_id,
                result["result_data"],
                result["colored_image"]
            )
            
            logger.info(f"K-means completed for image {image_id}")
            
        except Exception as e:
            logger.error(f"K-means task failed for image {image_id}: {str(e)}")
            raise

@router.post("/kmeans/{image_id}")
async def apply_kmeans(
    image_id: int,
    kmeans_params: KMeansRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Применение K-means кластеризации к изображению"""
    try:
        # Создаем сервис для работы с изображениями
        image_service = ImageService(db)
        
        # Получаем запись изображения из БД
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise HTTPException(
                status_code=404, 
                detail=f"Image with id {image_id} not found"
            )
        
        # Получаем путь к файлу изображения
        file_path = image_service.get_image_file_path(image)
        
        # Проверяем существование файла
        if not image_service.validate_file_exists(file_path):
            raise HTTPException(
                status_code=404, 
                detail="Image file not found on server"
            )
        
        # Загружаем изображение через OpenCV
        bgr_image = image_service.load_image_cv2(file_path)
        
        # Валидация параметров
        if len(kmeans_params.colors) != kmeans_params.nclusters:
            raise HTTPException(
                status_code=400,
                detail=f"Number of colors ({len(kmeans_params.colors)}) must match nclusters ({kmeans_params.nclusters})"
            )
        
        # Запускаем K-means в фоне
        background_tasks.add_task(
            run_kmeans_task,
            image_id,
            kmeans_params,
            bgr_image
        )
        
        return {
            "success": True,
            "message": f"K-means clustering started for image {image_id}",
            "image_id": image_id,
            "parameters": {
                "nclusters": kmeans_params.nclusters,
                "criteria": kmeans_params.criteria.value,
                "max_iterations": kmeans_params.max_iterations,
                "attempts": kmeans_params.attempts,
                "epsilon": kmeans_params.epsilon,  # Добавляем epsilon в ответ
                "flags": kmeans_params.flags.value,
                "colors": kmeans_params.colors
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing image")

@router.get("/kmeans/{image_id}/result")
async def get_kmeans_result(image_id: int, db: AsyncSession = Depends(get_db)):
    """Получение результата K-means для изображения"""
    try:
        # Ищем результат K-means для этого изображения
        result_query = select(Results).where(
            Results.name_method == "kmeans",
            Results.image_id == image_id
        ).order_by(Results.created_at.desc())
        
        result = await db.execute(result_query)
        kmeans_result = result.scalar_one_or_none()
        
        if not kmeans_result:
            raise HTTPException(
                status_code=404,
                detail=f"K-means result not found for image {image_id}"
            )
        
        # Проверяем существование файла результата
        result_data = kmeans_result.result
        result_image_path = result_data.get("result_image_path")
        image_exists = False
        
        if result_image_path and os.path.exists(result_image_path):
            image_exists = True
        
        return {
            "result_id": kmeans_result.id,
            "image_id": kmeans_result.image_id,
            "method": kmeans_result.name_method,
            "created_at": kmeans_result.created_at,
            "result": kmeans_result.result,
            "has_result_image": image_exists,
            "result_image_path": result_image_path if image_exists else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting K-means result for image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting result")

@router.get("/kmeans/{image_id}/result/image")
async def get_kmeans_result_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """Получение обработанного изображения K-means"""
    try:
        # Ищем результат K-means для этого изображения
        result_query = select(Results).where(
            Results.name_method == "kmeans",
            Results.image_id == image_id
        ).order_by(Results.created_at.desc())
        
        result = await db.execute(result_query)
        kmeans_result = result.scalar_one_or_none()
        
        if not kmeans_result:
            raise HTTPException(
                status_code=404,
                detail=f"K-means result not found for image {image_id}"
            )
        
        # Получаем путь к обработанному изображению
        result_data = kmeans_result.result
        result_image_path = result_data.get("result_image_path")
        
        if not result_image_path or not os.path.exists(result_image_path):
            raise HTTPException(
                status_code=404,
                detail="Result image file not found"
            )
        
        # Возвращаем файл изображения
        filename = result_data.get("result_filename", f"kmeans_result_{image_id}.jpg")
        
        return FileResponse(
            path=result_image_path,
            media_type="image/jpeg",
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting K-means result image for image {image_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting result image")
