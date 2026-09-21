from pydantic import BaseModel
from typing import Optional


class EmailIn(BaseModel):
    subject: str
    sender: str
    body: str
    si_attachment: Optional[str] = None
    bl_attachment: Optional[str] = None


class EmailOut(BaseModel):
    id: str
    subject: str
    sender: str
    classification: Optional[str] = None
    confidence: Optional[float] = None
    needs_review: bool = False
    review_reason: Optional[str] = None

    class Config:
        from_attributes = True


class Comparison(BaseModel):
    email_id: str
    mismatches: list[dict] = []
    result_summary: str = ""
