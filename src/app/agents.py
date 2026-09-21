import os
from dotenv import load_dotenv
import anthropic
import json
from groq import Groq


load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


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

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = response.choices[0].message.content.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"category": "general", "confidence": 0.0, "reasoning": "Failed to parse model response"}


def extract_fields(document_text: str, doc_type: str) -> dict:
    prompt = f"""Extract these 7 fields from this {doc_type} shipping document.
        Field labels can vary between documents (e.g. "Port of Loading" may also appear as "Load Port" or "POL"). Match by meaning, not exact wording.

        Fields to extract:
        - shipper
        - consignee
        - notify_party
        - port_of_loading
        - port_of_discharge
        - container_count
        - gross_weight_kg

        Formatting rules:
        - gross_weight_kg: return ONLY the numeric value in kilograms, no units, no commas (e.g. "21577" not "21,577 KG"). If given in another unit, convert to kg.
        - container_count: return the value as it appears (e.g. "1 x 40'HC"), since container type matters.
        - All other fields: reutrn the text as it appears in the document, trimmed of extra whitespace.
        - If a field is genuinely not presnet anywhere in the document, use null.


        Document text:
        {document_text}

        Respond with ONLY valid JSON, no other text, no markdown formatting, using exactly this shape:
        {{
            "shipper": "...", 
            "consignee": "...", 
            "notify_party": "...", 
            "port_of_loading": "...", 
            "port_of_discharge": "...", 
            "container_count": "...", 
            "gross_weight_kg": "...", "confidence": 0.0_to_1.0}}

        If a field cannot be found in the document, use null for that field's value."""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    raw_text = response.choices[0].message.content.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "failed to parse", "confidence": 0.0}
