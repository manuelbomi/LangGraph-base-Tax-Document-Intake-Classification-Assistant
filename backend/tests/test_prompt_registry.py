"""Unit tests for the prompt registry (`app/prompts/registry.py`).

Uses a tiny fake session (results are pre-programmed per test rather than
inspecting the real SQL) so this doesn't require a live Postgres. The real
templates + a real DB round-trip are exercised by `app/prompts/seed_prompts.py`
(run in the live smoke test).
"""
from __future__ import annotations

from app.prompts import registry


class _FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def update(self, *args, **kwargs):
        return None


class _FakeSession:
    def __init__(self, queue: list):
        self._queue = queue

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _stmt):
        return _FakeExecResult(self._queue.pop(0))

    def add(self, _obj):
        pass

    def commit(self):
        pass

    def query(self, _model):
        return _FakeQuery()


def test_get_prompt_returns_template_and_caches(monkeypatch):
    registry.invalidate_cache()

    class _Row:
        template = "Extract fields from: {raw_text}"

    monkeypatch.setattr(registry, "SessionLocal", lambda: _FakeSession([_Row()]))

    result1 = registry.get_prompt("extract_w2_text")
    assert result1 == "Extract fields from: {raw_text}"

    # Second call must hit the cache, not the DB -- the fake queue is now
    # empty, so a DB call here would raise IndexError.
    result2 = registry.get_prompt("extract_w2_text")
    assert result2 == "Extract fields from: {raw_text}"


def test_get_prompt_raises_when_missing(monkeypatch):
    registry.invalidate_cache()
    monkeypatch.setattr(registry, "SessionLocal", lambda: _FakeSession([None]))

    try:
        registry.get_prompt("does-not-exist")
        raise AssertionError("expected LookupError")
    except LookupError:
        pass


def test_render_prompt_formats_kwargs(monkeypatch):
    monkeypatch.setattr(registry, "get_prompt", lambda name: "Text: {raw_text}")

    rendered = registry.render_prompt("extract_w2_text", raw_text="w2 body")

    assert rendered == "Text: w2 body"


def test_add_prompt_version_increments_and_activates(monkeypatch):
    registry.invalidate_cache()
    # execute() is called once inside add_prompt_version to find current max version.
    monkeypatch.setattr(registry, "SessionLocal", lambda: _FakeSession([2]))

    new_version = registry.add_prompt_version("extract_w2_text", "new template text", activate=True)

    assert new_version == 3
