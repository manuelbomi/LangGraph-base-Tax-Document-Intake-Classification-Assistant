"""Shared test fixtures.

All tests in `tests/` (excluding `tests/live/`) are fully mocked: no real
LLM calls, no real Postgres, no real network. This keeps `pytest` free and
fast to run in CI. The real end-to-end path is exercised separately by
`tests/live/test_live_smoke.py`, which is excluded by default (see the
`live` marker in `pyproject.toml`) and requires a real `OPENAI_API_KEY`
plus a reachable Postgres.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")


class _FakeStructuredRunnable:
    """Stands in for `chat_model.with_structured_output(Schema)`."""

    def __init__(self, parent: "FakeChatModel"):
        self._parent = parent

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        self._parent.calls.append(prompt)
        if not self._parent._responses:
            raise AssertionError("FakeChatModel called more times than responses were queued")
        item = self._parent._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeChatModel:
    """Stand-in for a LangChain chat model used via `.with_structured_output(...)`.

    Construct with a list of canned responses (pydantic model instances, or
    an `Exception` instance to simulate a failure); each call to `ainvoke`
    pops the next one, regardless of which schema was requested or prompt
    content -- tests queue responses in the exact order the graph will call
    the model (classify, then whichever extract_* node the classification
    routes to).
    """

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls: list[Any] = []

    def with_structured_output(self, schema: Any) -> _FakeStructuredRunnable:
        return _FakeStructuredRunnable(self)


@pytest.fixture
def fake_chat_model(monkeypatch):
    """Patch `app.graph.nodes.get_chat_model` to return a FakeChatModel.

    Returns a factory: `make(responses=[...])` -> the FakeChatModel instance,
    so each test controls exactly what the "LLM" returns at each graph step.
    """
    holder: dict[str, FakeChatModel] = {}

    def make(responses: list[Any]) -> FakeChatModel:
        model = FakeChatModel(responses)
        holder["model"] = model
        return model

    def fake_get_chat_model(*args: Any, **kwargs: Any) -> FakeChatModel:
        return holder["model"]

    monkeypatch.setattr("app.graph.nodes.get_chat_model", fake_get_chat_model)
    return make


@pytest.fixture
def fake_prompts(monkeypatch):
    """Patch `app.graph.nodes.render_prompt` to a template-free passthrough.

    Node logic is what's under test here, not prompt wording (that's
    covered by the real templates in `app/prompts/seed_prompts.py`, which
    the live smoke test exercises against a real LLM). This just avoids
    requiring a Postgres-backed prompt registry in unit tests.
    """

    def fake_render_prompt(name: str, **kwargs: Any) -> str:
        return f"[[{name}]] {kwargs}"

    monkeypatch.setattr("app.graph.nodes.render_prompt", fake_render_prompt)


@pytest.fixture
def no_organizer_io(monkeypatch):
    """Patch out every real-Postgres call the graph nodes make (cross-check
    and completeness recompute), so unit/flow/API tests never need a live
    database. Returns a small namespace of the fakes so a test can
    configure return values."""

    class _Fakes:
        cross_check_flags: list[Any] = []
        completeness_result: dict = {
            "documents_expected": 0,
            "documents_received": 0,
            "completeness_status": "incomplete",
        }
        cross_check_calls: list[Any] = []
        recompute_calls: list[Any] = []

    fakes = _Fakes()

    def fake_cross_check_document(client_id, doc_type, extracted_fields, **kwargs):
        fakes.cross_check_calls.append((client_id, doc_type, extracted_fields))
        return fakes.cross_check_flags

    def fake_recompute_client_completeness(client_id, **kwargs):
        fakes.recompute_calls.append((client_id, kwargs))
        return fakes.completeness_result

    monkeypatch.setattr("app.graph.nodes.cross_check_document", fake_cross_check_document)
    monkeypatch.setattr("app.graph.nodes.recompute_client_completeness", fake_recompute_client_completeness)
    return fakes
