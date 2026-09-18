# LangGraph-base Tax Document Intake & Classification Assistant

A LangGraph-powered assistant for individual tax preparers: upload a client's
tax documents (W-2s, 1099s, K-1s, bank statements) one at a time as they
trickle in during tax season, and it classifies each one, extracts the real
IRS box values, cross-checks it against what that client's return should
have this year, and pauses for a preparer to confirm or correct everything
before it's added to the client's organizer.

Part of a tutorial series built to demonstrate production-shaped LangGraph
applications; see the sibling repos
[`langgraph-tutorial-01-research-report-assistant`](../langgraph-tutorial-01-research-report-assistant)
and
[`langgraph-tutorial-02-invoice-audit-reconciliation`](../langgraph-tutorial-02-invoice-audit-reconciliation)
for the same architectural pattern applied to other domains.

## What it does

1. **Ingest** -- extracts text from an uploaded PDF (`pdfplumber`), or
   base64-encodes an uploaded image for vision-LLM extraction.
2. **Classify** -- an LLM call classifies the document as `W-2`, `1099-NEC`,
   `1099-INT`, `1099-DIV`, `K-1`, `bank-statement`, or `other-unknown`, with
   a confidence score.
3. **Extract fields** -- routed (via a LangGraph conditional edge) to one of
   seven type-specific extraction nodes, each using the pydantic schema and
   prompt that match that form's real box layout (a W-2's box 1 wages has
   nothing in common with a K-1's box 1 ordinary business income, so this is
   a genuine conditional-routing case, not one generic "extract" step).
4. **Cross-check** (deterministic, no LLM) -- compares the newly extracted
   document against the client's expected-documents checklist and every
   document already on file for them: flags **missing** expected documents,
   **duplicate** re-uploads (same doc type + same employer/payer/EIN),
   **unexpected** documents not on the checklist, and **inconsistent** data
   (bad SSN/EIN formatting, negative box amounts, a tax year that doesn't
   match the client's return).
5. **Review** (`interrupt()`) -- pauses the graph and hands the
   classification, extracted fields, and cross-check flags to a preparer to
   **Approve**, **Correct-and-Approve**, or **Reject**.
6. **Finalize** -- on approval, adds the document to the client's organizer
   record in Postgres and recomputes that client's overall completeness
   (`documents_received` / `documents_expected` / `complete` \|
   `incomplete`).

### Architecture

```mermaid
flowchart TD
    START([START]) --> ingest[ingest]
    ingest --> classify[classify]
    classify -->|W-2| exW2[extract_w2]
    classify -->|1099-NEC| exNEC[extract_1099nec]
    classify -->|1099-INT| exINT[extract_1099int]
    classify -->|1099-DIV| exDIV[extract_1099div]
    classify -->|K-1| exK1[extract_k1]
    classify -->|bank-statement| exBank[extract_bank_statement]
    classify -->|other-unknown| exOther[extract_other]
    exW2 --> crossCheck[cross_check]
    exNEC --> crossCheck
    exINT --> crossCheck
    exDIV --> crossCheck
    exK1 --> crossCheck
    exBank --> crossCheck
    exOther --> crossCheck
    crossCheck --> review{{"review\n(interrupt --\nwaits for preparer)"}}
    review -->|approve / correct / reject| finalize[finalize]
    finalize --> END([END])

    style review fill:#fef3c7,stroke:#b45309,stroke-width:2px
    style crossCheck fill:#e0f2fe,stroke:#0369a1,stroke-width:1px
```

Every node's output, and the full checklist-vs-received cross-check, is
persisted to Postgres via LangGraph's `AsyncPostgresSaver` checkpointer as
the graph runs -- see [Why durable checkpointing matters here](#why-durable-checkpointing--human-review-matter-here) below.

## Sample documents: real IRS forms vs. synthetic recreations

This repo ships **synthetic recreations** of the IRS forms (W-2, 1099-NEC,
1099-INT, 1099-DIV, Schedule K-1), generated with `reportlab`, using the
*real* IRS box numbers and labels but our own simplified visual layout --
not the actual government-published PDFs. See
[`sample-data/README.md`](./sample-data/README.md) for the full rationale
and a complete manifest of what's included. Everything is fictitious: made-up
people, employers, banks, SSNs/EINs, and amounts.

**Zero-setup demo:** two fictitious clients are pre-seeded with several
already-processed documents so the Client Organizer page has real content
immediately:
- **Jordan Ellis** (tax year 2025) -- W-2 job + freelance 1099-NEC income +
  a savings account -- all three expected documents received, shown
  **complete**.
- **Morgan Alvarez** (tax year 2025) -- changed jobs mid-year (two expected
  W-2s), plus a family K-1 and a brokerage 1099-DIV -- only 3 of 4 expected
  documents received (the second W-2 was never provided), shown
  **incomplete** with a missing-document warning. A rejected duplicate
  re-upload of the first W-2 is also seeded, to show the duplicate-document
  catch.

From the Upload & Process page you can also run any of the 7 bundled sample
PDFs against either client yourself to watch the graph execute live.

## Why durable checkpointing + human review matter here

Real tax-season pain points this addresses:

- **Manual document sorting.** A preparer's inbox during tax season is a
  pile of PDFs and photographed forms with no consistent naming; someone has
  to open each one, figure out what it is, and re-key the relevant numbers
  into tax software by hand.
- **Tracking what's still missing.** As a client's documents trickle in over
  *weeks* (a W-2 in late January, a brokerage 1099 in mid-February, a K-1
  that doesn't show up until March), someone has to remember what that
  client's situation implies they should still be waiting on.
- **Data entry errors have real financial/compliance consequences.** A
  mistyped SSN, a missed duplicate 1099, or wages transposed into the wrong
  box isn't a cosmetic bug here -- it can mean an inaccurate return filed
  with the IRS. That is exactly why **nothing in this graph auto-posts**:
  `review`'s `interrupt()` means every classification and every extracted
  box value is shown to a preparer, who can correct it before it ever
  reaches the client's organizer.
- **Intake spans the whole season, not one sitting.** A client's document
  set isn't complete in one upload session -- it accumulates over the entire
  filing season. That's why this graph's state is checkpointed to Postgres
  after every node (`AsyncPostgresSaver`) rather than kept in memory: a
  document paused at `review` can sit there for days or weeks while more of
  that client's documents arrive and get processed independently, the
  backend process can restart entirely, and the preparer can still resume
  exactly where they left off on each one (`tests/live/test_live_smoke.py`
  proves this by tearing down the checkpointer and building a brand new one
  against the same thread mid-run).

## Repo structure

```
backend/            FastAPI + LangGraph app (Python 3.11+)
  app/
    graph/           LangGraph state, nodes, extraction schemas, graph assembly
    tools/           document_ingest.py (PDF/image), organizer.py (cross-check + completeness)
    prompts/         Postgres-backed prompt registry + seed_prompts.py
    api/routers/     clients.py, documents.py (REST + SSE)
    db/              SQLAlchemy models, Alembic migrations, checkpointer wiring
  scripts/           seed_clients.py, seed_examples.py
  tests/             mocked pytest suite + tests/live/test_live_smoke.py (real OpenAI + Postgres)
frontend/            Vite + React 18 + TypeScript + Tailwind + TanStack Query + reactflow
sample-data/         synthetic W-2/1099/K-1/bank-statement PDFs + organizer checklists (JSON)
docker-compose.yml   postgres + backend + frontend
.github/workflows/   CI: backend pytest (mocked) + frontend typecheck/build/vitest
```

## Prompt registry

Every LLM call's prompt template lives in the Postgres `prompts` table, not
hardcoded in Python: `classify_document_text` / `classify_document_vision`,
and one `extract_{type}_text` / `extract_{type}_vision` pair per document
type (`w2`, `1099nec`, `1099int`, `1099div`, `k1`, `bank_statement`, `other`).
`backend/app/prompts/seed_prompts.py` seeds version 1 of each; only one
version per name is `is_active` at a time, so you can add a new version and
flip it active (`app.prompts.registry.add_prompt_version`) to iterate on
prompt wording without a code deploy.

## Setup & run

### Docker Compose (recommended)

```bash
cp .env.example .env   # fill in OPENAI_API_KEY (or ANTHROPIC_API_KEY + LLM_PROVIDER=anthropic)
docker compose build
docker compose up
```

- Frontend: http://localhost:8080
- Backend API: http://localhost:8000 (docs at `/docs`)
- Postgres: localhost:5432

The backend's entrypoint runs Alembic migrations, seeds the prompt registry,
loads the two fictitious clients' checklists, and seeds their example
documents automatically on first boot -- no manual setup needed.

### Local development (without Docker)

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# start a local Postgres however you like, e.g.:
docker run -d --name tax_intake_pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=tax_intake -p 5432:5432 postgres:16-alpine
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tax_intake
export OPENAI_API_KEY=sk-...
alembic upgrade head
python -m app.prompts.seed_prompts
python -m scripts.seed_clients
python -m scripts.seed_examples
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, expects the backend on http://localhost:8000
```

### Tests

```bash
cd backend
pytest -v                              # mocked suite, no API key/DB needed
pytest -m live tests/live/test_live_smoke.py -v -s   # real OpenAI + real Postgres, see below

cd ../frontend
npm run typecheck
npm run build
npm run test
```

The live smoke test requires a real `OPENAI_API_KEY` and a reachable
Postgres (`DATABASE_URL`); it ingests the real sample W-2 end to end through
`review`, tears down and rebuilds the checkpointer to simulate a process
restart, resumes the same thread, and confirms it reaches `finalize` and is
added to the organizer. It makes exactly two `gpt-4o-mini` calls
(classification + extraction).

## License

MIT License, Copyright (c) 2026 Emmanuel Oyekanlu. See [LICENSE](./LICENSE).
