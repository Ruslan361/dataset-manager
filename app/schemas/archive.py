from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class ResultExportItem(BaseModel):
    name_method: str
    result_data: Dict[str, Any]  # Полный JSON из БД (params, data, resources)
    created_at: str

class ImageExportItem(BaseModel):
    original_filename: str
    filename: str  # Имя файла внутри архива в папке images/
    results: List[ResultExportItem]

class DatasetExportManifest(BaseModel):
    title: str
    description: Optional[str] = None  # Исправлено: добавлено значение по умолчанию
    created_at: str
    images: List[ImageExportItem]
    version: str = "1.0"