from sqlalchemy import Column, Integer, String, ForeignKey, JSON, TIMESTAMP, func
from app.db.base import Base
from sqlalchemy.orm import relationship

class Results(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True, index=True)
    name_method = Column(String)
    result = Column(JSON, nullable=False)
    image_id = Column(Integer, ForeignKey("images.id"))
    created_at = Column(TIMESTAMP, server_default=func.now())