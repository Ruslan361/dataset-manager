from enum import Enum
from typing import Dict, Optional, Any
from datetime import datetime
import uuid

class TaskStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Task:
    def __init__(self, task_type: str):
        self.task_id = str(uuid.uuid4())
        self.task_type = task_type
        self.status = TaskStatus.QUEUED
        self.created_at = datetime.now()
        self.result: Optional[Dict[str, Any]] = None # Здесь будет путь к файлу
        self.error: Optional[str] = None
        self.message: str = "Initialized"

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}

    def create_task(self, task_type: str) -> Task:
        task = Task(task_type)
        self.tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, status: TaskStatus, message: str = None, result: Any = None, error: str = None):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = status
            if message: task.message = message
            if result: task.result = result
            if error: task.error = error

# Глобальный инстанс
task_manager = TaskManager()