from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import asc, desc
from app.schemas.image import ResponseImagesList, GetImagesList, SortOrder
from app.service.IO.image_service import ImageService
from app.service.IO.dataset_service import DatasetService
from app.models.image import Image
from app.db.session import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/get-images-list/{dataset_id}", response_model=ResponseImagesList)
async def get_images_from_dataset(
    dataset_id: int,
    query: GetImagesList, 
    db: AsyncSession = Depends(get_db)
):
    """Получение списка изображений из датасета с пагинацией и сортировкой"""
    dataset_service = DatasetService(db)
    image_service = ImageService(db)
    
    try:
        # Проверяем существование датасета через сервис
        dataset = await dataset_service.get_dataset_by_id(dataset_id)
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset with id {dataset_id} not found"
            )
        
        # Валидация и подготовка параметров сортировки
        sort_column, order_by = _prepare_sort_params(query)
        
        # Получение изображений через сервис
        images, total_count = await image_service.get_images_from_dataset(
            dataset_id=dataset_id,
            start=query.start,
            limit=query.end - query.start,
            sort_column=sort_column,
            order_by=order_by
        )
        
        logger.info(f"Retrieved {len(images)} images from dataset {dataset_id} with sort: {query.sort_field} {query.sort_order}")
        
        return ResponseImagesList(
            images=images,
            total=total_count,
            start=query.start,
            end=query.end,
            dataset_id=dataset_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving images from dataset {dataset_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving images from dataset")

def _prepare_sort_params(query: GetImagesList):
    """Подготовка параметров сортировки"""
    # Мапинг полей схемы на колонки модели
    sort_mapping = {
        "id": Image.id,
        "filename": Image.filename,
        "original_filename": Image.original_filename,
        "dataset_id": Image.dataset_id
    }
    
    # Получаем колонку для сортировки
    sort_column = sort_mapping.get(query.sort_field)
    if not sort_column:
        raise HTTPException(status_code=400, detail=f"Invalid sort field: {query.sort_field}")
    
    # Применяем направление сортировки
    if query.sort_order == SortOrder.DESC:
        order_by = desc(sort_column)
    else:
        order_by = asc(sort_column)
    
    return sort_column, order_by