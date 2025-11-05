import aiofiles
import uuid
import shutil
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, UploadFile
import logging

logger = logging.getLogger(__name__)

class FileService:
    """Сервис для работы с файлами"""
    
    @staticmethod
    def generate_unique_filename(original_filename: str) -> str:
        """Генерация уникального имени файла"""
        file_extension = Path(original_filename).suffix
        return f"{uuid.uuid4()}{file_extension}"
    
    @staticmethod
    def create_upload_directory(dataset_id: int) -> Path:
        """Создание директории для загрузки"""
        upload_dir = Path(f"uploads/images/{dataset_id}")
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir
    
    @staticmethod
    async def save_upload_file(file: UploadFile, file_path: Path) -> None:
        """Сохранение загруженного файла"""
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            logger.info(f"File saved: {file_path}")
        except Exception as e:
            logger.error(f"Error saving file {file_path}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error saving file")
    
    @staticmethod
    def remove_file(file_path: Path) -> bool:
        """Удаление файла"""
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")
                return True
            else:
                logger.warning(f"File not found: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            return False
    
    @staticmethod
    def remove_directory(dir_path: Path) -> bool:
        """Удаление директории со всем содержимым"""
        try:
            if dir_path.exists() and dir_path.is_dir():
                shutil.rmtree(dir_path)
                logger.info(f"Deleted directory: {dir_path}")
                return True
            else:
                logger.warning(f"Directory not found: {dir_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting directory {dir_path}: {str(e)}")
            return False