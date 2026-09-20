from sqlalchemy import Column, String, Float, Boolean, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Email(Base):
    __tablename__ = "emails"

    id = Column(String(36), primary_key=True)
    subject = Column(String(500))
    sender = Column(String(255))
    body = Column(String(5000))
    si_attachment = Column(String(5000), nullable=True)
    bl_attachment = Column(String(5000), nullable=True)
    classification = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    needs_review = Column(Boolean, default=False)
    review_reason = Column(String(500), nullable=True)
    comparison_result = Column(JSON, nullable=True)
