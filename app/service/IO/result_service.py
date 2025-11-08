from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
import logging

from app.models.result import Results
from app.service.IO.base_service import BaseService

logger = logging.getLogger(__name__)

class ResultService(BaseService):
    """Сервис для работы с результатами"""
    
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