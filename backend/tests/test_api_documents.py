"""API contract tests for the /clients and /documents endpoints.

Uses a lightweight in-memory fake in place of the Postgres-backed
`SessionLocal`, and an `InMemorySaver` in place of the Postgres checkpointer,
so these run without any real database. LLM + organizer calls are mocked
exactly as in `test_graph_nodes.py` / `test_graph_flow.py`. PDF text
extraction is mocked too (`extract_pdf_text`) since the uploaded test file
isn't a real PDF -- `detect_file_kind` is left real since it's pure,
deterministic extension-sniffing with no I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.routers.clients import router as clients_router
from app.api.routers.documents import router as documents_router
from app.config import Settings
from app.db.models import Client, Document
from app.graph.extraction_schema import DocClassification, W2Fields
from app.graph.graph import build_graph


class _FakeResultSet:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, clients: dict, documents: dict):
        self._clients = clients
        self._documents = documents

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add(self, obj) -> None:
        if isinstance(obj, Client):
            self._clients[obj.id] = obj
        elif isinstance(obj, Document):
            self._documents[obj.id] = obj

    def commit(self) -> None:
        pass

    def get(self, model, id_):
        if model is Client:
            return self._clients.get(id_)
        if model is Document:
            return self._documents.get(id_)
        return None

    def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is Client:
            rows = sorted(self._clients.values(), key=lambda c: c.name)
        else:
            rows = sorted(self._documents.values(), key=lambda d: d.created_at, reverse=True)
        return _FakeResultSet(rows)


def _seed_client(clients: dict, client_id="jordan-ellis") -> Client:
    client = Client(
        id=client_id,
        name="Jordan Ellis",
        tax_year=2025,
        notes="",
        expected_documents=[{"doc_type": "W-2", "counterparty_name": "Cascade Retail Group"}],
        documents_expected=1,
        documents_received=0,
        completeness_status="incomplete",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    clients[client_id] = client
    return client


@pytest.fixture
def api_app(monkeypatch, fake_chat_model, fake_prompts, no_organizer_io, tmp_path):
    clients: dict[str, Client] = {}
    documents: dict[str, Document] = {}
    _seed_client(clients)

    monkeypatch.setattr("app.api.routers.clients.SessionLocal", lambda: _FakeSession(clients, documents))
    monkeypatch.setattr("app.api.routers.documents.SessionLocal", lambda: _FakeSession(clients, documents))

    fake_settings = Settings(
        upload_dir=str(tmp_path / "uploads"), sample_data_dir=str(tmp_path / "sample-data")
    )
    monkeypatch.setattr("app.api.routers.documents.get_settings", lambda: fake_settings)

    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "w-2 wage and tax statement")
    monkeypatch.setattr("app.graph.nodes.encode_image_base64", lambda p: "abc123")

    app = FastAPI()
    app.state.run_queues = {}
    app.state.run_tasks = {}
    app.state.graph = build_graph(checkpointer=InMemorySaver())
    app.include_router(clients_router)
    app.include_router(documents_router)
    return app, clients, documents


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _w2_response() -> W2Fields:
    return W2Fields(
        employer_name="Cascade Retail Group",
        employer_ein="84-1234567",
        employee_name="Jordan Ellis",
        employee_ssn="412-34-5678",
        tax_year=2025,
        box1_wages=28450.0,
    )


async def test_list_clients_returns_seeded_client(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/clients")
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.json()["clients"]}
        assert "jordan-ellis" in ids


async def test_get_client_detail(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/clients/jordan-ellis")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Jordan Ellis"
        assert len(body["expected_documents"]) == 1


async def test_get_unknown_client_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/clients/does-not-exist")
        assert resp.status_code == 404


async def test_list_samples_returns_catalog(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/documents/samples")
        assert resp.status_code == 200
        samples = resp.json()["samples"]
        ids = {s["id"] for s in samples}
        assert "w2-cascade-ellis" in ids


async def test_upload_w2_reaches_review(api_app, fake_chat_model):
    app, _, _ = api_app
    fake_chat_model([DocClassification(doc_type="W-2", confidence=0.95, reasoning="W-2 box layout."), _w2_response()])

    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload",
            data={"client_id": "jordan-ellis"},
            files={"file": ("test_w2.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        doc_id = body["id"]

        await app.state.run_tasks[doc_id]

        detail = await client.get(f"/documents/{doc_id}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["status"] == "awaiting_human"
        assert detail_body["doc_type"] == "W-2"
        assert detail_body["extracted_fields"]["employer_name"] == "Cascade Retail Group"
        assert len(detail_body["trace"]) >= 3


async def test_upload_unknown_client_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload",
            data={"client_id": "does-not-exist"},
            files={"file": ("test_w2.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        )
        assert resp.status_code == 404


async def test_upload_rejects_unsupported_extension(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload",
            data={"client_id": "jordan-ellis"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400


async def test_run_sample_document(api_app, fake_chat_model, tmp_path):
    app, _, _ = api_app
    fake_chat_model([DocClassification(doc_type="W-2", confidence=0.95, reasoning="W-2 box layout."), _w2_response()])

    sample_dir = tmp_path / "sample-data" / "w2"
    sample_dir.mkdir(parents=True)
    (sample_dir / "W2_Cascade_Retail_Group_Jordan_Ellis.pdf").write_bytes(b"%PDF-1.4 fake content")

    async with await _client(app) as client:
        resp = await client.post("/documents/samples/w2-cascade-ellis/run", data={"client_id": "jordan-ellis"})
        assert resp.status_code == 200
        doc_id = resp.json()["id"]

        await app.state.run_tasks[doc_id]

        detail = await client.get(f"/documents/{doc_id}")
        assert detail.json()["extracted_fields"]["employer_name"] == "Cascade Retail Group"


async def test_run_unknown_sample_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post("/documents/samples/does-not-exist/run", data={"client_id": "jordan-ellis"})
        assert resp.status_code == 404


async def test_resume_document_completes(api_app, fake_chat_model):
    app, _, _ = api_app
    fake_chat_model([DocClassification(doc_type="W-2", confidence=0.95, reasoning="W-2 box layout."), _w2_response()])

    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload",
            data={"client_id": "jordan-ellis"},
            files={"file": ("test_w2.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        )
        doc_id = resp.json()["id"]
        await app.state.run_tasks[doc_id]

        resume_resp = await client.post(
            f"/documents/{doc_id}/resume", json={"decision": "approve", "feedback": "Looks good."}
        )
        assert resume_resp.status_code == 200
        await app.state.run_tasks[doc_id]

        detail = await client.get(f"/documents/{doc_id}")
        detail_body = detail.json()
        assert detail_body["status"] == "completed"
        assert detail_body["final_status"] == "added_to_organizer"


async def test_resume_rejects_when_not_awaiting_human(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/documents/does-not-exist/resume", json={"decision": "approve", "feedback": ""}
        )
        assert resp.status_code == 404


async def test_list_documents_returns_summaries(api_app):
    app, _, documents = api_app
    now = datetime.now(timezone.utc)
    documents["d1"] = Document(
        id="d1", client_id="jordan-ellis", original_filename="a.pdf", doc_type="W-2",
        classification_confidence=0.9, status="completed", final_status="added_to_organizer",
        extracted_fields={}, cross_check_flags=[], trace=[], state_snapshot={}, created_at=now, updated_at=now,
    )
    documents["d2"] = Document(
        id="d2", client_id="jordan-ellis", original_filename="b.pdf", doc_type="1099-NEC",
        classification_confidence=0.9, status="awaiting_human", final_status=None,
        extracted_fields={}, cross_check_flags=[], trace=[], state_snapshot={}, created_at=now, updated_at=now,
    )

    async with await _client(app) as client:
        resp = await client.get("/documents")
        assert resp.status_code == 200
        ids = {d["id"] for d in resp.json()["documents"]}
        assert ids == {"d1", "d2"}


async def test_get_unknown_document_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/documents/nope")
        assert resp.status_code == 404
