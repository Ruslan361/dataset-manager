from fastapi import APIRouter
from app.api.v1.endpoints.analysis import gaussian_blur
from app.api.v1.endpoints.analysis import calculate_mean_lines
from app.api.v1.endpoints.analysis import k_means
from app.api.v1.endpoints.analysis import crop
router = APIRouter()

router.include_router(gaussian_blur.router, prefix="/manual", tags=["image"])
router.include_router(calculate_mean_lines.router, prefix="/manual", tags=["image"])
router.include_router(k_means.router, prefix="/kmeans", tags=['kmeans'])
router.include_router(crop.router, prefix="/crop", tags=['crop'])   