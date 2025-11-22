from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from src.db.session import Base

class ImageRecord(Base):
    __tablename__ = "image_records"

    id = Column(Integer, primary_key=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    image_name = Column(String, nullable=True)
    #
    additional_text = Column(String, nullable=True)
