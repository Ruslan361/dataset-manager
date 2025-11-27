import pytest
import numpy as np
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from app.models.result import Results
from sqlalchemy import select

# --- Тесты Эндпоинтов ---

@pytest.mark.asyncio
async def test_kmeans_start_success(client, sample_image):
    """Тест запуска задачи (POST)"""
    
    with patch("app.service.IO.image_service.ImageService.load_image_cv2") as mock_load:
        mock_load.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        
        payload = {
            "nclusters": 2,
            "colors": [[255, 0, 0], [0, 255, 0]]
        }
        
        response = await client.post(f"/kmeans/kmeans/{sample_image.id}", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert "result_id" in data
        assert data["success"] is True

@pytest.mark.asyncio
async def test_kmeans_validation_error(client, sample_image):
    """Тест валидации (кол-во цветов != кол-во кластеров)"""
    payload = {
        "nclusters": 3,
        "colors": [[255, 0, 0]] # Только 1 цвет
    }
    response = await client.post(f"/kmeans/kmeans/{sample_image.id}", json=payload)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_kmeans_get_result_processing(client, db_session, sample_image):
    """Тест получения статуса 'processing'"""
    # Вручную создаем запись в БД
    res = Results(
        image_id=sample_image.id,
        name_method="kmeans",
        result={"status": "processing"}
    )
    db_session.add(res)
    await db_session.commit()
    
    response = await client.get(f"/kmeans/kmeans/{sample_image.id}/result")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert data["has_result_image"] is False

@pytest.mark.asyncio
async def test_kmeans_get_result_completed(client, db_session, sample_image):
    """Тест получения статуса 'completed'"""
    res = Results(
        image_id=sample_image.id,
        name_method="kmeans",
        result={
            "status": "completed",
            "params": {},
            "data": {"compactness": 0.5},
            "resources": [{"key": "clustered_image", "path": "/tmp/fake.jpg"}]
        }
    )
    db_session.add(res)
    await db_session.commit()
    
    # Мокаем os.path.exists
    with patch("os.path.exists", return_value=True):
        response = await client.get(f"/kmeans/kmeans/{sample_image.id}/result")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"]["compactness"] == 0.5
        assert data["has_result_image"] is True


# --- Тест Фоновой Задачи (Integration) ---

@pytest.mark.asyncio
async def test_kmeans_background_task_logic(db_session, sample_image):
    """
    Прямой тест функции run_kmeans_task.
    Проверяет, что задача обновляет запись в БД с 'processing' на 'completed'.
    """
    from app.api.v1.endpoints.analysis.k_means import run_kmeans_task, KMeansRequest
    from app.service.IO.result_service import ResultService
    
    # 1. Создаем исходную запись "processing"
    service = ResultService(db_session)
    pending = await service.create_pending_result(
        sample_image.id, "kmeans", {}, clear_previous=True
    )
    
    # 2. Подготовка моков
    # Нам нужно, чтобы run_kmeans_task использовала НАШУ тестовую сессию,
    # а не создавала новую через AsyncSessionLocal.
    
    # Создаем AsyncContextManager, который возвращает нашу сессию
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__.return_value = db_session
    mock_session_cm.__aexit__.return_value = None
    
    # Данные для задачи
    params = KMeansRequest(nclusters=2, colors=[(0,0,0), (255,255,255)])
    fake_image = np.zeros((10, 10, 3), dtype=np.uint8)
    
    # 3. Запуск задачи (с патчами)
    with patch("app.api.v1.endpoints.analysis.k_means.AsyncSessionLocal", return_value=mock_session_cm), \
         patch("app.service.computation.cluster_service.ClusterService.apply_kmeans") as mock_calc, \
         patch("cv2.imwrite") as mock_write, \
         patch("asyncio.get_running_loop") as mock_loop:
             
        # Настройка execute в loop (чтобы не запускать реальные потоки)
        # loop.run_in_executor(executor, func, *args) -> просто вызываем func(*args)
        async def fake_run_in_executor(executor, func, *args):
            return func(*args)
            
        mock_loop.return_value.run_in_executor = fake_run_in_executor
        
        # Мок результата вычислений
        mock_calc.return_value = {
            "result_data": {
                "centers_sorted": [[0], [255]],
                "compactness": 0.1,
                "processed_pixels": 100
            },
            "colored_image": fake_image
        }

        # ВЫЗОВ
        await run_kmeans_task(
            result_id=pending.id,
            image_id=sample_image.id,
            params=params,
            bgr_image=fake_image,
            dataset_id=sample_image.dataset_id
        )
        
        # 4. Проверка
        # Обновляем запись из БД
        await db_session.refresh(pending)
        
        # Проверяем, что статус изменился
        unpacked = service._unpack(pending.result)
        assert unpacked["status"] == "completed"
        assert unpacked["compactness"] == 0.1
        
        # Проверяем, что cv2.imwrite вызывался
        mock_write.assert_called_once()