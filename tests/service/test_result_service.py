# tests/test_result_service.py
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import select, func
from fastapi import HTTPException
from app.service.IO.result_service import ResultService
from app.models.result import Results

# --- Unit Tests: Логика упаковки/распаковки ---

def test_pack_method():
    """Тест приватного метода _pack"""
    # Трюк: создаем экземпляр без передачи db, так как для этого теста она не нужна
    # В реальном коде лучше мокать, но BaseService требует db.
    # Проще передать MagicMock() как сессию.
    service = ResultService(db=MagicMock())
    
    params = {"k": 5}
    data = {"mean": 10.5}
    resources = [{"path": "/tmp/1.jpg"}]
    
    packed = service._pack(params, data, resources)
    
    assert packed["params"] == params
    assert packed["data"] == data
    assert packed["resources"] == resources

def test_pack_method_empty_resources():
    service = ResultService(db=MagicMock())
    packed = service._pack({"a": 1}, {"b": 2}, None)
    assert packed["resources"] == []

def test_unpack_method_new_format():
    """Тест распаковки НОВОГО формата"""
    service = ResultService(db=MagicMock())
    
    db_json = {
        "params": {"p1": "val1"},
        "data": {"d1": 100},
        "resources": []
    }
    
    unpacked = service._unpack(db_json)
    
    # Должен объединить params и data
    assert unpacked["p1"] == "val1"
    assert unpacked["d1"] == 100
    assert "params" not in unpacked # Убедимся, что верхний ключ ушел

def test_unpack_method_old_format():
    """Тест распаковки СТАРОГО формата (обратная совместимость)"""
    service = ResultService(db=MagicMock())
    
    old_json = {"just_key": "value", "another": 123}
    
    unpacked = service._unpack(old_json)
    
    assert unpacked == old_json
    assert unpacked["just_key"] == "value"

# --- Integration Tests: Работа с БД ---

@pytest.mark.asyncio
async def test_save_structured_result(db_session, sample_image):
    """Тест сохранения результата в базу"""
    service = ResultService(db_session)
    
    params = {"lines": [1, 2]}
    data = {"values": [0.5, 0.6]}
    method_name = "test_method"
    
    result = await service.save_structured_result(
        image_id=sample_image.id,
        method_name=method_name,
        params=params,
        data=data
    )
    
    assert result.id is not None
    assert result.image_id == sample_image.id
    assert result.result["params"] == params
    assert result.result["data"] == data

@pytest.mark.asyncio
async def test_save_clears_previous_results(db_session, sample_image):
    """Тест: при сохранении с clear_previous=True старые записи удаляются"""
    service = ResultService(db_session)
    method_name = "calc_method"
    
    # 1. Создаем "старую" запись вручную
    old_result = Results(
        image_id=sample_image.id,
        name_method=method_name,
        result={"old": "data"}
    )
    db_session.add(old_result)
    await db_session.commit()
    
    # Проверяем, что она есть
    count_query = select(func.count(Results.id))
    assert (await db_session.execute(count_query)).scalar() == 1
    
    # 2. Сохраняем новую через сервис (с флагом очистки)
    # Важно: мокаем os.remove, чтобы event listener модели не пытался удалить несуществующие файлы
    with patch("os.remove") as mock_remove:
        await service.save_structured_result(
            image_id=sample_image.id,
            method_name=method_name,
            params={},
            data={},
            clear_previous=True
        )
    
    # 3. Проверяем, что в базе все еще 1 запись (старая удалена, новая добавлена)
    results = (await db_session.execute(select(Results))).scalars().all()
    assert len(results) == 1
    assert results[0].id != old_result.id  # ID должен измениться, так как это новая запись
    assert "params" in results[0].result # Это новая структура

@pytest.mark.asyncio
async def test_save_does_not_clear_other_methods(db_session, sample_image):
    """Тест: удаляются результаты ТОЛЬКО указанного метода"""
    service = ResultService(db_session)
    
    # Создаем запись ДРУГОГО метода
    other_method_result = Results(
        image_id=sample_image.id,
        name_method="other_method",
        result={}
    )
    db_session.add(other_method_result)
    await db_session.commit()
    
    # Сохраняем "target_method"
    await service.save_structured_result(
        image_id=sample_image.id,
        method_name="target_method",
        params={},
        data={},
        clear_previous=True
    )
    
    # В базе должно быть 2 записи
    results_count = (await db_session.execute(select(func.count(Results.id)))).scalar()
    assert results_count == 2

@pytest.mark.asyncio
async def test_get_latest_result(db_session, sample_image):
    """Тест получения последнего результата"""
    service = ResultService(db_session)
    method = "sorting_test"
    
    # Создаем первую запись
    res1 = await service.save_structured_result(
        sample_image.id, method, {"v": 1}, {}, clear_previous=False
    )
    
    # Создаем вторую запись (она будет свежее по created_at/id)
    res2 = await service.save_structured_result(
        sample_image.id, method, {"v": 2}, {}, clear_previous=False
    )
    
    latest = await service.get_latest_result(sample_image.id, method)
    assert latest.id == res2.id
    assert latest.result["params"]["v"] == 2

@pytest.mark.asyncio
async def test_get_latest_result_data_unpacked(db_session, sample_image):
    """Тест: метод возвращает сразу распакованные данные"""
    service = ResultService(db_session)
    
    params = {"p": 1}
    data = {"d": 2}
    
    await service.save_structured_result(
        sample_image.id, "unpack_test", params, data
    )
    
    flat_dict = await service.get_latest_result_data(sample_image.id, "unpack_test")
    
    assert flat_dict["p"] == 1
    assert flat_dict["d"] == 2
    assert "params" not in flat_dict

@pytest.mark.asyncio
async def test_rollback_on_error(db_session, sample_image):
    """Тест: при ошибке БД вызывается откат и выбрасывается HTTPException"""
    
    # Создаем прокси объект сессии, чтобы замокать commit
    # Мы не можем просто замокать db_session.commit, так как это асинхронный метод
    # Но мы можем симулировать ошибку внутри сервиса
    
    service = ResultService(db_session)
    
    # Патчим db.add чтобы он вызывал ошибку
    with patch.object(db_session, 'add', side_effect=Exception("DB Error")):
        # Патчим rollback_db, чтобы проверить, что он вызвался
        with patch.object(service, 'rollback_db', wraps=service.rollback_db) as mock_rollback:
            
            with pytest.raises(HTTPException) as exc:
                await service.save_structured_result(
                    sample_image.id, "err_test", {}, {}
                )
            
            assert exc.value.status_code == 500
            mock_rollback.assert_called_once()