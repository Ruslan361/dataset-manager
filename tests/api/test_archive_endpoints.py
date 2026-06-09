import pytest
import shutil
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.models.result import Results
from sqlalchemy import select

@pytest.mark.asyncio
async def test_archive_export_import_flow(client, db_session, sample_image):
    """
    Полный тест цикла архивации с использованием Task Manager:
    1. Подготовка: Создаем файлы на диске и запись результата в БД.
    2. Экспорт (POST): Запускаем задачу.
    3. Ожидание: Поллинг статуса задачи.
    4. Скачивание (GET): Получение ZIP.
    5. Импорт (POST): Загрузка ZIP.
    6. Проверка: Новый датасет создан.
    """
    
    dataset_id = sample_image.dataset_id
    image_id = sample_image.id
    
    img_dir = Path(f"uploads/images/{dataset_id}")
    res_dir = Path(f"uploads/results/{dataset_id}")
    img_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)
    
    img_path = img_dir / sample_image.filename
    with open(img_path, "wb") as f:
        f.write(b"fake_image_content")
        
    res_filename = f"{image_id}_res.jpg"
    res_path = res_dir / res_filename
    with open(res_path, "wb") as f:
        f.write(b"fake_result_content")
        
    result_entry = Results(
        image_id=image_id,
        name_method="test_method",
        result={
            "params": {"k": 3},
            "data": {"score": 0.99},
            "resources": [{
                "type": "image", 
                "key": "clustered_image", 
                "path": str(res_path)
            }]
        }
    )
    db_session.add(result_entry)
    await db_session.commit()

    new_dataset_id = None
    
    mock_session_cm = MagicMock()
    
    async def fake_aenter(*args):
        return db_session
        
    async def fake_aexit(*args):
        pass

    mock_session_cm.__aenter__ = fake_aenter
    mock_session_cm.__aexit__ = fake_aexit

    try:
        with patch("app.api.v1.endpoints.IO.archive.AsyncSessionLocal", return_value=mock_session_cm):
            
            response_start = await client.post(f"/IO/archive/export/{dataset_id}")
            assert response_start.status_code == 200
            task_data = response_start.json()
            task_id = task_data["task_id"]
            assert task_data["status"] == "queued"

            max_retries = 20
            for _ in range(max_retries):
                await asyncio.sleep(0.1)
                
                resp_status = await client.get(f"/IO/archive/status/{task_id}")
                status_data = resp_status.json()
                
                if status_data["status"] == "completed":
                    break
                if status_data["status"] == "failed":
                    pytest.fail(f"Export task failed: {status_data['error']}")
            else:
                pytest.fail("Export task timed out")

            response_download = await client.get(f"/IO/archive/download/{task_id}")
            assert response_download.status_code == 200
            assert response_download.headers["content-type"] == "application/zip"
            zip_content = response_download.content
            assert len(zip_content) > 0

        files = {
            "file": ("exported_dataset.zip", zip_content, "application/zip")
        }
        
        response_import = await client.post("/IO/archive/import", files=files)
        assert response_import.status_code == 200
        import_data = response_import.json()
        assert import_data["success"] is True
        
        new_dataset_id = import_data["dataset_id"]
        assert new_dataset_id != dataset_id

        new_img_dir = Path(f"uploads/images/{new_dataset_id}")
        assert new_img_dir.exists()
        assert len(list(new_img_dir.glob("*"))) == 1
        
        new_res_dir = Path(f"uploads/results/{new_dataset_id}")
        assert new_res_dir.exists()
        assert len(list(new_res_dir.glob("*"))) == 1
        
        from app.models.image import Image
        new_image_res = await db_session.execute(
            select(Image).where(Image.dataset_id == new_dataset_id)
        )
        new_image = new_image_res.scalar_one()
        
        new_result_res = await db_session.execute(
            select(Results).where(Results.image_id == new_image.id)
        )
        new_result = new_result_res.scalar_one()
        
        res_path_in_db = new_result.result["resources"][0]["path"]
        assert str(new_dataset_id) in res_path_in_db
        assert Path(res_path_in_db).exists()

    finally:
        if img_dir.exists():
            shutil.rmtree(img_dir)
        if res_dir.exists():
            shutil.rmtree(res_dir)
        if new_dataset_id:
            shutil.rmtree(f"uploads/images/{new_dataset_id}", ignore_errors=True)
            shutil.rmtree(f"uploads/results/{new_dataset_id}", ignore_errors=True)
            
        shutil.rmtree("exports", ignore_errors=True)

@pytest.mark.asyncio
async def test_export_not_found(client):
    """Тест экспорта несуществующего датасета (должен вернуть 404 сразу)"""
    response = await client.post("/IO/archive/export/999999")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_import_bad_file(client):
    """Тест импорта битого файла"""
    files = {"file": ("bad.zip", b"not a zip file", "application/zip")}
    response = await client.post("/IO/archive/import", files=files)
    
    assert response.status_code == 500
    assert "Import failed" in response.json()["detail"]