"""LangGraph node implementations for the Tax Document Intake &
Classification Assistant.

Six real (non-stub) nodes/stages:
  ingest        - extracts raw text (pdfplumber) or base64-encodes an image
                  for vision extraction
  classify      - LLM classifies the document type + confidence
  extract_fields - one node per document type (extract_w2, extract_1099nec,
                  ...), reached via a conditional edge keyed on the
                  classification -- each uses the pydantic schema and
                  prompt that match that document's real IRS box layout
  cross_check   - deterministic: compares this document against the
                  client's expected-documents checklist and previously
                  received documents (missing/duplicate/unexpected/
                  inconsistent-data checks)
  review        - interrupt() pauses the graph for a preparer's decision
  finalize      - records the outcome and recomputes the client's organizer
                  completeness
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from app.graph.extraction_schema import (
    DOC_TYPE_PROMPT_KEY,
    EXTRACTION_SCHEMAS,
    DocClassification,
    OtherDocumentFields,
)
from app.graph.state import TaxIntakeState, TraceEvent
from app.llm import get_chat_model
from app.prompts import render_prompt
from app.tools.document_ingest import (
    detect_file_kind,
    encode_image_base64,
    extract_pdf_text,
    image_mime_type,
)
from app.tools.organizer import ReceivedDoc, cross_check_document, get_counterparty, recompute_client_completeness

logger = logging.getLogger(__name__)

_VALID_DOC_TYPES = set(EXTRACTION_SCHEMAS.keys())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(node: str, summary: str) -> list[TraceEvent]:
    return [{"node": node, "timestamp": _now(), "summary": summary}]


# --------------------------------------------------------------------------
# 1. ingest
# --------------------------------------------------------------------------
async def ingest_node(state: TaxIntakeState) -> dict:
    file_path = state["file_path"]
    kind = detect_file_kind(file_path)

    if kind == "image":
        image_b64 = encode_image_base64(file_path)
        mime = image_mime_type(file_path)
        return {
            "image_base64": image_b64,
            "mime_type": mime,
            "used_vision": True,
            "trace": _trace("ingest", "Detected image file; encoded for vision extraction."),
        }

    raw_text = extract_pdf_text(file_path)
    note = "" if len(raw_text) >= 40 else " (suspiciously little text -- may be a scanned page)"
    return {
        "raw_text": raw_text,
        "used_vision": False,
        "trace": _trace("ingest", f"Detected PDF; extracted {len(raw_text)} chars of text{note}."),
    }


# --------------------------------------------------------------------------
# 2. classify
# --------------------------------------------------------------------------
async def classify_node(state: TaxIntakeState) -> dict:
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(DocClassification)

    try:
        if state.get("used_vision"):
            prompt_text = render_prompt("classify_document_vision")
            mime = state.get("mime_type", "image/png")
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{state['image_base64']}"}},
                ]
            )
            result = await structured_llm.ainvoke([message])
        else:
            prompt_text = render_prompt("classify_document_text", raw_text=state.get("raw_text", ""))
            result = await structured_llm.ainvoke(prompt_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("classify_node: classification failed")
        return {
            "doc_type": "other-unknown",
            "classification_confidence": 0.0,
            "classification_reasoning": f"Classification failed: {exc.__class__.__name__}",
            "trace": _trace("classify", f"Classification failed ({exc.__class__.__name__}); defaulted to other-unknown."),
        }

    doc_type = result.doc_type if result.doc_type in _VALID_DOC_TYPES else "other-unknown"
    return {
        "doc_type": doc_type,
        "classification_confidence": result.confidence,
        "classification_reasoning": result.reasoning,
        "trace": _trace(
            "classify", f"Classified as {doc_type!r} (confidence={result.confidence:.2f}): {result.reasoning}"
        ),
    }


def route_after_classify(state: TaxIntakeState) -> str:
    """The conditional edge that sends each document to the extraction node
    whose pydantic schema and prompt match its classified type -- a W-2's
    box 1 wages and a K-1's box 1 ordinary income share nothing in common,
    so this is not a single generic extraction step."""
    doc_type = state.get("doc_type", "other-unknown")
    return {
        "W-2": "extract_w2",
        "1099-NEC": "extract_1099nec",
        "1099-INT": "extract_1099int",
        "1099-DIV": "extract_1099div",
        "K-1": "extract_k1",
        "bank-statement": "extract_bank_statement",
    }.get(doc_type, "extract_other")


# --------------------------------------------------------------------------
# 3. extract_fields (one node per document type)
# --------------------------------------------------------------------------
async def _extract_generic(state: TaxIntakeState, doc_type: str) -> dict:
    llm = get_chat_model()
    schema = EXTRACTION_SCHEMAS.get(doc_type, OtherDocumentFields)
    structured_llm = llm.with_structured_output(schema)
    prompt_key = DOC_TYPE_PROMPT_KEY.get(doc_type, "other")
    node_name = f"extract_{prompt_key}"

    try:
        if state.get("used_vision"):
            prompt_text = render_prompt(f"extract_{prompt_key}_vision")
            mime = state.get("mime_type", "image/png")
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{state['image_base64']}"}},
                ]
            )
            result = await structured_llm.ainvoke([message])
        else:
            prompt_text = render_prompt(f"extract_{prompt_key}_text", raw_text=state.get("raw_text", ""))
            result = await structured_llm.ainvoke(prompt_text)
        fields = result.model_dump()
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s: extraction failed", node_name)
        return {
            "extraction_schema_used": schema.__name__,
            "extracted_fields": {},
            "trace": _trace(node_name, f"Extraction failed ({exc.__class__.__name__}); left fields empty."),
        }

    return {
        "extraction_schema_used": schema.__name__,
        "extracted_fields": fields,
        "trace": _trace(node_name, f"Extracted {len(fields)} field(s) using {schema.__name__}."),
    }


async def extract_w2_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "W-2")


async def extract_1099nec_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "1099-NEC")


async def extract_1099int_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "1099-INT")


async def extract_1099div_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "1099-DIV")


async def extract_k1_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "K-1")


async def extract_bank_statement_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "bank-statement")


async def extract_other_node(state: TaxIntakeState) -> dict:
    return await _extract_generic(state, "other-unknown")


# --------------------------------------------------------------------------
# 4. cross_check (deterministic)
# --------------------------------------------------------------------------
async def cross_check_node(state: TaxIntakeState) -> dict:
    client_id = state["client_id"]
    doc_type = state.get("doc_type", "other-unknown")
    extracted_fields = state.get("extracted_fields", {}) or {}

    flags = cross_check_document(client_id, doc_type, extracted_fields)
    severities = ", ".join(sorted({f["severity"] for f in flags})) or "none"
    return {
        "cross_check_flags": flags,
        "trace": _trace("cross_check", f"{len(flags)} flag(s) found (severities: {severities})."),
    }


# --------------------------------------------------------------------------
# 5. review
# --------------------------------------------------------------------------
async def review_node(state: TaxIntakeState) -> dict:
    """Pause the graph and wait for a preparer's decision.

    `interrupt()` raises a `GraphInterrupt` the first time this node runs
    for a given thread; LangGraph's Postgres checkpointer persists state up
    to (but not including) this node's completion, so the process can exit
    entirely and be resumed later via `Command(resume=...)` against the
    same `thread_id` -- see `app/api/routers/documents.py::resume_document`.
    This is the point of the whole design: a document should never be added
    to a client's tax organizer without a preparer explicitly confirming
    the classification and extracted box values, and a client's document
    intake can span the entire tax season, so the workflow needs to durably
    resume per-document over that whole window, not just one sitting.
    """
    payload = interrupt(
        {
            "original_filename": state.get("original_filename"),
            "doc_type": state.get("doc_type"),
            "classification_confidence": state.get("classification_confidence"),
            "classification_reasoning": state.get("classification_reasoning"),
            "extraction_schema_used": state.get("extraction_schema_used"),
            "extracted_fields": state.get("extracted_fields", {}),
            "cross_check_flags": state.get("cross_check_flags", []),
        }
    )
    decision = str(payload.get("decision", "approve")).lower()
    feedback = str(payload.get("feedback", ""))
    corrected_fields = payload.get("corrected_fields") or {}
    if decision not in {"approve", "correct", "reject"}:
        decision = "approve"

    update: dict = {
        "human_decision": decision,
        "human_feedback": feedback,
        "trace": _trace("review", f"Preparer decision={decision} | {feedback[:200]}"),
    }

    if decision == "correct" and corrected_fields:
        merged = {**(state.get("extracted_fields") or {}), **corrected_fields}
        update["extracted_fields"] = merged
        update["corrected_fields"] = corrected_fields

    return update


# --------------------------------------------------------------------------
# 6. finalize
# --------------------------------------------------------------------------
async def finalize_node(state: TaxIntakeState) -> dict:
    decision = state.get("human_decision", "approve")
    doc_type = state.get("doc_type", "other-unknown")
    extracted_fields = state.get("extracted_fields", {}) or {}
    client_id = state["client_id"]

    if decision == "reject":
        final_status, status = "rejected", "rejected"
        recompute_client_completeness(client_id)
        summary = "Document rejected; not added to the organizer."
    else:
        final_status = "corrected_and_added" if decision == "correct" else "added_to_organizer"
        status = "completed"
        name, tax_id = get_counterparty(doc_type, extracted_fields)
        extra = [ReceivedDoc(id="__current__", doc_type=doc_type, counterparty_name=name, counterparty_id=tax_id)]
        result = recompute_client_completeness(client_id, extra_received=extra)
        summary = (
            f"Document added to organizer with status={final_status}. "
            f"Client now has {result.get('documents_received', '?')}/{result.get('documents_expected', '?')} "
            f"expected document(s) ({result.get('completeness_status', 'unknown')})."
        )

    return {"final_status": final_status, "status": status, "trace": _trace("finalize", summary)}
