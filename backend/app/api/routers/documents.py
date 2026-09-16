"""REST + SSE API for document intake: upload, the bundled-sample-document
catalog (for a zero-setup demo), starting/streaming/resuming a document's
graph run, and serving the original file back to the frontend detail view.

Concurrency model (intentionally simple for a tutorial app): each active
document run gets one `asyncio.Queue` in `request.app.state.run_queues`,
fed by a background `asyncio.Task` that drives `graph.astream(...)`. The
SSE endpoint just relays whatever lands on that queue. Every event is also
persisted to the `documents` table as it happens, so a client that
reconnects (or a run that finished while nobody was watching) can still be
inspected via `GET /documents/{id}` / replayed via
`GET /documents/{id}/stream`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from sqlalchemy import select

from app.api.schemas import (
    DocumentCreateResponse,
    DocumentDetail,
    DocumentListResponse,
    DocumentSummary,
    HumanDecisionRequest,
    SampleDocument,
    SamplesResponse,
)
from app.config import get_settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.tools.document_ingest import detect_file_kind

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# The catalog backing the "or pick one of the bundled sample documents"
# zero-setup demo path -- see sample-data/README.md for what each one is.
# `suggested_client_id` is a hint the frontend uses to preselect a client;
# any sample can be uploaded for any client.
SAMPLE_CATALOG: list[dict[str, str]] = [
    {
        "id": "w2-cascade-ellis",
        "label": "W-2 - Jordan Ellis / Cascade Retail Group",
        "doc_type": "W-2",
        "relative_path": "w2/W2_Cascade_Retail_Group_Jordan_Ellis.pdf",
        "suggested_client_id": "jordan-ellis",
    },
    {
        "id": "1099nec-bluepeak-ellis",
        "label": "1099-NEC - Jordan Ellis / Bluepeak Design Studio",
        "doc_type": "1099-NEC",
        "relative_path": "1099/1099NEC_Bluepeak_Design_Studio_Jordan_Ellis.pdf",
        "suggested_client_id": "jordan-ellis",
    },
    {
        "id": "1099int-harborview-ellis",
        "label": "1099-INT - Jordan Ellis / Harborview Savings Bank",
        "doc_type": "1099-INT",
        "relative_path": "1099/1099INT_Harborview_Savings_Bank_Jordan_Ellis.pdf",
        "suggested_client_id": "jordan-ellis",
    },
    {
        "id": "bank-stmt-harborview-ellis",
        "label": "Bank Statement - Jordan Ellis / Harborview Savings Bank (supplementary)",
        "doc_type": "bank-statement",
        "relative_path": "bank-statements/Harborview_Savings_Bank_Statement_Jordan_Ellis.pdf",
        "suggested_client_id": "jordan-ellis",
    },
    {
        "id": "w2-fenwick-alvarez",
        "label": "W-2 - Morgan Alvarez / Fenwick Logistics Inc",
        "doc_type": "W-2",
        "relative_path": "w2/W2_Fenwick_Logistics_Inc_Morgan_Alvarez.pdf",
        "suggested_client_id": "morgan-alvarez",
    },
    {
        "id": "1099div-crestline-alvarez",
        "label": "1099-DIV - Morgan Alvarez / Crestline Investments",
        "doc_type": "1099-DIV",
        "relative_path": "1099/1099DIV_Crestline_Investments_Morgan_Alvarez.pdf",
        "suggested_client_id": "morgan-alvarez",
    },
    {
        "id": "k1-alvarez-holdings",
        "label": "Schedule K-1 - Morgan Alvarez / Alvarez Family Holdings LLC",
        "doc_type": "K-1",
        "relative_path": "k1/K1_Alvarez_Family_Holdings_LLC_Morgan_Alvarez.pdf",
        "suggested_client_id": "morgan-alvarez",
    },
]
_SAMPLE_BY_ID = {s["id"]: s for s in SAMPLE_CATALOG}


def _is_flagged(doc: Document) -> bool:
    return any(f.get("severity") in {"warning", "error"} for f in (doc.cross_check_flags or []))


def _to_summary(doc: Document) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        client_id=doc.client_id,
        original_filename=doc.original_filename,
        doc_type=doc.doc_type,  # type: ignore[arg-type]
        classification_confidence=doc.classification_confidence,
        status=doc.status,  # type: ignore[arg-type]
        final_status=doc.final_status,
        flagged=_is_flagged(doc),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


async def _run_graph(request: Request, thread_id: str, graph_input: Any) -> None:
    """Background task: drive the graph, persist + broadcast each step."""
    graph = request.app.state.graph
    queue: asyncio.Queue = request.app.state.run_queues[thread_id]
    config = {"configurable": {"thread_id": thread_id}}

    def _set_status(status: str, **extra: Any) -> None:
        with SessionLocal() as db:
            doc = db.get(Document, thread_id)
            if doc is None:
                return
            doc.status = status
            for k, v in extra.items():
                setattr(doc, k, v)
            db.commit()

    def _record_event(node_output: dict[str, Any]) -> None:
        trace_items = node_output.get("trace", [])
        with SessionLocal() as db:
            doc = db.get(Document, thread_id)
            if doc is None:
                return
            doc.trace = [*doc.trace, *trace_items]
            merged_snapshot = {**doc.state_snapshot, **{k: v for k, v in node_output.items() if k != "trace"}}
            doc.state_snapshot = merged_snapshot
            doc.doc_type = merged_snapshot.get("doc_type", doc.doc_type)
            doc.classification_confidence = merged_snapshot.get(
                "classification_confidence", doc.classification_confidence
            )
            if "extracted_fields" in node_output:
                doc.extracted_fields = node_output["extracted_fields"]
            if "cross_check_flags" in node_output:
                doc.cross_check_flags = node_output["cross_check_flags"]
            db.commit()

    try:
        _set_status("running")
        async for event in graph.astream(graph_input, config=config, stream_mode="updates"):
            if "__interrupt__" in event:
                interrupt_obj = event["__interrupt__"][0]
                payload = dict(interrupt_obj.value)
                with SessionLocal() as db:
                    doc = db.get(Document, thread_id)
                    if doc is not None:
                        doc.status = "awaiting_human"
                        doc.state_snapshot = {**doc.state_snapshot, "interrupt": payload}
                        db.commit()
                await queue.put(_sse("interrupt", payload))
                continue

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                _record_event(node_output)
                await queue.put(
                    _sse(
                        "node",
                        {
                            "node": node_name,
                            "output": {k: v for k, v in node_output.items() if k != "trace"},
                            "trace": node_output.get("trace", []),
                        },
                    )
                )
                if node_name != "review":
                    _set_status("running")

        # Loop ended without an interrupt -> graph ran to completion (END).
        state = await graph.aget_state(config)
        if not state.next:  # no pending nodes => finished
            values = state.values
            status = values.get("status", "completed")
            final_status = values.get("final_status")
            with SessionLocal() as db:
                doc = db.get(Document, thread_id)
                if doc is not None:
                    doc.status = status
                    doc.final_status = final_status
                    merged_snapshot = {**doc.state_snapshot, **values}
                    doc.state_snapshot = merged_snapshot
                    doc.doc_type = values.get("doc_type", doc.doc_type)
                    doc.classification_confidence = values.get(
                        "classification_confidence", doc.classification_confidence
                    )
                    doc.extracted_fields = values.get("extracted_fields", doc.extracted_fields)
                    doc.cross_check_flags = values.get("cross_check_flags", doc.cross_check_flags)
                    db.commit()
            await queue.put(_sse("done", {"status": status, "final_status": final_status}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Document run %s failed", thread_id)
        with SessionLocal() as db:
            doc = db.get(Document, thread_id)
            if doc is not None:
                doc.status = "error"
                doc.error = str(exc)
                db.commit()
        await queue.put(_sse("error", {"message": str(exc)}))
    finally:
        await queue.put(None)  # sentinel: close the SSE stream


def _start_background_run(request: Request, thread_id: str, graph_input: Any) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.run_queues[thread_id] = queue
    task = asyncio.create_task(_run_graph(request, thread_id, graph_input))
    request.app.state.run_tasks[thread_id] = task


async def start_document_run(
    request: Request,
    *,
    client_id: str,
    file_path: str,
    original_filename: str,
    run_id: str | None = None,
) -> DocumentCreateResponse:
    """Create a `Document` row and kick off the graph in the background.
    Shared by both the upload and run-a-sample-document endpoints below."""
    with SessionLocal() as db:
        from app.db.models import Client

        if db.get(Client, client_id) is None:
            raise HTTPException(404, f"client {client_id!r} not found")

    run_id = run_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        doc = Document(
            id=run_id,
            client_id=client_id,
            original_filename=original_filename,
            doc_type="unknown",
            status="pending",
            extracted_fields={},
            cross_check_flags=[],
            trace=[],
            state_snapshot={},
            created_at=now,
            updated_at=now,
        )
        db.add(doc)
        db.commit()

    _start_background_run(
        request,
        run_id,
        {"file_path": file_path, "original_filename": original_filename, "client_id": client_id},
    )
    return DocumentCreateResponse(id=run_id, client_id=client_id, status="pending", original_filename=original_filename, doc_type="unknown")


@router.get("/samples", response_model=SamplesResponse)
async def list_samples() -> SamplesResponse:
    return SamplesResponse(
        samples=[
            SampleDocument(
                id=s["id"], label=s["label"], doc_type=s["doc_type"], suggested_client_id=s["suggested_client_id"]
            )
            for s in SAMPLE_CATALOG
        ]
    )


@router.post("/samples/{sample_id}/run", response_model=DocumentCreateResponse)
async def run_sample_document(sample_id: str, request: Request, client_id: str = Form(...)) -> DocumentCreateResponse:
    entry = _SAMPLE_BY_ID.get(sample_id)
    if entry is None:
        raise HTTPException(404, "unknown sample id")

    settings = get_settings()
    src_path = os.path.join(settings.sample_data_dir, entry["relative_path"])
    if not os.path.exists(src_path):
        raise HTTPException(500, f"sample file missing on server: {entry['relative_path']}")

    return await start_document_run(
        request,
        client_id=client_id,
        file_path=src_path,
        original_filename=os.path.basename(entry["relative_path"]),
    )


@router.post("/upload", response_model=DocumentCreateResponse)
async def upload_document(request: Request, client_id: str = Form(...), file: UploadFile = File(...)) -> DocumentCreateResponse:
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'!r}. Allowed: {sorted(_ALLOWED_EXTENSIONS)}")
    detect_file_kind(filename)  # raises if truly unrecognized

    settings = get_settings()
    run_id = str(uuid.uuid4())
    dest_dir = os.path.join(settings.upload_dir, run_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    return await start_document_run(
        request, client_id=client_id, file_path=dest_path, original_filename=filename, run_id=run_id
    )


@router.get("/{document_id}/file")
async def get_document_source_file(document_id: str):
    """Serve the original uploaded/sample file back to the frontend, so the
    organizer detail view can show the source document alongside its
    extracted fields."""
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "document not found")

    settings = get_settings()
    candidate = os.path.join(settings.upload_dir, document_id, doc.original_filename)
    if not os.path.exists(candidate):
        for sample in SAMPLE_CATALOG:
            if os.path.basename(sample["relative_path"]) == doc.original_filename:
                candidate = os.path.join(settings.sample_data_dir, sample["relative_path"])
                break

    if not os.path.exists(candidate):
        raise HTTPException(404, "original file not found on the server")

    return FileResponse(candidate, filename=doc.original_filename)


@router.post("/{document_id}/resume", response_model=DocumentCreateResponse)
async def resume_document(document_id: str, body: HumanDecisionRequest, request: Request) -> DocumentCreateResponse:
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        if doc.status != "awaiting_human":
            raise HTTPException(409, f"document is not awaiting human review (status={doc.status})")
        client_id = doc.client_id
        original_filename = doc.original_filename
        doc_type = doc.doc_type

    _start_background_run(
        request,
        document_id,
        Command(
            resume={
                "decision": body.decision,
                "feedback": body.feedback,
                "corrected_fields": body.corrected_fields or {},
            }
        ),
    )
    return DocumentCreateResponse(
        id=document_id, client_id=client_id, status="running", original_filename=original_filename, doc_type=doc_type
    )


@router.get("/{document_id}/stream")
async def stream_document(document_id: str, request: Request) -> StreamingResponse:
    async def event_source():
        queue: asyncio.Queue | None = request.app.state.run_queues.get(document_id)

        if queue is None:
            # No live background task (already finished, or the server was
            # restarted after this document reached a terminal/awaiting
            # state). Replay what's durably stored instead of streaming live.
            with SessionLocal() as db:
                doc = db.get(Document, document_id)
            if doc is None:
                yield _sse("error", {"message": "document not found"})
                return
            yield _sse(
                "replay",
                {
                    "status": doc.status,
                    "trace": doc.trace,
                    "state_snapshot": doc.state_snapshot,
                    "final_status": doc.final_status,
                },
            )
            if doc.status == "awaiting_human":
                interrupt_payload = doc.state_snapshot.get("interrupt", {})
                yield _sse("interrupt", interrupt_payload)
            yield _sse("done", {"status": doc.status, "final_status": doc.final_status})
            return

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(client_id: str | None = None) -> DocumentListResponse:
    with SessionLocal() as db:
        stmt = select(Document).order_by(Document.created_at.desc())
        if client_id:
            stmt = stmt.where(Document.client_id == client_id)
        rows = db.execute(stmt).scalars().all()
        return DocumentListResponse(documents=[_to_summary(d) for d in rows])


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str) -> DocumentDetail:
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            raise HTTPException(404, "document not found")
        return DocumentDetail(
            **_to_summary(doc).model_dump(),
            extraction_schema_used=doc.state_snapshot.get("extraction_schema_used"),
            extracted_fields=doc.extracted_fields,
            cross_check_flags=doc.cross_check_flags,
            trace=doc.trace,
            state_snapshot=doc.state_snapshot,
            error=doc.error,
        )
