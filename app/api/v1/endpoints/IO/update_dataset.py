from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.dataset import DatasetResponse, UpdateDatasetForm
from app.service.IO.dataset_service import DatasetService

router = APIRouter()


@router.put("/update-dataset/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: int,
    payload: UpdateDatasetForm,
    db: AsyncSession = Depends(get_db)
):
    dataset_service = DatasetService(db)

    if payload.title is None and payload.description is None:
        raise HTTPException(status_code=400, detail="No dataset fields to update")

    return await dataset_service.update_dataset(
        dataset_id=dataset_id,
        title=payload.title,
        description=payload.description,
    )