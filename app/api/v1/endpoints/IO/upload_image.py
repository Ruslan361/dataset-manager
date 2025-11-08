from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.image import ResultResponse, ImageUploadForm
from app.service.IO.image_service import ImageService
from app.service.IO.file_services import FileService
from app.db.session import get_db
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/upload", response_model=ResultResponse)
async def upload_image(
    file: UploadFile = File(...),
    form_data: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Загрузка изображения"""
    image_service = ImageService(db)
    file_path = None
    
    try:
        # Валидация данных загрузки
        upload_form = await _validate_upload_data(file, form_data)

        # Создание директории для сохранения
        upload_dir = FileService.create_upload_directory(upload_form.dataset_id)
        
        # Генерация уникального имени файла
        unique_filename = FileService.generate_unique_filename(file.filename)
        file_path = upload_dir / unique_filename
        
        # Сохранение файла
        await FileService.save_upload_file(file, file_path)
        
        # Создание записи в БД
        image = await image_service.create_image(
            filename=unique_filename,
            original_filename=file.filename,
            dataset_id=upload_form.dataset_id
        )

        return ResultResponse(
            success=True,
            message="Image saved",
            data={"image_id": image.id}
        )
        
    except HTTPException:
        # Если произошла HTTP ошибка, делаем rollback
        if file_path:
            FileService.remove_file(file_path)
        raise
    except Exception as e:
        # Если произошла любая другая ошибка
        logger.error(f"Error uploading image: {str(e)}")
        if file_path:
            FileService.remove_file(file_path)
        raise HTTPException(status_code=500, detail="Error uploading image")

async def _validate_upload_data(file: UploadFile, form_data: str) -> ImageUploadForm:
    """Валидация данных загрузки"""
    try:
        data = json.loads(form_data)
        upload_form = ImageUploadForm(**data)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid form data")
    
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File type not supported.")
    
    # Проверка размера файла (например, максимум 10MB)
    file.file.seek(0, 2)  # Перемещаем курсор в конец файла
    file_size = file.file.tell()
    file.file.seek(0)  # Возвращаем курсор в начало
    
    if file_size > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=413, detail="File too large")
    
    return upload_form
