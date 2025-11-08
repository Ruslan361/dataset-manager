from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.result import ResultResponse 
from app.schemas.dataset import CreateDatasetForm
from app.service.IO.dataset_service import DatasetService
from app.db.session import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/create-dataset", response_model=ResultResponse)
async def create_dataset(
    dataset: CreateDatasetForm, 
    db: AsyncSession = Depends(get_db)
):
    """Создание нового датасета"""
    dataset_service = DatasetService(db)
    
    try:
        # Создание датасета через сервис
        new_dataset = await dataset_service.create_dataset(
            title=dataset.title,
            description=dataset.description
        )
        
        return ResultResponse(
            success=True,
            message=f"Dataset '{new_dataset.title}' created successfully with ID: {new_dataset.id}"
        )
        
    except HTTPException:
        # HTTPException уже обработаны в сервисе
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_dataset endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")