from pydantic import BaseModel
from typing import Optional, Any

class ResultResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None