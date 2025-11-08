from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import asc, desc
from app.schemas.dataset import ResponseDatasetsList, GetDatasetsList, SortOrder
from app.service.IO.dataset_service import DatasetService
from app.models.dataset import Dataset
from app.db.session import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/get-datasets-list", response_model=ResponseDatasetsList)
async def get_datasets_list(
    query: GetDatasetsList, 
    db: AsyncSession = Depends(get_db)
):
    """Получение списка датасетов с пагинацией и сортировкой"""
    dataset_service = DatasetService(db)
    
    try:
        # Валидация и подготовка параметров сортировки
        sort_column, order_by = _prepare_sort_params(query)
        
        # Получение данных через сервис
        datasets, total_count = await dataset_service.get_datasets_list(
            start=query.start,
            limit=query.end - query.start,
            sort_column=sort_column,
            order_by=order_by
        )
        
        logger.info(f"Retrieved {len(datasets)} datasets with sort: {query.sort_field} {query.sort_order}")
        
        return ResponseDatasetsList(
            datasets=datasets,
            total=total_count,
            start=query.start,
            end=query.end
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_datasets_list endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")

def _prepare_sort_params(query: GetDatasetsList):
    """Подготовка параметров сортировки"""
    # Мапинг полей схемы на колонки модели
    sort_mapping = {
        "id": Dataset.id,
        "title": Dataset.title,
        "description": Dataset.description,
        "created_at": Dataset.created_at,
        "updated_at": Dataset.updated_at
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