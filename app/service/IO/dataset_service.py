from typing import Optional, List
from sqlalchemy import select, delete, asc, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
import logging

from app.models.dataset import Dataset
from app.models.image import Image
from app.models.result import Results
from app.service.IO.base_service import BaseService
from app.service.IO.image_service import ImageService
from app.service.IO.file_services import FileService
from pathlib import Path

logger = logging.getLogger(__name__)

class DatasetService(BaseService):
    """Сервис для работы с датасетами"""
    
    async def create_dataset(self, title: str, description: str) -> Dataset:
        """Создание нового датасета"""
        try:
            new_dataset = Dataset(
                title=title,
                description=description,
            )
            self.db.add(new_dataset)
            await self.db.commit()
            await self.db.refresh(new_dataset)
            
            logger.info(f"Created dataset: {new_dataset.id} - {title}")
            return new_dataset
            
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error creating dataset '{title}': {str(e)}")
            raise HTTPException(status_code=500, detail="Error creating dataset")
    
    async def get_dataset_by_id(self, dataset_id: int) -> Optional[Dataset]:
        """Получение датасета по ID"""
        try:
            dataset_query = select(Dataset).where(Dataset.id == dataset_id)
            result = await self.db.execute(dataset_query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting dataset {dataset_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def get_datasets_list(
        self, 
        start: int, 
        limit: int, 
        sort_column, 
        order_by
    ) -> tuple[List[Dataset], int]:
        """Получение списка датасетов с пагинацией"""
        try:
            # Подсчет общего количества
            count_stmt = select(func.count(Dataset.id))
            total_result = await self.db.execute(count_stmt)
            total_count = total_result.scalar()
            
            # Получение датасетов
            stmt = select(Dataset)\
                .order_by(order_by)\
                .offset(start)\
                .limit(limit)
            
            result = await self.db.execute(stmt)
            datasets = result.scalars().all()
            
            return datasets, total_count
            
        except Exception as e:
            logger.error(f"Error getting datasets list: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def delete_dataset(self, dataset_id: int) -> tuple[Dataset, int]:
        """Удаление датасета из БД с каскадным удалением изображений, результатов и файлов"""
        try:
            dataset = await self.get_dataset_by_id(dataset_id)
            if not dataset:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset with id {dataset_id} not found"
                )

            # Получаем ID всех изображений датасета
            img_rows = (await self.db.execute(
                select(Image.id).where(Image.dataset_id == dataset_id)
            )).scalars().all()
            images_count = len(img_rows)

            # Удаляем записи Results для всех изображений датасета
            if img_rows:
                await self.db.execute(
                    delete(Results).where(Results.image_id.in_(img_rows))
                )

            # Удаляем записи Image
            await self.db.execute(
                delete(Image).where(Image.dataset_id == dataset_id)
            )

            # Удаляем файлы с диска
            try:
                FileService.remove_directory(Path(f"uploads/images/{dataset_id}"))
                FileService.remove_directory(Path(f"uploads/results/{dataset_id}"))
            except Exception as fe:
                logger.warning(f"File system cleanup failed for dataset {dataset_id}: {fe}")

            # Удаляем сам датасет и фиксируем всё разом
            await self.db.delete(dataset)
            await self.db.commit()

            logger.info(f"Deleted dataset: {dataset_id}, removed {images_count} images")
            return dataset, images_count

        except HTTPException:
            await self.rollback_db()
            raise
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error deleting dataset {dataset_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def update_dataset(
        self, 
        dataset_id: int, 
        title: Optional[str] = None, 
        description: Optional[str] = None
    ) -> Dataset:
        """Обновление датасета"""
        try:
            dataset = await self.get_dataset_by_id(dataset_id)
            if not dataset:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset with id {dataset_id} not found"
                )
            
            if title is not None:
                dataset.title = title
            if description is not None:
                dataset.description = description
            
            await self.db.commit()
            await self.db.refresh(dataset)
            
            logger.info(f"Updated dataset: {dataset_id}")
            return dataset
            
        except HTTPException:
            await self.rollback_db()
            raise
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error updating dataset {dataset_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")