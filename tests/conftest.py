import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, APIRouter
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 1. Импорт Базы и Моделей
from app.db.base import Base
from app.models.dataset import Dataset
from app.models.image import Image
from app.models.result import Results

# 2. Импорт зависимости
from app.db.session import get_db

# 3. Импорт роутеров
from app.api.v1.endpoints.analysis.calculate_mean_lines import router as mean_lines_router
from app.api.v1.endpoints.analysis.gaussian_blur import router as gaussian_blur_router
from app.api.v1.endpoints.analysis.k_means import router as k_means_router
from app.api.v1.endpoints.IO.archive import router as archive_router

# Используем SQLite в памяти
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Создает изолированную сессию БД для каждого теста."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
def app_overrides(db_session):
    """Фикстура для подмены зависимости get_db."""
    async def override_get_db():
        yield db_session
    return override_get_db


@pytest_asyncio.fixture(scope="function")
async def client(app_overrides):
    """
    Создает тестовый клиент FastAPI.
    """
    app = FastAPI()
    
    # 1. Роутер IO (Archive)
    # ИСПРАВЛЕНО: Добавлен префикс /api/v1, чтобы совпадало с base_url клиента
    app.include_router(archive_router, prefix="/api/v1/IO/archive")
    
    # Роутер IO (общий) - заглушка, если нужен
    io_router = APIRouter()
    app.include_router(io_router, prefix="/api/v1/IO")
    
    # 2. Роутеры Analysis (Manual)
    app.include_router(mean_lines_router, prefix="/api/v1/manual")
    app.include_router(gaussian_blur_router, prefix="/api/v1/manual")
    
    # 3. Роутер K-Means
    app.include_router(k_means_router, prefix="/api/v1/kmeans")

    # --- Переопределение БД ---
    app.dependency_overrides[get_db] = app_overrides

    # --- Настройка Base URL ---
    base_url = "http://test/api/v1"
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url=base_url) as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def sample_image(db_session):
    """Создает тестовый датасет и изображение."""
    dataset = Dataset(title="Test Dataset", description="Test Description")
    db_session.add(dataset)
    await db_session.commit()
    await db_session.refresh(dataset)
    
    image = Image(
        filename="test_image.jpg", 
        original_filename="original.jpg", 
        dataset_id=dataset.id
    )
    db_session.add(image)
    await db_session.commit()
    await db_session.refresh(image)
    
    return image