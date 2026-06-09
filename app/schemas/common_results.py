from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ResourceItem(BaseModel):
    type: str  # например: "image", "csv", "json_file"
    key: str   # ключ для фронтенда, например: "clustered_image"
    path: str  # локальный путь на сервере: "uploads/results/1/file.jpg"
    url: Optional[str] = None

class BaseAnalysisResult(BaseModel):
    params: Dict[str, Any]
    data: Dict[str, Any]
    resources: List[ResourceItem] = []