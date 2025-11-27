from sqlalchemy import Column, Integer, String, ForeignKey, JSON, TIMESTAMP, func, event
from sqlalchemy.orm import relationship
from app.db.base import Base
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class Results(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True, index=True)
    name_method = Column(String)
    # Структура JSON теперь ожидается такой:
    # {
    #    "params": { ... },
    #    "data": { ... },
    #    "resources": [ {"type": "image", "path": "uploads/...", "key": "result_img"} ]
    # }
    result = Column(JSON, nullable=False)
    image_id = Column(Integer, ForeignKey("images.id"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Опционально: связь с image, чтобы работали каскады на уровне ORM
    # image = relationship("Image", back_populates="results")

# Обработчик события после удаления записи
@event.listens_for(Results, 'after_delete')
def receive_after_delete(mapper, connection, target):
    """
    Автоматически удаляет файлы, указанные в result['resources'],
    после удаления записи из базы данных.
    """
    result_data = target.result
    
    if not result_data or not isinstance(result_data, dict):
        return

    resources = result_data.get("resources", [])
    
    for resource in resources:
        file_path_str = resource.get("path")
        if file_path_str:
            try:
                file_path = Path(file_path_str)
                if file_path.exists() and file_path.is_file():
                    os.remove(file_path)
                    logger.info(f"Auto-cleanup: Deleted file {file_path}")
            except Exception as e:
                logger.error(f"Auto-cleanup failed for {file_path_str}: {e}")