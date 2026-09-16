"""Graph state schema.

A `TypedDict` (LangGraph's preferred state shape) rather than a Pydantic
model, so partial node returns (`{"doc_type": "..."}`) merge cleanly via
LangGraph's default "last write wins per key" reducer. Only `trace`
accumulates (via an `operator.add` reducer) since every other field is
written exactly once per run (this graph has no revision loops -- a
preparer's correction is applied inline in `review_node`, not by looping
back).

Unlike the invoice/receipt tutorial in this series, `extracted_fields` is
kept as a single nested dict rather than flattened into top-level state
keys: the relevant box numbers differ completely by document type (a W-2's
box 1 wages has nothing in common with a K-1's box 1 ordinary income), so
flattening would either collide keys across types or require one state key
per box across every supported form. `extract_fields_node` picks the
pydantic schema to use based on `doc_type` (see `extraction_schema.py`) and
dumps the result into this one dict.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class CrossCheckFlag(TypedDict):
    code: str
    severity: str  # "info" | "warning" | "error"
    message: str
    details: dict[str, Any]


class TraceEvent(TypedDict):
    node: str
    timestamp: str
    summary: str


class TaxIntakeState(TypedDict, total=False):
    # --- input ---
    file_path: str
    original_filename: str
    client_id: str

    # --- ingest ---
    raw_text: str  # pdfplumber-extracted text (text-layer PDFs)
    image_base64: str  # scanned/photographed documents, base64-encoded
    mime_type: str
    used_vision: bool  # True if this document went through the vision fallback

    # --- classify ---
    doc_type: str  # "W-2" | "1099-NEC" | "1099-INT" | "1099-DIV" | "K-1" | "bank-statement" | "other-unknown"
    classification_confidence: float
    classification_reasoning: str

    # --- extract_fields ---
    extraction_schema_used: str
    extracted_fields: dict[str, Any]

    # --- cross_check (deterministic) ---
    cross_check_flags: list[CrossCheckFlag]

    # --- review (human-in-the-loop) ---
    human_decision: str  # "approve" | "correct" | "reject" | ""
    human_feedback: str
    corrected_fields: dict[str, Any]

    # --- finalize ---
    final_status: str  # "added_to_organizer" | "corrected_and_added" | "rejected"
    status: str  # mirrors app.db.models.Document.status

    # --- observability (appended to, not replaced) ---
    trace: Annotated[list[TraceEvent], operator.add]
