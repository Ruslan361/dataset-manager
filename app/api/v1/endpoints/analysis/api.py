from fastapi import APIRouter
from app.api.v1.endpoints.analysis import gaussian_blur
from app.api.v1.endpoints.analysis import calculate_mean_lines
router = APIRouter()

router.include_router(gaussian_blur.router, prefix="/blur", tags=["image"])
router.include_router(calculate_mean_lines.router, prefix="/image", tags=["image"])