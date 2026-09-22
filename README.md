# CheckDoc — Shipping Document Verification

Built for the Averis x Monash Hackathon 2026.

An AI-assisted pipeline that reads a mixed shipping-operations inbox, classifies each
email, and — for document-comparison requests — extracts the Shipping Instruction (SI)
and Bill of Lading (BL) attachments, compares them field by field, and flags mismatches
before the BL is finalized.

## Problem

A shipping team's inbox mixes document-comparison requests, new SI requests, invoice
queries, general messages, and spam. Staff currently read every email manually to
figure out what it is, and manually cross-check SI vs BL documents across 7 fields —
slow, repetitive, and error-prone. Label wording also varies between documents (e.g.
"Port of Loading" vs "Load Port"), which makes naive text comparison unreliable.

## What it does

1. **Classify** — every email is sorted into one of 5 categories: document comparison
   request, new SI request, invoice query, general, or spam. Returns a category, a
   confidence score, and a short reasoning string.
2. **Extract** — for comparison requests only, the SI and BL attachments are read and
   7 fields are pulled from each: shipper, consignee, notify party, port of loading,
   port of discharge, container count, gross weight (kg). The model is prompted to
   reason about what *role* each piece of text plays (e.g. "who is the receiving
   party") rather than pattern-matching a fixed list of labels, since real documents
   use inconsistent wording (e.g. "Port of Loading" vs "Load Port", or "Consignee" vs
   "To the Order of"). Each field's extraction includes a confidence score and, when
   the model had to infer meaning rather than match an obvious label, a short
   explanation.
3. **Compare** — the extracted SI and BL field sets are compared by a dedicated
   comparison agent (`compare_documents`, in `agents.py`), rather than plain
   string/number diffing. This lets the comparison step reason about formatting
   differences (units, casing, punctuation) and genuinely equivalent values the same
   way a human reviewer would, instead of relying only on hardcoded normalization
   rules.
4. **Escalate** — if an attachment is missing, extraction or comparison confidence is
   low, a field can't be found, or the comparison agent itself flags uncertainty, the
   email/comparison is marked `needs_review` with a human-readable reason, instead of
   guessing or failing silently. Review flags are tracked separately for the
   classification step and the comparison step, since either stage can independently
   need human input.

## Tech stack

- **Backend:** FastAPI (Python), async SQLAlchemy
- **Database:** MySQL
- **AI:** Groq API (`openai/gpt-oss-120b`) for classification, field extraction, and
  SI vs BL comparison
- **Frontend:** HTML/CSS/JS dashboard (inbox list with classified / unclassified /
  needs-review counts, email detail view, classification and comparison actions,
  live system terminal log). Runs separately from the backend (e.g. via Live Server
  on `http://127.0.0.1:5500`); CORS is enabled on the backend for local development.
- **Dataset access:** provided `loader.py`, reading from the local `data/` bundle

## Project structure

```
app/
├── app.py              # FastAPI app and all endpoints
├── agents.py           # LLM calls: classify_email(), extract_fields()
├── models.py            # SQLAlchemy models: Email, Comparison
├── schemas.py            # Pydantic request/response schemas
├── db.py                # async DB engine + session
├── data/
│   ├── loader.py        # provided dataset loader
│   ├── inbox/            # email JSON records
│   └── attachments/      # SI / BL .txt attachments
├── index.html            # frontend dashboard
├── index.js
├── style.css
└── .env                 # API keys + DB credentials (not committed)
```

## Setup

1. Install dependencies:
   ```
   uv sync
   ```
2. Create a `.env` file:
   ```
   GROQ_API_KEY=your_key_here
   MYSQL_USERNAME=...
   MYSQL_PASSWORD=...
   MYSQL_HOST=localhost
   MYSQL_DATABASE=checkdoc
   ```
3. Create the MySQL database (tables are created automatically on server startup).
4. Run the backend:
   ```
   uv run uvicorn app:app --reload
   ```
5. Open `index.html` in a browser (or serve it) — it talks to the backend at
   `http://localhost:8000`.

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/ingest` | Loads all emails from the dataset into the database |
| POST | `/emails/{id}/classify` | Classifies one email (category, confidence, reasoning) |
| POST | `/emails/classify_all` | Classifies all emails concurrently, with retries and per-email failure isolation |
| POST | `/extract/{id}` | Extracts SI and BL fields for a comparison-request email; re-running overwrites the previous extraction rather than duplicating it |
| POST | `/emails/{id}/compare` | Runs the AI comparison agent on the extracted SI vs BL fields; returns mismatches, a summary, and a review flag/reason |
| GET | `/emails/` | Lists all emails with both classification-stage and comparison-stage review status |
| GET | `/emails/{id}` | Returns one email's full record |
| GET | `/emails/{id}/comparison` | Returns the stored comparison result (extracted fields, mismatches, summary) for one email, if it exists |

## Prompting strategy

Three agents (functions in `agents.py`), each a single LLM call with a narrow,
specific job — not a generic "do everything" prompt:

- **`classify_email`** — sorts an email into one of the 5 categories and returns a
  confidence score plus a short reasoning string, so a low-confidence or ambiguous
  classification can be traced back to *why* the model was unsure.
- **`extract_fields`** — reads one document (SI or BL) at a time and pulls the 7
  target fields. Rather than searching for an exact label list, the prompt describes
  what each field *means* (e.g. "consignee: the party the goods are being shipped to,
  may appear as 'Consignee', 'Consignee (Non-Negotiable)', or 'To the Order of'"),
  so it generalizes to label wording it hasn't seen an explicit synonym for. When the
  model has to infer a field from an unusual label rather than match an obvious one,
  it's instructed to lower that field's confidence and briefly explain why.
- **`compare_documents`** — takes the two already-extracted field sets (SI and BL)
  and determines mismatches, a plain-language summary, and whether the result needs
  human review. Using an agent for this step (rather than only plain string/number
  diffing) lets it recognize values that are equivalent despite different formatting
  or phrasing, and flag genuine ambiguity rather than only exact-match differences.

Every agent call is wrapped in a retry loop (up to 3 attempts, 1s backoff) since LLM
API calls can fail transiently; a failure that survives all retries is recorded as a
review flag on the relevant email/comparison rather than crashing the request.

## Design notes

- **Separate `Email` and `Comparison` tables** — classification data lives on
  `Email`; extraction/comparison data (which only exists for a subset of emails)
  lives in its own `Comparison` table, linked by `email_id`.
- **Re-running extract updates in place** — if extraction is re-run for an email that
  already has a `Comparison` row (e.g. after a prompt fix), the existing row is
  updated rather than a duplicate being inserted, and the stale mismatch/summary is
  cleared so a re-comparison is required before it's trusted again.
- **Retry logic** on all LLM calls (up to 3 attempts) to handle transient API
  failures without giving up immediately; batch classification (`classify_all`)
  additionally isolates failures per-email so one bad email doesn't stop the rest of
  the batch.
- **Confidence-based escalation at every stage** — classification, extraction, and
  comparison each independently track a review flag and reason. `GET /emails/`
  reports classification-stage and comparison-stage review status separately (and
  combined), since an email can need review for either reason independently.

## Known limitations / advanced stage not yet implemented

- Basic stage only: plain-text SI/BL attachments. PDF/Word parsing and OCR for
  scanned documents (advanced stage) are not implemented.
- No automated retry-on-rate-limit backoff tuned to a specific provider's exact
  limits — if the LLM provider's rate limit is hit, calls are retried a fixed
  number of times before escalating.

## Team
Ivan Yong Pak Theng
Ling Yew Cheng