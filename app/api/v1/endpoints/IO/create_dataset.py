from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.result import ResultResponse 
from app.schemas.dataset import CreateDatasetForm
from app.models.dataset import Dataset
from app.db.session import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/create-dataset", response_model=ResultResponse)
async def create_dataset(
    dataset: CreateDatasetForm, 
    db: AsyncSession = Depends(get_db)
):
    try:
        new_dataset = Dataset(
            title=dataset.title,
            description=dataset.description,
        )
        db.add(new_dataset)
        await db.commit()
        await db.refresh(new_dataset)
        
        return ResultResponse(
            success=True,
            message="Dataset created"
        )
    except Exception as e:
        logger.error(f"Error creating dataset: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Error creating dataset")