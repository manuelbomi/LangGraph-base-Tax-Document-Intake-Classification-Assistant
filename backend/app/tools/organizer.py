"""Real (non-stub, deterministic) cross-checking of a newly extracted
document against a client's expected-documents checklist and their
previously received documents, plus the organizer completeness recompute
that runs after every `finalize`.

This is the module that turns a pile of individually-classified documents
into an actual "tax organizer": it answers the three questions a preparer
otherwise has to track by hand across a whole tax season --
  1. Is anything on the checklist still missing?
  2. Did this client's documents already include this exact W-2/1099/K-1
     (same counterparty), i.e. is this an accidental re-upload?
  3. Does this document look wrong on its face (bad SSN/EIN format,
     negative wages, a tax year that doesn't match the client's return)?

Matching strategy (intentionally simple and inspectable, no LLM call):
  - Counterparty names (employer/payer/partnership/bank) are compared with
    `difflib.SequenceMatcher` on a normalized (lowercased, punctuation-
    stripped, common-suffix-agnostic) form -- good enough to survive minor
    formatting differences ("Cascade Retail Group" vs "Cascade Retail
    Group, Inc.") without pulling in a fuzzy-matching dependency.
  - A checklist item is "received" if some received document of the same
    `doc_type` has a counterparty name similarity at/above the configured
    threshold.
  - A duplicate is a second RECEIVED document with the same `doc_type` and
    the same counterparty (by name similarity OR an exact tax-id match).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Client, Document
from app.db.session import SessionLocal
from app.graph.extraction_schema import COUNTERPARTY_FIELDS

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_COMMON_SUFFIXES = re.compile(r"\b(inc|llc|corp|co|company|ltd)\b")

_SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_EIN_RE = re.compile(r"^\d{2}-\d{7}$")


def normalize_name(name: str) -> str:
    normalized = _NORMALIZE_RE.sub(" ", (name or "").lower()).strip()
    normalized = _COMMON_SUFFIXES.sub("", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def get_counterparty(doc_type: str, extracted_fields: dict) -> tuple[str, str]:
    """Return (counterparty_name, tax_id) using the field names that apply
    to this `doc_type` (see `extraction_schema.COUNTERPARTY_FIELDS`)."""
    name_field, id_field = COUNTERPARTY_FIELDS.get(doc_type, ("", ""))
    name = str(extracted_fields.get(name_field, "") or "") if name_field else ""
    tax_id = str(extracted_fields.get(id_field, "") or "") if id_field else ""
    return name, tax_id


@dataclass
class ReceivedDoc:
    id: str
    doc_type: str
    counterparty_name: str
    counterparty_id: str


def _received_documents(client_id: str, *, exclude_document_id: str | None = None) -> list[ReceivedDoc]:
    """All of this client's previously *finalized* documents (i.e. ones a
    preparer has already reviewed and added to the organizer) -- documents
    that are still `pending`/`running`/`awaiting_human` don't count yet."""
    with SessionLocal() as db:
        rows = db.execute(
            select(Document).where(
                Document.client_id == client_id,
                Document.status == "completed",
            )
        ).scalars().all()

    out: list[ReceivedDoc] = []
    for row in rows:
        if exclude_document_id and row.id == exclude_document_id:
            continue
        name, tax_id = get_counterparty(row.doc_type, row.extracted_fields or {})
        out.append(ReceivedDoc(id=row.id, doc_type=row.doc_type, counterparty_name=name, counterparty_id=tax_id))
    return out


def _matches_expected_item(received: ReceivedDoc, expected: dict, threshold: float) -> bool:
    if received.doc_type != expected.get("doc_type"):
        return False
    expected_name = expected.get("counterparty_name", "")
    if not expected_name:
        return True
    return name_similarity(received.counterparty_name, expected_name) >= threshold


def cross_check_document(
    client_id: str,
    doc_type: str,
    extracted_fields: dict,
    *,
    exclude_document_id: str | None = None,
) -> list[dict]:
    """Deterministic cross-check of one newly extracted document against
    the client's checklist and previously received documents. Returns a
    list of flag dicts: `{code, severity, message, details}`."""
    settings = get_settings()
    threshold = settings.counterparty_match_threshold
    flags: list[dict] = []

    with SessionLocal() as db:
        client = db.get(Client, client_id)
    if client is None:
        return [
            {
                "code": "unknown_client",
                "severity": "error",
                "message": f"Client {client_id!r} was not found.",
                "details": {},
            }
        ]

    counterparty_name, counterparty_id = get_counterparty(doc_type, extracted_fields)
    received = _received_documents(client_id, exclude_document_id=exclude_document_id)
    expected_list: list[dict] = client.expected_documents or []

    # --- 1. duplicate detection ------------------------------------------
    duplicates = [
        r
        for r in received
        if r.doc_type == doc_type
        and (
            (counterparty_id and r.counterparty_id and counterparty_id == r.counterparty_id)
            or name_similarity(r.counterparty_name, counterparty_name) >= threshold
        )
    ]
    if duplicates:
        flags.append(
            {
                "code": "duplicate_document",
                "severity": "error",
                "message": (
                    f"This looks like a duplicate: {client.name} already has a {doc_type} "
                    f"on file from {counterparty_name or 'the same counterparty'} "
                    f"(document id(s): {', '.join(d.id for d in duplicates)})."
                ),
                "details": {"duplicate_document_ids": [d.id for d in duplicates]},
            }
        )

    # --- 2. unexpected document -------------------------------------------
    is_expected = any(
        e.get("doc_type") == doc_type
        and (not e.get("counterparty_name") or name_similarity(counterparty_name, e["counterparty_name"]) >= threshold)
        for e in expected_list
    )
    if not is_expected and expected_list:
        flags.append(
            {
                "code": "unexpected_document",
                "severity": "info",
                "message": (
                    f"{doc_type} from {counterparty_name or 'this counterparty'} was not on "
                    f"{client.name}'s expected-documents checklist for {client.tax_year}. It may "
                    "still be useful supplementary information, but confirm it before filing."
                ),
                "details": {},
            }
        )

    # --- 3. still-missing expected documents (including this one) --------
    all_received_including_this = received + [
        ReceivedDoc(id="__current__", doc_type=doc_type, counterparty_name=counterparty_name, counterparty_id=counterparty_id)
    ]
    for expected in expected_list:
        satisfied = any(_matches_expected_item(r, expected, threshold) for r in all_received_including_this)
        if not satisfied:
            flags.append(
                {
                    "code": "missing_expected_document",
                    "severity": "warning",
                    "message": (
                        f"Still missing: {expected.get('doc_type')} from "
                        f"{expected.get('counterparty_name', 'an unspecified counterparty')} "
                        f"({client.name}, tax year {client.tax_year})."
                    ),
                    "details": {"expected": expected},
                }
            )

    # --- 4. sanity checks on the extracted data ---------------------------
    for key, value in extracted_fields.items():
        if "ssn" in key.lower() and value:
            if not _SSN_RE.match(str(value)):
                flags.append(
                    {
                        "code": "invalid_ssn_format",
                        "severity": "warning",
                        "message": f"Field '{key}' value {value!r} doesn't look like a valid SSN (XXX-XX-XXXX).",
                        "details": {"field": key},
                    }
                )
        if "ein" in key.lower() and value:
            if not _EIN_RE.match(str(value)):
                flags.append(
                    {
                        "code": "invalid_ein_format",
                        "severity": "warning",
                        "message": f"Field '{key}' value {value!r} doesn't look like a valid EIN (XX-XXXXXXX).",
                        "details": {"field": key},
                    }
                )
        if key.startswith("box") and isinstance(value, (int, float)) and value < 0:
            flags.append(
                {
                    "code": "negative_amount",
                    "severity": "error",
                    "message": f"Field '{key}' is negative ({value}), which is not plausible for this box.",
                    "details": {"field": key, "value": value},
                }
            )

    tax_year = extracted_fields.get("tax_year")
    if tax_year is not None and int(tax_year) != client.tax_year:
        flags.append(
            {
                "code": "tax_year_mismatch",
                "severity": "error",
                "message": (
                    f"Document tax year {tax_year} does not match {client.name}'s tax year "
                    f"{client.tax_year}. Confirm this document belongs in this client's organizer."
                ),
                "details": {"document_tax_year": tax_year, "client_tax_year": client.tax_year},
            }
        )

    return flags


def recompute_client_completeness(
    client_id: str, *, extra_received: list[ReceivedDoc] | None = None
) -> dict:
    """Recompute `documents_expected` / `documents_received` /
    `completeness_status` for a client, based on which checklist items are
    satisfied by that client's finalized (`status == "completed"`)
    documents.

    `extra_received` lets `finalize_node` count the document it is *in the
    process of* finalizing before the API layer has persisted its Document
    row as `status == "completed"` (that write happens just after the graph
    run returns -- see `app/api/routers/documents.py`), so the organizer
    reflects the just-approved document immediately rather than one request
    later.
    """
    settings = get_settings()
    threshold = settings.counterparty_match_threshold

    with SessionLocal() as db:
        client = db.get(Client, client_id)
        if client is None:
            return {}

        received = _received_documents(client_id) + list(extra_received or [])
        expected_list: list[dict] = client.expected_documents or []
        received_count = sum(
            1
            for expected in expected_list
            if any(_matches_expected_item(r, expected, threshold) for r in received)
        )

        client.documents_expected = len(expected_list)
        client.documents_received = received_count
        client.completeness_status = "complete" if received_count >= len(expected_list) else "incomplete"
        db.commit()
        return {
            "documents_expected": client.documents_expected,
            "documents_received": client.documents_received,
            "completeness_status": client.completeness_status,
        }
