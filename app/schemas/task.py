from pydantic import BaseModel, Field
from typing import Optional, Any, List
from enum import Enum
import datetime

class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    message: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float
    completed: bool

class TaskSummaryResponse(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    message: str = ""
    has_result: bool
    has_error: bool
    created_at: float
    completed: bool

class GetTasksListRequest(BaseModel):
    start: int = Field(ge=0, description="Начальная позиция")
    limit: int = Field(gt=0, le=100, description="Количество задач")
    status_filter: Optional[TaskStatus] = Field(None, description="Фильтр по статусу")

class TasksListResponse(BaseModel):
    tasks: List[TaskSummaryResponse]
    total: int
    start: int
    limit: int

class TaskStatsResponse(BaseModel):
    total: int
    queued: int
    processing: int
    completed: int
    failed: int
    cancelled: int

class ClearTasksRequest(BaseModel):
    only_completed: bool = Field(True, description="Удалять только завершенные задачи")

class ClearTasksResponse(BaseModel):
    success: bool
    message: str
    cleared_count: int