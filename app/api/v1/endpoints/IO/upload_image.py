from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.image import ResultResponse, ImageUploadForm
from app.models.image import Image
from app.db.session import get_db
import json
import aiofiles
import uuid
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload", response_model=ResultResponse)
async def upload_image(
    file: UploadFile = File(...),
    form_data: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    file_path = None
    
    try:
        upload_form = await validate_upload_data(file, form_data)

        # Создание директории для сохранения
        upload_dir = Path(f"uploads/images/{upload_form.dataset_id}")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Генерация уникального имени файла
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        
        # Сохранение файла
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        logger.info(f"File saved: {file_path}")

        # Создание записи в БД
        image = Image(
            filename=unique_filename,
            original_filename=file.filename,
            dataset_id=upload_form.dataset_id
        )
        db.add(image)
        await db.commit()
        await db.refresh(image)

        return ResultResponse(
            success=True,
            message="Image saved"
        )
        
    except HTTPException:
        # Если произошла HTTP ошибка, делаем rollback
        await rollback_operations(db, file_path)
        raise
    except Exception as e:
        # Если произошла любая другая ошибка
        logger.error(f"Error uploading image: {str(e)}")
        await rollback_operations(db, file_path)
        raise HTTPException(status_code=500, detail="Error uploading image")

async def rollback_operations(db: AsyncSession, file_path: Path = None):
    """Откат операций при ошибке"""
    try:
        # Откат транзакции БД
        await db.rollback()
        logger.info("Database transaction rolled back")
        
        # Удаление файла если он был создан
        if file_path and file_path.exists():
            os.remove(file_path)
            logger.info(f"File removed: {file_path}")
            
    except Exception as rollback_error:
        logger.error(f"Error during rollback: {str(rollback_error)}")

async def validate_upload_data(file: UploadFile, form_data: str) -> ImageUploadForm:
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
