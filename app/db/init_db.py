from sqlalchemy.ext.asyncio import create_async_engine
from app.db.base import Base
from app.core.config import settings
# Импортируем все модели
from app.models import dataset, image, result

async def init_db():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()