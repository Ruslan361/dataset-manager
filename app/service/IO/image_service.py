from typing import Optional, List
from pathlib import Path
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
import cv2
import logging
import shutil

from app.models.image import Image
from app.models.dataset import Dataset
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)

class ImageService(BaseService):
    """Сервис для работы с изображениями"""
    
    async def get_image_by_id(self, image_id: int) -> Optional[Image]:
        """Получение изображения по ID"""
        try:
            image_query = select(Image).where(Image.id == image_id)
            result = await self.db.execute(image_query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting image {image_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def get_images_from_dataset(
        self, 
        dataset_id: int, 
        start: int, 
        limit: int, 
        sort_column, 
        order_by
    ) -> tuple[List[Image], int]:
        """Получение списка изображений из датасета с пагинацией"""
        try:
            # Подсчет общего количества
            count_query = select(func.count(Image.id)).where(Image.dataset_id == dataset_id)
            count_result = await self.db.execute(count_query)
            total_count = count_result.scalar()
            
            # Получение изображений
            images_query = select(Image)\
                .where(Image.dataset_id == dataset_id)\
                .order_by(order_by)\
                .offset(start)\
                .limit(limit)
            
            images_result = await self.db.execute(images_query)
            images = images_result.scalars().all()
            
            return images, total_count
        except Exception as e:
            logger.error(f"Error getting images from dataset {dataset_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def create_image(self, filename: str, original_filename: str, dataset_id: int) -> Image:
        """Создание записи изображения в БД"""
        try:
            image = Image(
                filename=filename,
                original_filename=original_filename,
                dataset_id=dataset_id
            )
            self.db.add(image)
            await self.db.commit()
            await self.db.refresh(image)
            return image
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error creating image record: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def delete_image(self, image_id: int) -> Image:
        """Удаление изображения из БД"""
        try:
            image = await self.get_image_by_id(image_id)
            if not image:
                raise HTTPException(status_code=404, detail=f"Image with id {image_id} not found")
            
            await self.db.delete(image)
            await self.db.commit()
            return image
        except HTTPException:
            await self.rollback_db()
            raise
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error deleting image {image_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    async def delete_images_by_dataset(self, dataset_id: int) -> int:
        """Удаление всех изображений датасета"""
        try:
            # Подсчет количества изображений
            images_count_query = select(Image).where(Image.dataset_id == dataset_id)
            images_result = await self.db.execute(images_count_query)
            images_count = len(images_result.scalars().all())
            
            # Удаление записей
            await self.db.execute(delete(Image).where(Image.dataset_id == dataset_id))
            
            return images_count
        except Exception as e:
            logger.error(f"Error deleting images from dataset {dataset_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")
    
    def get_image_file_path(self, image: Image) -> Path:
        """Получение пути к файлу изображения"""
        return Path(f"uploads/images/{image.dataset_id}/{image.filename}")
    
    def validate_file_exists(self, file_path: Path) -> bool:
        """Проверка существования файла"""
        return file_path.exists() and file_path.is_file()
    
    def load_image_cv2(self, file_path: Path):
        """Загрузка изображения через OpenCV"""
        if not self.validate_file_exists(file_path):
            raise HTTPException(status_code=404, detail="Image file not found on server")
        
        bgr_image = cv2.imread(str(file_path))
        if bgr_image is None:
            raise HTTPException(status_code=400, detail="Failed to load image")
        
        return bgr_image
    
    def validate_image_bounds(self, image, vertical_lines: List[int], horizontal_lines: List[int]):
        """Валидация границ линий относительно размеров изображения"""
        height, width = image.shape[:2]
        
        if any(x < 0 or x >= width for x in vertical_lines):
            raise HTTPException(
                status_code=400,
                detail=f"Vertical lines must be within image width (0-{width-1})"
            )
        
        if any(y < 0 or y >= height for y in horizontal_lines):
            raise HTTPException(
                status_code=400,
                detail=f"Horizontal lines must be within image height (0-{height-1})"
            )