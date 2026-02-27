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

from app.models.result import Results
from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.service.computation.cluster_service import ClusterService
from app.core.exceptions import ResourceNotFoundError, CalculationError
from app.schemas.result import ResultResponse




logger = logging.getLogger(__name__)
router = APIRouter()

class AutoCropRequest(BaseModel):
    image_id: int

class Crop(BaseModel):
    top: int
    bottom: int
    left: int
    right: int



def crop_without_white_borders(mask_bgr: np.ndarray, white_thresh=0.9):
    """
    Находит границы контента (не белого фона) и возвращает точный Bounding Box.
    Работает через векторизованные операции NumPy (быстрее циклов).
    """
    mask_gray = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2GRAY)
    H, W = mask_gray.shape

    # 1. Создаем булевы маски для строк и столбцов
    # Строка считается "белой", если доля белых пикселей > white_thresh
    row_is_white = np.mean(mask_gray == 255, axis=1) > white_thresh
    col_is_white = np.mean(mask_gray == 255, axis=0) > white_thresh

    # 2. Находим индексы, где есть контент (НЕ белые строки/столбцы)
    # np.where возвращает индексы элементов, где условие True (в данном случае ~row_is_white)
    rows_with_content = np.where(~row_is_white)[0]
    cols_with_content = np.where(~col_is_white)[0]

    # Если контента нет (весь лист белый)
    if rows_with_content.size == 0 or cols_with_content.size == 0:
        return None

    # 3. Определяем границы (Tight Bounding Box)
    top = rows_with_content[0] + 2
    bottom = rows_with_content[-1] -2  # +1 для корректного среза [top:bottom]
    left = cols_with_content[0] + 2
    right = cols_with_content[-1] -2

    # Возвращаем срез самой маски и координаты для кропа оригинала
    # Важно: мы возвращаем ПРЯМОУГОЛЬНИК, а не квадрат, чтобы не терять данные.
    # Квадратизация произойдет при наложении на черный фон.
    cropped_mask = mask_bgr[top:bottom, left:right]
    
    return cropped_mask, (top, bottom, left, right)


@router.post("/auto-crop", response_model=ResultResponse)
async def auto_crop_image(
    request: AutoCropRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для обрезки изображения по основным объектам.
    Поддерживаются методы KMEANS и THRESHOLD.
    Результат сохраняется в таблице Results.
    """
    image_service = ImageService(db)
    result_service = ResultService(db)
    cluster_service = ClusterService()

    # Получаем изображение из БД
    image_record = await image_service.get_image_by_id(request.image_id)
    path = image_service.get_image_file_path(image_record)
    image = image_service.load_image_cv2(path)
    if not image_record:
        raise HTTPException(status_code=404, detail="Image not found")

    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read image file")

        # --- K-MEANS Logic ---
    # Получаем L-канал (OpenCV Lab)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2Lab)
    L = lab[:, :, 0]
    data = L.reshape((-1, 1)).astype(np.float32)

    # KMeans 2 кластера
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 0.1)
    attempts = 3 # Можно меньше попыток для скорости
    flags = cv2.KMEANS_PP_CENTERS
    compactness, labels, centers = cv2.kmeans(data, 2, None, criteria, attempts, flags)
    
    # Определяем кластер "белого" (фон) как тот, у которого центр ярче (больше значение L)
    white_cluster_idx = int(np.argmax(centers))
    
    labels = labels.flatten()
    # Создаем маску: 255 там, где фон (белый кластер), 0 там, где объект
    # ВАЖНО: Ваша логика crop_without_white_borders ищет белые границы (255).
    # Значит, фон должен быть 255.
    mask = np.zeros_like(L, dtype=np.uint8)
    mask.flat[labels == white_cluster_idx] = 255 

    # BGR маска для совместимости с crop-функцией
    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

    # --- Cropping Logic ---
    crop_res = crop_without_white_borders(mask_bgr)

    cropped_mask, (top, bottom, left, right) = crop_res
    return ResultResponse(
        success=True,
        message="Image cropped successfully",
        data=Crop(
            top=top,
            bottom=bottom,
            left=left,
            right=right
        )
    )
    

@router.post("/crop-image/{image_id}", response_model=ResultResponse)
async def crop_image(
    image_id: int,
    crop: Crop,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для обрезки изображения по заданным координатам.
    Результат сохраняется в таблице Results.
    """
    image_service = ImageService(db)

    # Получаем изображение из БД
    image_record = await image_service.get_image_by_id(image_id)
    if not image_record:
        raise HTTPException(status_code=404, detail="Image not found")

    # Загружаем изображение с диска
    image_path = image_service.get_image_file_path(image_record)
    
    image = image_service.load_image_cv2(image_path)
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read image file")

    # Кропаем изображение по заданным координатам
    cropped_image = image[crop.top:crop.bottom, crop.left:crop.right]
    if cropped_image.size == 0:
        raise HTTPException(status_code=400, detail="Cropped area is empty")

    # Сохраняем результат в БД (фоновая задача)
    async def save_cropped_result():
        async with AsyncSessionLocal() as bg_db:
            bg_result_service = ResultService(bg_db)
            await bg_result_service.save_structured_result(
                image_id=image_id,
                method_name="crop",
                params=crop.model_dump(),
                data=None  # Можно сохранить путь к файлу или другие данные
            )
    
    background_tasks.add_task(save_cropped_result)

    return ResultResponse(
        success=True,
        message="Image cropped and result saving in background",
        data=None
    )


@router.get("/get-crop/{image_id}", response_model=ResultResponse)
async def get_crop_results(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для получения результатов кропа изображения.
    """
    result_service = ResultService(db)

    # Получаем последний результат кропа для данного изображения
    result_record = await result_service.get_latest_result(image_id, "crop")
    if not result_record:
        raise HTTPException(status_code=404, detail="No crop results found for this image")

    unpacked_result = result_record.result.get("params", {})
    crop_data = unpacked_result

    return ResultResponse(
        success=True,
        message="Crop results retrieved successfully",
        data=Crop(
            top=crop_data.get("top"),
            bottom=crop_data.get("bottom"),
            left=crop_data.get("left"),
            right=crop_data.get("right")
        )
    )

@router.get("/download-cropped-image/{image_id}")
async def download_cropped_image(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для скачивания обрезанного изображения.
    """
    image_service = ImageService(db)
    result_service = ResultService(db)

    # Получаем изображение из БД
    image_record = await image_service.get_image_by_id(image_id)
    if not image_record:
        raise HTTPException(status_code=404, detail="Image not found")

    # Получаем последний результат кропа для данного изображения
    result_record = await result_service.get_latest_result(image_id, "crop")
    if not result_record:
        raise HTTPException(status_code=404, detail="No crop results found for this image")

    crop_data = result_record.result.get("params", {})
    top = crop_data.get("top")
    bottom = crop_data.get("bottom")
    left = crop_data.get("left")
    right = crop_data.get("right")

    # Загружаем изображение с диска
    image_path = image_service.get_image_file_path(image_record)
    image = image_service.load_image_cv2(image_path)
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read image file")

    # Кропаем изображение по сохраненным координатам
    cropped_image = image[top:bottom, left:right]
    if cropped_image.size == 0:
        raise HTTPException(status_code=400, detail="Cropped area is empty")

    # Сохраняем временный файл для скачивания
    temp_path = Path(f"temp/cropped_{image_id}.png")
    cv2.imwrite(str(temp_path), cropped_image)

    return FileResponse(
        path=temp_path,
        filename=f"cropped_image_{image_id}.png",
        media_type='image/png'
    )