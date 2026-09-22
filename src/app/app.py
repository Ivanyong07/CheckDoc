import re
from fastapi import FastAPI, HTTPException, Depends
import uvicorn
import uuid
from sqlalchemy.future import select
import time
import asyncio

from schemas import EmailIn, EmailOut
from models import Email, Comparison
from db import get_async_session
from agents import (classify_email, extract_fields, compare_documents)

from sqlalchemy.ext.asyncio import AsyncSession
from data.loader import Inbox
import sys
from fastapi.middleware.cors import CORSMiddleware
sys.path.append("src/append/data")

app = FastAPI()
inbox = Inbox("data")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://doccheck.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            await asyncio.sleep(1)  # wait for 1s

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
            bl_result = extract_fields(bl_text, "BL")
            break
        except Exception as e:
            if attempt == max_retries:
                raise HTTPException(
                    500, f"Extraction failed after {max_retries+1} attempts: {str(e)}")
            await asyncio.sleep(1)

    if "error" in si_result or "error" in bl_result:
        raise HTTPException(
            500, "Extraction returned invalid data - not saved")

    existing = await session.execute(select(Comparison).where(Comparison.email_id == id))
    comparison = existing.scalar_one_or_none()

    if comparison:
        comparison.si_fields = si_result
        comparison.bl_fields = bl_result
        comparison.mismatches = None
        comparison.result_summary = None
    else:
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
async def compare(
    id: str,
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(
        select(Comparison).where(
            Comparison.email_id == id
        )
    )

    comparison = result.scalar_one_or_none()

    if not comparison:
        raise HTTPException(
            404,
            "Run extract first"
        )

    if not comparison.si_fields or not comparison.bl_fields:
        raise HTTPException(
            400,
            "SI or B/L extraction data is missing"
        )

    max_retries = 2
    comparison_result = None

    for attempt in range(max_retries + 1):
        try:
            comparison_result = compare_documents(
                comparison.si_fields,
                comparison.bl_fields
            )
            break

        except Exception as e:
            if attempt == max_retries:
                raise HTTPException(
                    500,
                    f"Comparison failed after {max_retries + 1} attempts: {str(e)}"
                )

            await asyncio.sleep(1)

    mismatches = comparison_result.get(
        "mismatches",
        []
    )

    result_summary = comparison_result.get(
        "result_summary",
        "No comparison summary available"
    )

    needs_review = comparison_result.get(
        "needs_review",
        True
    )

    review_reason = comparison_result.get(
        "review_reason"
    )

    comparison.mismatches = mismatches
    comparison.result_summary = result_summary
    comparison.needs_review = needs_review
    comparison.review_reason = review_reason

    await session.commit()
    await session.refresh(comparison)

    return {
        "mismatches": comparison.mismatches,
        "result_summary": comparison.result_summary,
        "needs_review": comparison.needs_review,
        "review_reason": comparison.review_reason
    }


@app.get("/emails/")
async def get_emails(
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(
        select(Email)
    )

    emails = result.scalars().all()

    response = []

    for email in emails:
        comparison_result = await session.execute(
            select(Comparison).where(
                Comparison.email_id == email.id
            )
        )

        comparison = comparison_result.scalar_one_or_none()

        response.append({
            "id": email.id,
            "subject": email.subject,
            "sender": email.sender,
            "body": email.body,
            "classification": email.classification,
            "confidence": email.confidence,

            # Classification review
            "classification_needs_review": email.needs_review,
            "classification_review_reason": email.review_reason,

            # Document comparison review
            "comparison_needs_review": (
                comparison.needs_review
                if comparison
                else False
            ),
            "comparison_review_reason": (
                comparison.review_reason
                if comparison
                else None
            ),
            "needs_review": (
                email.needs_review
                or (
                    comparison.needs_review
                    if comparison
                    else False
                )
            )
        })

    return response


@app.get("/emails/{id}")
async def show_email_id(id: str, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Email).where(Email.id == id))

    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(404, "Email not found")
    return email


@app.get("/emails/{id}/comparison")
async def show_comparison(
    id: str,
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(
        select(Comparison).where(Comparison.email_id == id)
    )

    comparison = result.scalar_one_or_none()

    if not comparison:
        return None

    return {
        "si_fields": comparison.si_fields,
        "bl_fields": comparison.bl_fields,
        "mismatches": comparison.mismatches or [],
        "result_summary": comparison.result_summary,
        "extraction_confidence": comparison.extraction_confidence,
        "needs_review": comparison.needs_review,
        "review_reason": comparison.review_reason
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
