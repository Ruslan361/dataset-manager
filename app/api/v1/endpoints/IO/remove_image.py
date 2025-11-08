from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.schemas.result import ResultResponse 
from app.service.IO.image_service import ImageService
from app.service.IO.file_services import FileService
from app.models.result import Results
from app.db.session import get_db
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter()

async def delete_all_image_results(db: AsyncSession, image_id: int):
    """Удаление всех результатов связанных с изображением"""
    try:
        # Получаем все результаты для данного изображения
        results_query = select(Results).where(Results.image_id == image_id)
        results = await db.execute(results_query)
        result_records = results.scalars().all()
        
        for result_record in result_records:
            try:
                result_data = result_record.result
                method_name = result_record.name_method
                
                if isinstance(result_data, dict):
                    # Для K-means - особая структура с result_image_path
                    if method_name == "kmeans":
                        result_image_path = result_data.get("result_image_path")
                        if result_image_path and os.path.exists(result_image_path):
                            os.remove(result_image_path)
                            logger.info(f"Deleted K-means result file: {result_image_path}")
                    
                    # Для других методов - стандартные пути к файлам
                    else:
                        # Проверяем различные возможные поля с путями к файлам
                        file_path_fields = [
                            "output_file_path", 
                            "processed_image_path", 
                            "result_path",
                            "blurred_image_path",
                            "analysis_result_path"
                        ]
                        
                        for field in file_path_fields:
                            file_path = result_data.get(field)
                            if file_path and os.path.exists(file_path):
                                os.remove(file_path)
                                logger.info(f"Deleted {method_name} result file: {file_path}")
                        
                        # Проверяем массивы файлов
                        if "result_files" in result_data and isinstance(result_data["result_files"], list):
                            for file_path in result_data["result_files"]:
                                if file_path and os.path.exists(file_path):
                                    os.remove(file_path)
                                    logger.info(f"Deleted {method_name} result file: {file_path}")
                
            except Exception as e:
                logger.warning(f"Failed to delete files for {result_record.name_method} result {result_record.id}: {str(e)}")
                continue
        
        # Удаляем все записи результатов из БД
        if result_records:
            delete_query = delete(Results).where(Results.image_id == image_id)
            await db.execute(delete_query)
            await db.commit()
            logger.info(f"Deleted {len(result_records)} result records for image {image_id}")
        
    except Exception as e:
        logger.error(f"Error deleting results for image {image_id}: {str(e)}")
        await db.rollback()
        raise

async def cleanup_empty_result_directories(dataset_id: int):
    """Очистка пустых директорий результатов"""
    try:
        result_dir = Path(f"uploads/results/{dataset_id}")
        if result_dir.exists() and result_dir.is_dir():
            remaining_files = list(result_dir.glob("*"))
            if not remaining_files:
                result_dir.rmdir()
                logger.info(f"Removed empty result directory: {result_dir}")
                
                # Проверяем родительскую директорию
                parent_dir = result_dir.parent
                if parent_dir.name == "results" and parent_dir.exists():
                    remaining_subdirs = list(parent_dir.glob("*"))
                    if not remaining_subdirs:
                        parent_dir.rmdir()
                        logger.info(f"Removed empty results directory: {parent_dir}")
    except Exception as e:
        logger.warning(f"Error cleaning up directories: {str(e)}")

@router.delete("/remove-image/{image_id}", response_model=ResultResponse)
async def remove_image(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаление изображения по ID с каскадным удалением всех связанных результатов"""
    image_service = ImageService(db)
    
    try:
        # Получение изображения
        image = await image_service.get_image_by_id(image_id)
        if not image:
            raise HTTPException(
                status_code=404,
                detail=f"Image with id {image_id} not found"
            )
        
        # Сохраняем dataset_id для очистки директорий
        dataset_id = image.dataset_id
        
        # Получение пути к файлу
        file_path = image_service.get_image_file_path(image)
        
        # Удаление всех связанных результатов (K-means и других)
        await delete_all_image_results(db, image_id)
        
        # Удаление записи из БД
        deleted_image = await image_service.delete_image(image_id)
        
        # Удаление физического файла
        file_deleted = FileService.remove_file(file_path)
        if not file_deleted:
            logger.warning(f"File not found or couldn't be deleted: {file_path}")
        
        # Очистка пустых директорий результатов
        await cleanup_empty_result_directories(dataset_id)
        
        logger.info(f"Image {image_id} and all its results deleted successfully")
        
        return ResultResponse(
            success=True,
            message=f"Image {image_id} deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in remove_image endpoint: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error occurred")