from abc import ABC
from typing import Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import os

logger = logging.getLogger(__name__)

class BaseService(ABC):
    """Базовый класс для сервисов с обработкой ошибок"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def rollback_db(self):
        """Откат транзакции БД"""
        try:
            await self.db.rollback()
            logger.info("Database transaction rolled back")
        except Exception as e:
            logger.error(f"Error during database rollback: {str(e)}")
    
    def remove_file_safe(self, file_path: Path) -> bool:
        """Безопасное удаление файла"""
        try:
            if file_path and file_path.exists():
                os.remove(file_path)
                logger.info(f"File removed: {file_path}")
                return True
        except Exception as e:
            logger.error(f"Error removing file {file_path}: {str(e)}")
        return False