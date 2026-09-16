"""Read-only client / organizer endpoints: the per-client checklist
(expected vs. received documents) and document history that back the
"Client Organizer / Example Analyses" page."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.schemas import ClientDetail, ClientListResponse, ClientSummary, DocumentSummary
from app.db.models import Client
from app.db.session import SessionLocal

router = APIRouter(prefix="/clients", tags=["clients"])


def _is_flagged(doc) -> bool:
    return any(f.get("severity") in {"warning", "error"} for f in (doc.cross_check_flags or []))


def _to_summary(client: Client) -> ClientSummary:
    return ClientSummary(
        id=client.id,
        name=client.name,
        tax_year=client.tax_year,
        documents_expected=client.documents_expected,
        documents_received=client.documents_received,
        completeness_status=client.completeness_status,  # type: ignore[arg-type]
    )


@router.get("", response_model=ClientListResponse)
async def list_clients() -> ClientListResponse:
    with SessionLocal() as db:
        rows = db.execute(select(Client).order_by(Client.name)).scalars().all()
        return ClientListResponse(clients=[_to_summary(c) for c in rows])


@router.get("/{client_id}", response_model=ClientDetail)
async def get_client(client_id: str) -> ClientDetail:
    with SessionLocal() as db:
        client = db.get(Client, client_id)
        if client is None:
            raise HTTPException(404, "client not found")
        documents = [
            DocumentSummary(
                id=d.id,
                client_id=d.client_id,
                original_filename=d.original_filename,
                doc_type=d.doc_type,  # type: ignore[arg-type]
                classification_confidence=d.classification_confidence,
                status=d.status,  # type: ignore[arg-type]
                final_status=d.final_status,
                flagged=_is_flagged(d),
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in client.documents
        ]
        summary = _to_summary(client)
        return ClientDetail(
            **summary.model_dump(),
            notes=client.notes,
            expected_documents=client.expected_documents or [],
            documents=documents,
        )
