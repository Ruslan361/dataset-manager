import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.service.IO.dataset_service import DatasetService

DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="function")
async def db_session():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_and_get_dataset(db_session):
    service = DatasetService(db_session)
    dataset = await service.create_dataset("Test Dataset", "Test description")
    assert dataset.title == "Test Dataset"
    assert dataset.description == "Test description"

    fetched = await service.get_dataset_by_id(dataset.id)
    assert fetched is not None
    assert fetched.title == "Test Dataset"
    assert fetched.description == "Test description"

@pytest.mark.asyncio
async def test_get_datasets_list(db_session):
    service = DatasetService(db_session)
    # Создаем несколько датасетов
    await service.create_dataset("Dataset 1", "Desc 1")
    await service.create_dataset("Dataset 2", "Desc 2")
    await service.create_dataset("Dataset 3", "Desc 3")

    datasets, total = await service.get_datasets_list(
        start=0, limit=2, sort_column=None, order_by=None
    )
    assert total == 3
    assert len(datasets) == 2

@pytest.mark.asyncio
async def test_update_dataset(db_session):
    service = DatasetService(db_session)
    dataset = await service.create_dataset("Old Title", "Old Desc")
    updated = await service.update_dataset(dataset.id, title="New Title", description="New Desc")
    assert updated.title == "New Title"
    assert updated.description == "New Desc"

@pytest.mark.asyncio
async def test_delete_dataset(db_session):
    service = DatasetService(db_session)
    dataset = await service.create_dataset("To Delete", "Desc")
    deleted = await service.delete_dataset(dataset.id)
    assert deleted.id == dataset.id
    # Проверяем, что датасет удалён
    fetched = await service.get_dataset_by_id(dataset.id)
    assert fetched is None