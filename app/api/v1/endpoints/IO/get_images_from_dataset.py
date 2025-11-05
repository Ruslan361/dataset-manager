from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc, func
from app.schemas.image import ResponseImagesList, GetImagesList, ImageSortField, SortOrder
from app.models.image import Image
from app.models.dataset import Dataset
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
    try:
        # Проверяем существование датасета
        dataset_query = select(Dataset).where(Dataset.id == dataset_id)
        result = await db.execute(dataset_query)
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset with id {dataset_id} not found"
            )
        
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
        
        # Подсчет общего количества изображений в датасете
        count_query = select(func.count(Image.id)).where(Image.dataset_id == dataset_id)
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()
        
        # Основной запрос с фильтрацией по датасету, сортировкой и пагинацией
        images_query = select(Image)\
            .where(Image.dataset_id == dataset_id)\
            .order_by(order_by)\
            .offset(query.start)\
            .limit(query.end - query.start)
        
        images_result = await db.execute(images_query)
        images = images_result.scalars().all()
        
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