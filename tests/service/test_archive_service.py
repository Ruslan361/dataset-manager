import pytest
import shutil
import zipfile
import json
import os
from pathlib import Path
from fastapi import UploadFile
from app.service.IO.archive_service import ArchiveService
from app.models.result import Results
from app.core.task_manager import task_manager, TaskStatus

@pytest.mark.asyncio
async def test_archive_service_export_task(db_session, sample_image):
    """
    Тест сервиса: запуск задачи экспорта и проверка результата.
    """
    # 1. Подготовка
    dataset_id = sample_image.dataset_id
    
    # Фейковое изображение на диске
    img_dir = Path(f"uploads/images/{dataset_id}")
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / sample_image.filename
    with open(img_path, "wb") as f:
        f.write(b"test image")
        
    # Результат в БД
    res_entry = Results(
        image_id=sample_image.id,
        name_method="test",
        result={"params": {}, "data": {}, "resources": []}
    )
    db_session.add(res_entry)
    await db_session.commit()
    
    # 2. Запуск задачи
    service = ArchiveService(db_session)
    task = task_manager.create_task("export")
    
    # Вызываем напрямую (без фона, чтобы дождаться в тесте)
    await service.run_export_task(task.task_id, dataset_id)
    
    # 3. Проверка
    assert task.status == TaskStatus.COMPLETED
    assert task.result is not None
    zip_path = Path(task.result["file_path"])
    
    assert zip_path.exists()
    assert zipfile.is_zipfile(zip_path)
    
    # Проверка содержимого архива
    with zipfile.ZipFile(zip_path, 'r') as z:
        namelist = z.namelist()
        assert "manifest.json" in namelist
        assert f"images/{sample_image.filename}" in namelist
    
    # Очистка
    if zip_path.exists():
        os.remove(zip_path)
    shutil.rmtree(img_dir, ignore_errors=True)

@pytest.mark.asyncio
async def test_archive_service_import(db_session):
    """
    Тест сервиса: импорт валидного ZIP-архива.
    """
    service = ArchiveService(db_session)
    
    # 1. Создаем валидный ZIP в памяти
    temp_zip = Path("test_import.zip")
    
    manifest_data = {
        "title": "Test Import",
        "created_at": "2023-01-01",
        "images": [
            {
                "original_filename": "orig.jpg",
                "filename": "img.jpg",
                "results": []
            }
        ]
    }
    
    with zipfile.ZipFile(temp_zip, 'w') as z:
        z.writestr("manifest.json", json.dumps(manifest_data))
        z.writestr("images/img.jpg", b"fake content")
        
    # 2. Вызов импорта
    with open(temp_zip, "rb") as f:
        upload = UploadFile(filename="test.zip", file=f)
        new_dataset = await service.import_dataset(upload)
        
    # 3. Проверка
    assert new_dataset.id is not None
    assert "Test Import" in new_dataset.title
    
    # Проверка создания папок
    assert Path(f"uploads/images/{new_dataset.id}").exists()
    
    # Очистка
    if temp_zip.exists():
        os.remove(temp_zip)
    shutil.rmtree(f"uploads/images/{new_dataset.id}", ignore_errors=True)
    shutil.rmtree(f"uploads/results/{new_dataset.id}", ignore_errors=True)

@pytest.mark.asyncio
async def test_export_task_failed(db_session):
    """Тест обработки ошибок в задаче"""
    service = ArchiveService(db_session)
    task = task_manager.create_task("export")
    
    # Пытаемся экспортировать несуществующий датасет
    await service.run_export_task(task.task_id, 999999)
    
    assert task.status == TaskStatus.FAILED
    assert "not found" in task.error