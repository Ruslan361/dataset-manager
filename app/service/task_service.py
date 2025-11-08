from typing import Optional, List, Dict, Any
from fastapi import HTTPException
import logging
import uuid
from app.core.task_manager import task_manager, Task, TaskStatus
from app.service.IO.base_service import BaseService

logger = logging.getLogger(__name__)

class TaskService:
    """Сервис для работы с задачами"""
    
    @staticmethod
    def create_task(task_type: str, **kwargs) -> str:
        """Создание новой задачи"""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            **kwargs
        )
        task_manager.add_task(task)
        logger.info(f"Created task {task_id} of type {task_type}")
        return task_id
    
    @staticmethod
    def get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
        """Получение задачи по ID"""
        task = task_manager.get_task(task_id)
        if not task:
            return None
        
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "progress": task.progress,
            "message": task.message,
            "result": task.result,
            "error": task.error,
            "created_at": task.created_at,
            "completed": task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        }
    
    @staticmethod
    def get_tasks_list(
        start: int = 0, 
        limit: int = 10,
        status_filter: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """Получение списка задач с пагинацией и фильтрацией"""
        all_tasks = []
        
        for task_id, task in task_manager.tasks.items():
            # Фильтрация по статусу
            if status_filter and task.status.value != status_filter:
                continue
                
            task_info = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status.value,
                "progress": task.progress,
                "message": task.message,
                "has_result": task.result is not None,
                "has_error": task.error is not None,
                "created_at": task.created_at,
                "completed": task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
            }
            all_tasks.append(task_info)
        
        # Сортировка по времени создания (новые первые)
        all_tasks.sort(key=lambda x: x["created_at"], reverse=True)
        
        # Пагинация
        total_count = len(all_tasks)
        tasks_page = all_tasks[start:start + limit]
        
        return tasks_page, total_count
    
    @staticmethod
    async def cancel_task(task_id: str) -> bool:
        """Отмена задачи"""
        success = await task_manager.cancel_task(task_id)
        if success:
            logger.info(f"Task {task_id} cancelled")
        else:
            logger.warning(f"Failed to cancel task {task_id}")
        return success
    
    @staticmethod
    def delete_task(task_id: str) -> bool:
        """Удаление задачи"""
        task = task_manager.get_task(task_id)
        if not task:
            return False
        
        # Можно удалять только завершенные задачи
        if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete running task. Cancel it first."
            )
        
        task_manager.remove_task(task_id)
        logger.info(f"Task {task_id} deleted")
        return True
    
    @staticmethod
    async def clear_all_tasks(only_completed: bool = True) -> int:
        """Очистка всех задач или только завершенных"""
        tasks_to_remove = []
        
        for task_id, task in task_manager.tasks.items():
            if only_completed:
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    tasks_to_remove.append(task_id)
            else:
                # Отменяем запущенные задачи перед удалением
                if task.status in [TaskStatus.QUEUED, TaskStatus.PROCESSING]:
                    await task_manager.cancel_task(task_id)
                tasks_to_remove.append(task_id)
        
        # Удаляем задачи
        for task_id in tasks_to_remove:
            task_manager.remove_task(task_id)
        
        logger.info(f"Cleared {len(tasks_to_remove)} tasks")
        return len(tasks_to_remove)
    
    @staticmethod
    def get_task_result(task_id: str) -> Optional[Dict[str, Any]]:
        """Получение результата выполнения задачи"""
        task = task_manager.get_task(task_id)
        if not task:
            return None
        
        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Task {task_id} is not completed yet"
            )
        
        return task.result
    
    @staticmethod
    def get_tasks_stats() -> Dict[str, Any]:
        """Получение статистики по задачам"""
        stats = {
            "total": 0,
            "queued": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }
        
        for task in task_manager.tasks.values():
            stats["total"] += 1
            stats[task.status.value] += 1
        
        return stats