import re
from fastapi import FastAPI, HTTPException, Depends
import uvicorn
import uuid
from sqlalchemy.future import select
import time

from schemas import EmailIn, EmailOut
from models import Email, Comparison
from db import get_async_session
from agents import classify_email, extract_fields

from sqlalchemy.ext.asyncio import AsyncSession
from data.loader import Inbox
import sys
sys.path.append("src/append/data")

app = FastAPI()
inbox = Inbox("data")


@app.post("/ingest")  # done
async def store_email(session: AsyncSession = Depends(get_async_session)) -> dict:

    raw_emails = inbox.emails()

    for item in raw_emails:
        si_path = next((a for a in item["attachments"] if "_SI" in a), None)
        bl_path = next((a for a in item["attachments"] if "_BL" in a), None)

        email = Email(
            id=item["email_id"],
            sender=item["from"],
            subject=item["subject"],
            body=item["body"],
            si_attachment=si_path,
            bl_attachment=bl_path,
        )

        session.add(email)

    await session.commit()
    return {"ingested": len(raw_emails)}


@app.post("/emails/{id}/classify", response_model=EmailOut)
async def classify(id: str, session: AsyncSession = Depends(get_async_session)):

    result = await session.execute(select(Email).where(Email.id == id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(404, "Email not found")

    has_attachments = bool(email.si_attachment or email.bl_attachment)

    classification_result = None
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            classification_result = classify_email(
                subject=email.subject,
                body=email.body,
                has_attachments=has_attachments
            )
            break
        except Exception as e:
            if attempt == max_retries:
                raise HTTPException(
                    500, f"Classification failed after {max_retries} attempts: {str(e)}")
            time.sleep(1)  # wait for 1s

    email.classification = classification_result["category"]
    email.confidence = classification_result["confidence"]
    email.needs_review = classification_result["confidence"] < 0.7
    email.review_reason = classification_result["reasoning"] if email.needs_review else None

    await session.commit()
    await session.refresh(email)

    return email

FIELDS = ["shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg"]


@app.post("/extract/{id}")
async def extract_si_and_bl_attachments(id: str, session: AsyncSession = Depends(get_async_session)):

    result = await session.execute(select(Email).where(Email.id == id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(404, "Email not found, can't extract")

    if email.classification != "document_comparison_request":
        raise HTTPException(400, "Not a comparison request")

    if not email.si_attachment or not email.bl_attachment:
        raise HTTPException(400, "Missing SI or BL attachment")

    si_text = inbox.read_text(email.si_attachment)
    bl_text = inbox.read_text(email.bl_attachment)

    si_result, bl_result = None, None
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            si_result = extract_fields(si_text, "SI")
            bl_result = extract_fields(si_text, "BL")
            break
        except Exception as e:
            if attempt == max_retries:
                raise HTTPException(
                    500, f"Extraction failed after {max_retries+1} attempts: {str(e)}")
            time.sleep(1)

    comparison = Comparison(
        email_id=id,
        si_fields=si_result,
        bl_fields=bl_result
    )

    session.add(comparison)
    await session.commit()

    return {"si_fields": si_result, "bl_fields": bl_result}


def normalize_value(value):
    if value is None:
        return None
    value = str(value).strip().lower()
    # \s+ one or more tab, space or new line
    # r means dont disturb the \ symbol
    value = re.sub(r"\s+", " ", value)
    value = value.replace(",", "")
    return value


def extract_number(value):
    if value is None:
        return None

    digits = re.sub(r"[^\d.]", "", str(value))
    return float(digits) if digits else None


@app.post("/emails/{id}/compare")
async def compare(id: str, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Comparison).where(Comparison.email_id == id))

    comparison = result.scalar_one_or_none()

    if not comparison:
        raise HTTPException(404, "Run extract first")

    mismatches = []

    missing_si = [f for f in FIELDS if not comparison.si_fields.get(f)]
    missing_bl = [f for f in FIELDS if not comparison.bl_fields.get(f)]

    if missing_si or missing_bl:
        comparison.needs_review = True
        comparison.review_reason = (
            f"Could not extract : SI missing {missing_si}, BL missing {missing_bl}"
        )

        await session.commit()
        return {
            "mismatches": [],
            "result_summary": "Escalated - incomplete extraction",
            "needs_review": True,
            "review_reason": comparison.review_reason
        }

    si_confidence = comparison.si_fields.get("confidence", 1.0)
    bl_confidence = comparison.bl_fields.get("confidence", 1.0)

    if si_confidence < 0.7 or bl_confidence < 0.7:
        comparison.needs_review = True
        comparison.review_reason = f"Low extraction confidence (SI: {si_confidence}, BL: {bl_confidence})"

    for field in FIELDS:
        si_val = comparison.si_fields.get(field)
        bl_val = comparison.bl_fields.get(field)

        if field in ["gross_weight_kg", "container_count"]:
            if extract_number(si_val) != extract_number(bl_val):
                mismatches.append(
                    {"field": field, "si_value": si_val, "bl_value": bl_val})
        else:
            if normalize_value(si_val) != normalize_value(bl_val):
                mismatches.append(
                    {"field": field, "si_value": si_val, "bl_value": bl_val})

    summary = "No mistatch detected" if not mismatches else f"{len(mismatches)} field(s) mismatched"

    comparison.mismatches = mismatches
    comparison.result_summary = summary
    await session.commit()

    return {"mismatches": mismatches, "result_summary": summary}


@app.get("/emails/")
async def show_email(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Email))
    return result.scalars().all()


@app.get("/emails/{id}")
async def show_email_id(id: str, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Email).where(Email.id == id))

    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(404, "Email not found")
    return email


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
