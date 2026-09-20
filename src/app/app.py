from fastapi import FastAPI, HTTPException, Depends
import uvicorn
import uuid
from app.schemas import *
import models
from app.agents import classify_email
from app.models import Email
from sqlalchemy.future import select

app = FastAPI()

# Agent 1 Classifier agent
# Agent 2 Extraction agent
# Agent 3 Normalization agent
# Agent 4 Comparison agent
# Agent 5 Auditor/escalation agent


@app.post("/emails", response_model=EmailOut)
def store_email(email: EmailIn) -> dict:
    email_id = str(uuid.uuid4())
    record = {"id": email_id}
    return Inbox


@app.post("/emails/{id}/classify")
async def classify(id: str, session: AsyncSession = Depends(get_async_session)) -> dict:

    result = await session.execute(select(Email).where(Email.id == id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(404, "Email not found")

    has_attachments = bool(email.si_attachment or email.bl_attachment)

    classification_result = classify_email(
        subject=email.subject,
        body=email.body,
        has_attachments=has_attachments
    )

    email.classification = classification_result["category"]
    email.confidence = classification_result["confidence"]
    email.needs_review = classification_result["confidence"] < 0.7
    email.review_reason = classification_result["reasoning"] if email.needs_review else None

    await session.commit()
    await session.refresh(email)

    return email


@app.post("/emails/{id}/compare")
def compare(id: str) -> dict:
    return Compare


@app.get("/emails/")
def show_email():
    return emails


@app.get("/emails/{id}")
def show_email_id(id: str = uuid):
    return emails
