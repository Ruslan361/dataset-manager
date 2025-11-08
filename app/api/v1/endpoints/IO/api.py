from fastapi import APIRouter
from app.api.v1.endpoints.IO import create_dataset,\
get_dataset, upload_image, remove_dataset, get_images_from_dataset,\
remove_image, download_image, get_image_info, archive


router = APIRouter()

router.include_router(create_dataset.router, prefix="/dataset", tags=["dataset"])
router.include_router(get_dataset.router, prefix="/dataset", tags=["dataset"])
router.include_router(upload_image.router, prefix="/image", tags=["image"])
router.include_router(remove_dataset.router, prefix="/dataset", tags=["dataset"])
router.include_router(get_images_from_dataset.router, prefix="/dataset", tags=["dataset"])
router.include_router(remove_image.router, prefix="/image", tags=["image"])
router.include_router(download_image.router, prefix="/image", tags=["image"])
router.include_router(get_image_info.router, prefix="/image", tags=["image"])
router.include_router(archive.router, prefix="/archive", tags=["archive"])