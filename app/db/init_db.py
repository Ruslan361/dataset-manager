from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from app.db.base import Base
from app.db.session import AsyncSessionLocal
from app.core.config import settings
# Импортируем все модели
from app.models import dataset, image, result
from app.models.result import Results
import logging

logger = logging.getLogger(__name__)

async def init_db():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

async def cleanup_stale_processing_results():
    """Переводит все записи со статусом 'processing' в 'failed' при старте.
    Такие записи остаются если сервер упал во время обработки задачи."""
    async with AsyncSessionLocal() as session:
        query = select(Results).where(
            Results.result["data"]["status"].as_string() == "processing"
        )
        res = await session.execute(query)
        stale = res.scalars().all()

        if not stale:
            return

        for record in stale:
            current = record.result or {}
            params = current.get("params", {})
            record.result = {
                "params": params,
                "data": {"status": "failed", "error": "Server restarted while task was processing"},
                "resources": []
            }

        await session.commit()
        logger.info(f"Startup cleanup: marked {len(stale)} stale processing result(s) as failed")