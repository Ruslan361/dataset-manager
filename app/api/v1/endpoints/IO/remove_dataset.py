from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.result import ResultResponse
from app.service.IO.dataset_service import DatasetService
from app.db.session import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.delete("/remove-dataset/{dataset_id}", response_model=ResultResponse)
async def remove_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаление датасета со всеми изображениями и файлами"""
    dataset_service = DatasetService(db)

    try:
        # Удаление датасета вместе с изображениями, результатами и файлами
        # (404 бросает сам delete_dataset если датасет не найден)
        deleted_dataset, images_count = await dataset_service.delete_dataset(dataset_id)

        success_message = f"Dataset '{deleted_dataset.title}' (ID: {dataset_id}) and {images_count} images deleted successfully"
        
        logger.info(success_message)
        
        return ResultResponse(
            success=True,
            message=success_message
        )
        
    except HTTPException:
        # HTTPException уже обработаны в сервисах
        raise
    except Exception as e:
        logger.error(f"Unexpected error in remove_dataset endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")