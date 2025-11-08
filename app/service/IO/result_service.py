from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
import logging

from app.models.result import Results
from app.service.IO.base_service import BaseService

logger = logging.getLogger(__name__)

class ResultService(BaseService):
    """Сервис для работы с результатами"""
    
    async def create_result(
        self, 
        image_id: int,
        filename: str,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Results:
        """Создание записи результата в БД"""
        try:
            new_result = Results(
                image_id=image_id,
                filename=filename,
                description=description,
                parameters=parameters
            )
            self.db.add(new_result)
            await self.db.commit()
            await self.db.refresh(new_result)
            return new_result
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error creating result record: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")

    async def get_results_by_image(self, image_id: int) -> List[Results]:
        """Получение всех результатов для изображения"""
        try:
            results_query = select(Results).where(Results.image_id == image_id)
            results_result = await self.db.execute(results_query)
            results = results_result.scalars().all()
            return results
        except Exception as e:
            logger.error(f"Error getting results for image {image_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Database error")

    async def save_analysis_result(
        self, 
        method_name: str, 
        result_data: Dict[str, Any], 
        image_id: int
    ) -> Results:
        """Сохранение результата анализа"""
        try:
            db_result = Results(
                name_method=method_name,
                result=result_data,
                image_id=image_id
            )
            self.db.add(db_result)
            await self.db.commit()
            await self.db.refresh(db_result)
            return db_result
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error saving analysis result: {str(e)}")
            raise HTTPException(status_code=500, detail="Error saving analysis result")