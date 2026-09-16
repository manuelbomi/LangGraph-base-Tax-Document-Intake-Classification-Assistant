"""Pydantic request/response schemas for the REST + SSE API.

Keep these in sync with `frontend/src/api/types.ts` -- that file is a
hand-written TypeScript mirror of this one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentStatus = Literal["pending", "running", "awaiting_human", "completed", "rejected", "error"]
DocType = Literal[
    "W-2", "1099-NEC", "1099-INT", "1099-DIV", "K-1", "bank-statement", "other-unknown", "unknown"
]


class ExpectedDocumentItem(BaseModel):
    doc_type: str
    counterparty_name: str = ""
    notes: str = ""


class ClientSummary(BaseModel):
    id: str
    name: str
    tax_year: int
    documents_expected: int
    documents_received: int
    completeness_status: Literal["complete", "incomplete"]


class ClientDetail(ClientSummary):
    notes: str
    expected_documents: list[ExpectedDocumentItem]
    documents: list["DocumentSummary"]


class ClientListResponse(BaseModel):
    clients: list[ClientSummary]


class SampleDocument(BaseModel):
    id: str
    label: str
    doc_type: DocType
    suggested_client_id: str | None = None


class SamplesResponse(BaseModel):
    samples: list[SampleDocument]


class DocumentCreateResponse(BaseModel):
    id: str
    client_id: str
    status: DocumentStatus
    original_filename: str
    doc_type: DocType


class HumanDecisionRequest(BaseModel):
    decision: Literal["approve", "correct", "reject"]
    feedback: str = ""
    corrected_fields: dict[str, Any] | None = None


class TraceEventOut(BaseModel):
    node: str
    timestamp: datetime
    summary: str


class DocumentSummary(BaseModel):
    id: str
    client_id: str
    original_filename: str
    doc_type: DocType
    classification_confidence: float
    status: DocumentStatus
    final_status: str | None
    # Derived for the organizer table's status badges: true if any
    # cross-check flag is severity warning/error.
    flagged: bool
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    extraction_schema_used: str | None = None
    extracted_fields: dict[str, Any]
    cross_check_flags: list[dict[str, Any]]
    trace: list[TraceEventOut]
    state_snapshot: dict[str, Any]
    error: str | None


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]


ClientDetail.model_rebuild()
