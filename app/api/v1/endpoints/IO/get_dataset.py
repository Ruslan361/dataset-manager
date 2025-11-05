from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import asc, desc, select, func
from app.schemas.dataset import ResponseDatasetsList, GetDatasetsList, SortOrder, DatasetResponse
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
    try:
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
        
        # Подсчет общего количества
        count_stmt = select(func.count(Dataset.id))
        total_result = await db.execute(count_stmt)
        total_count = total_result.scalar()
        
        # Основной запрос с сортировкой и пагинацией
        stmt = select(Dataset).order_by(order_by).offset(query.start).limit(query.end - query.start)
        result = await db.execute(stmt)
        datasets = result.scalars().all()
        
        logger.info(f"Retrieved {len(datasets)} datasets with sort: {query.sort_field} {query.sort_order}")
        
        return ResponseDatasetsList(
            datasets=datasets,
            total=total_count,
            start=query.start,
            end=query.end
        )
        
    except Exception as e:
        logger.error(f"Error retrieving datasets: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving datasets")