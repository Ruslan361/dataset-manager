from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from concurrent.futures import ThreadPoolExecutor
import asyncio
import uuid
import json
import logging
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)
router = APIRouter()

# Глобальный thread pool
thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="image_processing")

class TaskStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.QUEUED
    progress: int = 0
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: Optional[float] = field(default_factory=lambda: asyncio.get_event_loop().time())
    future: Optional[asyncio.Future] = field(default=None, init=False)

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.subscribers: Dict[str, List[Callable]] = {}  # task_id -> list of callback functions
        
    def add_task(self, task: Task) -> None:
        """Добавить задачу в менеджер"""
        self.tasks[task.task_id] = task
        logger.info(f"Task {task.task_id} ({task.task_type}) added to manager")
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Получить задачу по ID"""
        return self.tasks.get(task_id)
    
    def remove_task(self, task_id: str) -> None:
        """Удалить задачу"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            # Отменяем future если есть
            if task.future and not task.future.done():
                task.future.cancel()
            del self.tasks[task_id]
            # Очищаем подписчиков
            if task_id in self.subscribers:
                del self.subscribers[task_id]
            logger.info(f"Task {task_id} removed from manager")
    
    def subscribe_to_task(self, task_id: str, callback: Callable):
        """Подписаться на обновления задачи"""
        if task_id not in self.subscribers:
            self.subscribers[task_id] = []
        self.subscribers[task_id].append(callback)
        logger.info(f"Added subscriber for task {task_id}")
    
    def unsubscribe_from_task(self, task_id: str, callback: Callable):
        """Отписаться от обновлений задачи"""
        if task_id in self.subscribers and callback in self.subscribers[task_id]:
            self.subscribers[task_id].remove(callback)
            if not self.subscribers[task_id]:  # Если больше нет подписчиков
                del self.subscribers[task_id]
    
    async def notify_subscribers(self, task_id: str):
        """Уведомить всех подписчиков об изменении задачи"""
        if task_id not in self.subscribers:
            return
            
        task = self.get_task(task_id)
        if not task:
            return
        
        notification = {
            "task_id": task_id,
            "status": task.status.value,
            "progress": task.progress,
            "message": task.message,
            "completed": task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        }
        
        # Добавляем результат или ошибку если есть
        if task.result:
            notification["has_result"] = True
        if task.error:
            notification["error"] = task.error
        
        # Уведомляем всех подписчиков
        for callback in self.subscribers[task_id]:
            try:
                await callback(notification)
            except Exception as e:
                logger.error(f"Error notifying subscriber for task {task_id}: {e}")
    
    async def update_task_progress(self, task_id: str, progress: int, message: str = ""):
        """Обновить прогресс задачи"""
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Attempted to update non-existent task {task_id}")
            return
            
        task.progress = progress
        task.message = message
        
        logger.debug(f"Task {task_id} progress: {progress}% - {message}")
        await self.notify_subscribers(task_id)
    
    async def complete_task(self, task_id: str, result: dict):
        """Завершить задачу успешно"""
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Attempted to complete non-existent task {task_id}")
            return
            
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.progress = 100
        
        logger.info(f"Task {task_id} completed successfully")
        await self.notify_subscribers(task_id)
    
    async def fail_task(self, task_id: str, error: str):
        """Завершить задачу с ошибкой"""
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Attempted to fail non-existent task {task_id}")
            return
            
        task.status = TaskStatus.FAILED
        task.error = error
        
        logger.error(f"Task {task_id} failed: {error}")
        await self.notify_subscribers(task_id)
    
    async def cancel_task(self, task_id: str):
        """Отменить задачу"""
        task = self.get_task(task_id)
        if not task:
            return False
            
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            return False  # Уже завершена
            
        task.status = TaskStatus.CANCELLED
        if task.future:
            task.future.cancel()
            
        logger.info(f"Task {task_id} cancelled")
        await self.notify_subscribers(task_id)
        return True
    
    def get_task_summary(self, task_id: str) -> Optional[dict]:
        """Получить краткую информацию о задаче"""
        task = self.get_task(task_id)
        if not task:
            return None
            
        return {
            "task_id": task_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "progress": task.progress,
            "message": task.message,
            "has_result": task.result is not None,
            "has_error": task.error is not None,
            "created_at": task.created_at
        }
    
    def get_all_tasks_summary(self) -> List[dict]:
        """Получить краткую информацию о всех задачах"""
        return [self.get_task_summary(task_id) for task_id in self.tasks.keys()]
    
    async def cleanup_old_tasks(self, max_age_hours: float = 24):
        """Очистить старые завершенные задачи"""
        current_time = asyncio.get_event_loop().time()
        max_age_seconds = max_age_hours * 3600
        
        tasks_to_remove = []
        for task_id, task in self.tasks.items():
            if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and
                current_time - task.created_at > max_age_seconds):
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            self.remove_task(task_id)
        
        if tasks_to_remove:
            logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")

# Глобальный менеджер задач
task_manager = TaskManager()

# Функция для автоматической очистки старых задач
async def start_cleanup_scheduler():
    """Запустить периодическую очистку старых задач"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        await task_manager.cleanup_old_tasks()