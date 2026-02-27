from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
from enum import Enum
from typing import List, Optional
import logging
import asyncio
import cv2
import numpy as np
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from app.db.session import get_db
# Импортируем фабрику сессий для фоновых задач (т.к. сессия из Depends закроется после ответа)
from app.db.session import AsyncSessionLocal 

from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.service.computation.cluster_service import ClusterService
from app.core.exceptions import ResourceNotFoundError, CalculationError

logger = logging.getLogger(__name__)
router = APIRouter()
from app.core.executor import get_executor # <--- Импорт

# Создаем пул потоков для тяжелых операций OpenCV, чтобы не блокировать Event Loop
executor = get_executor()

# --- Pydantic Models ---

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
    colors: List[tuple[int, int, int]]
    
    @field_validator('colors')
    def validate_colors_count(cls, v, values):
        # Проверяем, что количество цветов совпадает с количеством кластеров
        if 'nclusters' in values.data and len(v) != values.data['nclusters']:
            raise ValueError(f"Number of colors ({len(v)}) must match nclusters ({values.data['nclusters']})")
        return v

# --- Background Task ---

async def run_kmeans_task(
    result_id: int,       # ID записи в БД, которую нужно обновить
    image_id: int, 
    params: KMeansRequest, 
    bgr_image: np.ndarray, 
    dataset_id: int
):
    """
    Фоновая задача:
    1. Выполняет K-Means (CPU-bound).
    2. Сохраняет результат на диск (IO).
    3. Обновляет запись в БД (processing -> completed/failed).
    """
    # Создаем новую сессию БД, так как это фоновая задача
    async with AsyncSessionLocal() as db:
        result_service = ResultService(db)
        try:
            loop = asyncio.get_running_loop()
            
            # 1. Вычисления (в отдельном потоке, чтобы не блокировать сервер)
            calc_res = await loop.run_in_executor(
                executor,
                ClusterService.apply_kmeans,
                bgr_image,
                params.nclusters,
                params.criteria.value,
                params.max_iterations,
                params.attempts,
                params.epsilon,
                params.flags.value,
                params.colors
            )
            
            # 2. Сохранение файла на диск
            filename = f"{image_id}_kmeans_{params.nclusters}.jpg"
            save_dir = Path(f"uploads/results/{dataset_id}")
            save_dir.mkdir(parents=True, exist_ok=True)
            file_path = save_dir / filename
            
            # cv2.imwrite блокирующий, запускаем в потоке
            await loop.run_in_executor(
                executor,
                cv2.imwrite,
                str(file_path),
                calc_res.colored_image
            )
            
            # 3. Обновление записи в БД
            stats = calc_res.result_data
            
            # Данные для сохранения (статус меняется на completed)
            data_to_save = {
                "status": "completed", 
                "centers_sorted": getattr(stats, "centers_sorted", []),
                "compactness": float(getattr(stats, "compactness", 0.0)),
                "processed_pixels": int(getattr(stats, "processed_pixels", 0))
            }
            
            # Ресурсы (ссылка на файл)
            resources_to_save = [{
                "type": "image",
                "key": "clustered_image",
                "path": str(file_path)
            }]
            
            await result_service.update_result_data(
                result_id=result_id,
                data=data_to_save,
                resources=resources_to_save
            )
            
            logger.info(f"K-means task finished successfully for result_id {result_id}")
            
        except Exception as e:
            logger.error(f"K-means task failed for result_id {result_id}: {e}")
            # Важно: записываем ошибку в БД, чтобы фронтенд узнал о провале
            await result_service.mark_as_failed(result_id, str(e))

# --- Endpoints ---

@router.post("/kmeans/{image_id}")
async def apply_kmeans(
    image_id: int,
    kmeans_params: KMeansRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Запуск K-means кластеризации.
    Возвращает 200 OK со статусом "processing" сразу после валидации.
    """
    try:
        # 1. Валидация и загрузка изображения
        image_service = ImageService(db)
        result_service = ResultService(db)

        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise ResourceNotFoundError(f"Image {image_id} not found")

        file_path = image_service.get_image_file_path(image)
        # Загружаем изображение сразу, чтобы вернуть 404/400, если файл битый, до запуска задачи
        bgr_image = image_service.load_image_cv2(file_path)

        # Если в БД есть последний результат "crop", применяем сохранённые координаты.
        try:
            crop_record = await result_service.get_latest_result(image_id, "crop")
            if crop_record:
                params = (crop_record.result or {}).get("params") or {}
                top = params.get("top")
                bottom = params.get("bottom")
                left = params.get("left")
                right = params.get("right")
                # Проверяем, что все координаты целые числа
                if all(isinstance(v, int) for v in (top, bottom, left, right)):
                    h, w = bgr_image.shape[:2]
                    # Ограничиваем координаты пределами изображения
                    top = max(0, min(h, top))
                    bottom = max(0, min(h, bottom))
                    left = max(0, min(w, left))
                    right = max(0, min(w, right))
                    # Применяем кроп только если область непустая
                    if bottom > top and right > left:
                        bgr_image = bgr_image[top:bottom, left:right]
        except Exception:
            # В случае проблем с чтением/парсингом записи — продолжаем без кропа
            pass

        # 2. Создаем запись в БД со статусом "processing"
        
        # Сохраняем параметры запуска, чтобы они были видны на фронтенде
        params_dict = {
            "nclusters": kmeans_params.nclusters,
            "criteria": kmeans_params.criteria.value,
            "max_iterations": kmeans_params.max_iterations,
            "epsilon": kmeans_params.epsilon,
            "flags": kmeans_params.flags.value,
            "colors": kmeans_params.colors
        }
        
        # create_pending_result удалит старые результаты этого метода для этой картинки
        pending_record = await result_service.create_pending_result(
            image_id=image_id,
            method_name="kmeans",
            params=params_dict,
            clear_previous=True 
        )
        
        # 3. Добавляем задачу в фон
        background_tasks.add_task(
            run_kmeans_task,
            result_id=pending_record.id,
            image_id=image_id,
            params=kmeans_params,
            bgr_image=bgr_image,
            dataset_id=image.dataset_id
        )
        
        return {
            "success": True,
            "message": "K-means task queued",
            "image_id": image_id,
            "result_id": pending_record.id,
            "status": "processing"
        }
        
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting kmeans task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/kmeans/{image_id}/result")
async def get_kmeans_result(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Получение результата.
    Возвращает JSON с полем 'status', которое может быть: 'processing', 'completed', 'failed'.
    """
    try:
        result_service = ResultService(db)
        
        # Получаем запись (метаданные)
        record = await result_service.get_latest_result(image_id, "kmeans")
        
        if not record:
            raise HTTPException(status_code=404, detail="K-means calculation never started for this image")
            
        # Распаковываем данные (params + data)
        data = await result_service.get_latest_result_data(image_id, "kmeans")
        
        # Определяем статус (для обратной совместимости со старыми записями по умолчанию completed)
        status = data.get("status", "completed")
        
        # Проверяем наличие файла картинки (только если статус completed)
        has_image = False
        image_path = None
        
        if status == "completed":
            resources = record.result.get("resources", [])
            for r in resources:
                if r.get("key") == "clustered_image":
                    image_path = r.get("path")
                    break
            has_image = bool(image_path and os.path.exists(image_path))

        return {
            "result_id": record.id,
            "image_id": record.image_id,
            "method": record.name_method,
            "status": status,
            "created_at": record.created_at,
            "result": data,           # Содержит params, centers, compactness и т.д.
            "has_result_image": has_image,
            "error": data.get("error") # Будет заполнено, если status == failed
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting kmeans result: {e}")
        raise HTTPException(status_code=500, detail="Error getting result")


@router.get("/kmeans/{image_id}/result/image")
async def get_kmeans_result_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """
    Скачивание обработанного изображения.
    """
    try:
        result_service = ResultService(db)
        record = await result_service.get_latest_result(image_id, "kmeans")
        
        if not record:
             raise HTTPException(status_code=404, detail="Result not found")
        
        # Проверяем статус в самом JSON
        data = await result_service.get_latest_result_data(image_id, "kmeans")
        if data.get("status") == "processing":
            raise HTTPException(status_code=400, detail="Image is still processing")
        if data.get("status") == "failed":
             raise HTTPException(status_code=400, detail="Processing failed, no image available")

        # Ищем путь к файлу
        resources = record.result.get("resources", [])
        image_path = None
        for r in resources:
            if r.get("key") == "clustered_image":
                image_path = r.get("path")
                break
        
        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Result file missing on server")
        
        # Получаем имя файла для заголовка Content-Disposition
        filename = Path(image_path).name
            
        return FileResponse(
            path=image_path, 
            media_type="image/jpeg",
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving result image: {e}")
        raise HTTPException(status_code=500, detail="Error serving file")