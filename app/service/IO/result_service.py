from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
import logging

from app.models.result import Results
from app.service.IO.base_service import BaseService

logger = logging.getLogger(__name__)

class ResultService(BaseService):
    """
    Сервис для работы с таблицей Results.
    Обеспечивает упаковку/распаковку JSON и управление записями.
    """

    def _pack(self, params: Dict[str, Any], data: Dict[str, Any], resources: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Упаковка данных в структуру для БД: {params, data, resources}"""
        return {
            "params": params,
            "data": data,
            "resources": resources or []
        }

    def _unpack(self, db_json: Any) -> Dict[str, Any]:
        """Распаковка данных для API. Объединяет params и data в плоский словарь."""
        if not isinstance(db_json, dict):
            return db_json or {}
        
        # Поддержка новой структуры
        if "params" in db_json and "data" in db_json:
            return {**db_json["params"], **db_json["data"]}
        
        # Поддержка старой структуры (backward compatibility)
        return db_json

    async def get_latest_result(self, image_id: int, method_name: str) -> Optional[Results]:
        """
        Получение последней записи результата.
        Сортировка по created_at и id для стабильности тестов.
        """
        try:
            query = select(Results).where(
                Results.name_method == method_name,
                Results.image_id == image_id
            ).order_by(
                Results.created_at.desc(),
                Results.id.desc()
            ).limit(1)
            
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"DB Error getting latest result for {method_name}: {e}")
            raise HTTPException(status_code=500, detail="Database error retrieving results")

    async def get_latest_result_data(self, image_id: int, method_name: str) -> Optional[Dict[str, Any]]:
        """Получение готового (распакованного) словаря данных."""
        record = await self.get_latest_result(image_id, method_name)
        if not record:
            return None
        return self._unpack(record.result)

    async def save_structured_result(
        self,
        image_id: int,
        method_name: str,
        params: Dict[str, Any],
        data: Dict[str, Any],
        resources: List[Dict[str, Any]] = None,
        clear_previous: bool = True
    ) -> Results:
        """
        Сохранение результата.
        :param clear_previous: Если True, удаляет все старые результаты этого метода для данного изображения.
        """
        try:
            # 1. Очистка старых записей
            if clear_previous:
                old_results_query = select(Results).where(
                    Results.name_method == method_name,
                    Results.image_id == image_id
                )
                result = await self.db.execute(old_results_query)
                for record in result.scalars().all():
                    await self.db.delete(record)
                    # Примечание: файлы удалятся автоматически через event listener в модели Results
            
            # 2. Упаковка
            packed_json = self._pack(params, data, resources)
            
            # 3. Сохранение
            new_result = Results(
                image_id=image_id,
                name_method=method_name,
                result=packed_json
            )
            
            self.db.add(new_result)
            await self.db.commit()
            await self.db.refresh(new_result)
            
            return new_result

        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error saving structured result for {method_name}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error saving analysis result")
        
    async def create_pending_result(
        self,
        image_id: int,
        method_name: str,
        params: Dict[str, Any],
        clear_previous: bool = True
    ) -> Results:
        """
        Создает запись со статусом 'processing'. 
        Это нужно вызвать ДО запуска фоновой задачи.
        """
        try:
            # 1. Очистка старых, если нужно
            if clear_previous:
                old_results = await self.db.execute(
                    select(Results).where(
                        Results.name_method == method_name,
                        Results.image_id == image_id
                    )
                )
                for record in old_results.scalars().all():
                    await self.db.delete(record)
            
            # 2. Формируем JSON со статусом
            initial_json = self._pack(
                params=params,
                data={"status": "processing", "progress": 0}, # Флаг процессинга
                resources=[]
            )
            
            # 3. Создаем запись
            new_result = Results(
                image_id=image_id,
                name_method=method_name,
                result=initial_json
            )
            
            self.db.add(new_result)
            await self.db.commit()
            await self.db.refresh(new_result)
            
            return new_result
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error creating pending result: {e}")
            raise HTTPException(status_code=500, detail="Database error")

    async def update_result_data(
        self,
        result_id: int,
        data: Dict[str, Any],
        resources: List[Dict[str, Any]] = None
    ) -> Results:
        """
        Обновляет уже созданную запись (когда задача завершилась).
        """
        try:
            # Получаем текущую запись, чтобы сохранить params
            query = select(Results).where(Results.id == result_id)
            res = await self.db.execute(query)
            record = res.scalar_one_or_none()
            
            if not record:
                # Если запись удалили пока шла задача
                logger.warning(f"Result {result_id} not found during update")
                return None

            # Берем старые params, чтобы не потерять их
            current_json = record.result or {}
            params = current_json.get("params", {})
            
            # Формируем новый JSON (status перезапишется данными)
            new_json = self._pack(params, data, resources)
            
            record.result = new_json
            await self.db.commit()
            await self.db.refresh(record)
            return record
            
        except Exception as e:
            await self.rollback_db()
            logger.error(f"Error updating result {result_id}: {e}")
            # Не рейзим HTTP ошибку, т.к. это выполняется в фоне
            return None

    async def mark_as_failed(self, result_id: int, error_message: str):
        """Помечает результат как ошибочный"""
        await self.update_result_data(
            result_id, 
            data={"status": "failed", "error": error_message}
        )