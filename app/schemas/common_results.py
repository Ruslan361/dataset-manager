from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ResourceItem(BaseModel):
    type: str  # например: "image", "csv", "json_file"
    key: str   # ключ для фронтенда, например: "clustered_image"
    path: str  # локальный путь на сервере: "uploads/results/1/file.jpg"
    url: Optional[str] = None # если нужно отдавать статику

class BaseAnalysisResult(BaseModel):
    params: Dict[str, Any]      # Входные параметры (k=3, lines=[...])
    data: Dict[str, Any]        # Числовые результаты (матрицы, средние)
    resources: List[ResourceItem] = [] # Сгенерированные файлы