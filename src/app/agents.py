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
    - spam (uMalaysia.nsolicited, irreleven or junk)

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

        IMPORTANT: Document labels vary a lot and won't always match common terms exactly.
        Don't just search for exact keywords — reason about what ROLE each piece of information plays in the document, then map it to the correct field.

        Field meanings (not exact labels to search for):
        - shipper: the party sending/exporting the goods (may appear as "Shipper", "Exporter", "Shipper/Exporter")
        - consignee: the party the goods are being shipped TO, i.e. the receiving party on record (may appear as "Consignee", "Consignee (Non-Negotiable)", "To the Order of", or even a bank/agent if the shipment is bank-negotiated — but if a distinct "Notify Party" also exists, prefer whoever the document treats as the actual receiving party)
        - notify_party: the party to be notified on arrival (may appear as "Notify", "Notify Party")
        - port_of_loading: where the shipment departs from (may appear as "Port of Loading", "POL", "Load Port")
        - port_of_discharge: where the shipment arrives (may appear as "Port of Discharge", "POD", "Discharge Port")
        - container_count: number and type of containers (may appear as "Container Count", "No. of Containers", "Total Containers")
        - gross_weight_kg: total weight in kg (may appear as "Gross Weight", "Gross Wt")

        If a label is unusual or you're inferring meaning rather than matching an obvious label, lower your confidence score for that field accordingly — don't guess with high confidence.

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
            "gross_weight_kg": "...", 
            "confidence": 0.0_to_1.0,
            "reasoning": "brief explanation of any uncertain fields, or 'all fields clearly labeled' if none"}}

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
