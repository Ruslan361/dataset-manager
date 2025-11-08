from fastapi import APIRouter
from app.api.v1.endpoints.analysis import api as AnalysisApi
from app.api.v1.endpoints.IO import api as IOApi
from app.api.v1.endpoints.tasks import task_management
router = APIRouter()

router.include_router(AnalysisApi.router, prefix='/analysis')
router.include_router(IOApi.router, prefix='/IO')

