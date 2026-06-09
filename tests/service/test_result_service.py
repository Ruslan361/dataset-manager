import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import select, func
from fastapi import HTTPException
from app.service.IO.result_service import ResultService
from app.models.result import Results

def test_pack_method():
    """Тест приватного метода _pack"""
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
    
    assert unpacked["p1"] == "val1"
    assert unpacked["d1"] == 100
    assert "params" not in unpacked

def test_unpack_method_old_format():
    """Тест распаковки СТАРОГО формата (обратная совместимость)"""
    service = ResultService(db=MagicMock())
    
    old_json = {"just_key": "value", "another": 123}
    
    unpacked = service._unpack(old_json)
    
    assert unpacked == old_json
    assert unpacked["just_key"] == "value"

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
    
    old_result = Results(
        image_id=sample_image.id,
        name_method=method_name,
        result={"old": "data"}
    )
    db_session.add(old_result)
    await db_session.commit()
    
    count_query = select(func.count(Results.id))
    assert (await db_session.execute(count_query)).scalar() == 1
    
    with patch("os.remove") as mock_remove:
        await service.save_structured_result(
            image_id=sample_image.id,
            method_name=method_name,
            params={},
            data={},
            clear_previous=True
        )
    
    results = (await db_session.execute(select(Results))).scalars().all()
    assert len(results) == 1
    assert results[0].id != old_result.id
    assert "params" in results[0].result

@pytest.mark.asyncio
async def test_save_does_not_clear_other_methods(db_session, sample_image):
    """Тест: удаляются результаты ТОЛЬКО указанного метода"""
    service = ResultService(db_session)
    
    other_method_result = Results(
        image_id=sample_image.id,
        name_method="other_method",
        result={}
    )
    db_session.add(other_method_result)
    await db_session.commit()
    
    await service.save_structured_result(
        image_id=sample_image.id,
        method_name="target_method",
        params={},
        data={},
        clear_previous=True
    )
    
    results_count = (await db_session.execute(select(func.count(Results.id)))).scalar()
    assert results_count == 2

@pytest.mark.asyncio
async def test_get_latest_result(db_session, sample_image):
    """Тест получения последнего результата"""
    service = ResultService(db_session)
    method = "sorting_test"
    
    res1 = await service.save_structured_result(
        sample_image.id, method, {"v": 1}, {}, clear_previous=False
    )
    
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
    
    
    service = ResultService(db_session)
    
    with patch.object(db_session, 'add', side_effect=Exception("DB Error")):
        with patch.object(service, 'rollback_db', wraps=service.rollback_db) as mock_rollback:
            
            with pytest.raises(HTTPException) as exc:
                await service.save_structured_result(
                    sample_image.id, "err_test", {}, {}
                )
            
            assert exc.value.status_code == 500
            mock_rollback.assert_called_once()