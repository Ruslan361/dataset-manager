from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum

class ImageUploadForm(BaseModel):
    title: str
    dataset_id: int
    description: Optional[str] = None

class ResultResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class ImageSortField(str, Enum):
    ID = "id"
    FILENAME = "filename"
    ORIGINAL_FILENAME = "original_filename"
    DATASET_ID = "dataset_id"

class GetImagesList(BaseModel):
    start: int = Field(ge=0, description="Начальная позиция")
    end: int = Field(gt=0, description="Конечная позиция")
    sort_field: Optional[ImageSortField] = Field(ImageSortField.ID, description="Поле для сортировки")
    sort_order: Optional[SortOrder] = Field(SortOrder.ASC, description="Направление сортировки")
    
    @field_validator('end')
    def end_must_be_greater_than_start(cls, v, info):
        if 'start' in info.data and v <= info.data['start']:
            raise ValueError('end must be greater than start')
        return v

class ImageResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    dataset_id: int
    class Config:
        from_attributes = True 

class ResponseImagesList(BaseModel):
    images: list[ImageResponse]
    total: int
    start: int
    end: int
    dataset_id: int