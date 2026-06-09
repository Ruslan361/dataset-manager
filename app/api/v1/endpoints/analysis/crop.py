from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import logging
from pathlib import Path

from app.db.session import get_db, AsyncSessionLocal
from app.service.IO.image_service import ImageService
from app.service.IO.result_service import ResultService
from app.service.computation.crop_service import CropService
from app.core.exceptions import CalculationError
from app.schemas.result import ResultResponse

logger = logging.getLogger(__name__)
router = APIRouter()

class AutoCropRequest(BaseModel):
    image_id: int

class Crop(BaseModel):
    top: int
    bottom: int
    left: int
    right: int

@router.post("/auto-crop", response_model=ResultResponse)
async def auto_crop_image(
    request: AutoCropRequest,
    db: AsyncSession = Depends(get_db)
):
    image_service = ImageService(db)

    image_record = await image_service.get_image_by_id(request.image_id)
    if not image_record:
        raise HTTPException(status_code=404, detail="Image not found")

    image = image_service.load_image_cv2(image_service.get_image_file_path(image_record))
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read image file")

    try:
        top, bottom, left, right = CropService.compute_auto_crop(image)
    except CalculationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ResultResponse(
        success=True,
        message="Image cropped successfully",
        data=Crop(top=top, bottom=bottom, left=left, right=right)
    )

@router.post("/crop-image/{image_id}", response_model=ResultResponse)
async def crop_image(
    image_id: int,
    crop: Crop,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    if crop.bottom <= crop.top or crop.right <= crop.left:
        raise HTTPException(status_code=400, detail="Cropped area is empty")

    async def save_cropped_result():
        async with AsyncSessionLocal() as bg_db:
            await ResultService(bg_db).save_structured_result(
                image_id=image_id,
                method_name="crop",
                params=crop.model_dump(),
                data=None
            )

    background_tasks.add_task(save_cropped_result)

    return ResultResponse(
        success=True,
        message="Image cropped and result saving in background",
        data=None
    )

@router.get("/get-crop/{image_id}", response_model=ResultResponse)
async def get_crop_results(
    image_id: int,
    db: AsyncSession = Depends(get_db)
):
    image_service = ImageService(db)
    result_service = ResultService(db)

    result_record = await result_service.get_latest_result(image_id, "crop")

    if result_record:
        unpacked = result_record.result.get("params", {})
        return ResultResponse(
            success=True,
            message="Crop results retrieved successfully",
            data=Crop(
                top=unpacked.get("top"),
                bottom=unpacked.get("bottom"),
                left=unpacked.get("left"),
                right=unpacked.get("right"),
            )
        )

    image_record = await image_service.get_image_by_id(image_id)
    if not image_record:
        raise HTTPException(status_code=404, detail="Image not found")

    image = image_service.load_image_cv2(image_service.get_image_file_path(image_record))
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read image file")

    try:
        top, bottom, left, right = CropService.compute_auto_crop(image)
    except CalculationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await result_service.save_structured_result(
        image_id=image_id,
        method_name="crop",
        params={"top": top, "bottom": bottom, "left": left, "right": right},
        data=None
    )

    return ResultResponse(
        success=True,
        message="Crop computed automatically (no prior data found)",
        data=Crop(top=top, bottom=bottom, left=left, right=right)
    )

