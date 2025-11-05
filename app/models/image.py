from sqlalchemy import Column, Integer, String, LargeBinary, ForeignKey
from app.db.base import Base
from sqlalchemy.orm import relationship

class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, index=True)
    filename = Column(String, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))