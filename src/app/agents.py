import os
from dotenv import load_dotenv
import anthropic
import json

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def classify_email(subject: str, body: str, has_attachments: bool) -> dict:
    # comparison request
    # new si request
    # invoice query
    # general
    # spam

    prompt = f"""You are classifying emails for a shipping operations inbox.

    Classify this email into EXACTLY one category:
    - document_comparison_request (asking to check/ verify shipping documents, usally has SI and BL attachments)
    - new_si_request (asking to prepare a new shipping instruction)
    - invoice_query (question about an invoice or payment)
    - general (any other legitimate business message)
    - spam (unsolicited, irreleven or junk)

    Email subject: {subject}
    Email body: {body}
    Has attachments: {has_attachments}

    Respond with ONLY valid JSON, nothing else, no markdown formatting:
    {{"category": "one_of_the_five_above", "confidence": 0.0_to_1.0, "reasoning": "one short sentence"}}"""

    response = client.message.create(
        model="claude-sonnet-4-6",
        max_token=200,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = response.content[0].text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"category": "general", "confidence": 0.0, "reasoning": "Failed to parse model response"}


# def extract_fields():
