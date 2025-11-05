from pydantic import BaseModel, Field, field_validator
from typing import Optional
import datetime
from enum import Enum

class CreateDatasetForm(BaseModel):
    title: str
    description: Optional[str] = None

class GetDatasetsList(BaseModel):
    start: int = Field(gt=-1)
    end: int = Field(gt=0)

class DatasetResponse(BaseModel):
    id: int
    title: str
    description: str
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True

class ResponseDatasetsList(BaseModel):
    datasets: list[DatasetResponse]


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class DatasetSortField(str, Enum):
    ID = "id"
    NAME = "name"
    DESCRIPTION = "description"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class GetDatasetsList(BaseModel):
    start: int = Field(ge=0, description="Начальная позиция")
    end: int = Field(gt=0, description="Конечная позиция")
    sort_field: Optional[DatasetSortField] = Field(DatasetSortField.CREATED_AT, description="Поле для сортировки")
    sort_order: Optional[SortOrder] = Field(SortOrder.DESC, description="Направление сортировки")
    
    @field_validator('end')
    def end_must_be_greater_than_start(cls, v, info):
        if 'start' in info.data and v <= info.data['start']:
            raise ValueError('end must be greater than start')
        return v