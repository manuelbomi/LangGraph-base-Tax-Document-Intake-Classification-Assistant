"""REAL end-to-end smoke test: actual OpenAI API calls + a real Postgres.

This is deliberately excluded from the default `pytest` run (see the `live`
marker + `addopts` in `pyproject.toml`). Run it explicitly with:

    export OPENAI_API_KEY=sk-...
    export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tax_intake
    cd backend
    pytest -m live tests/live/test_live_smoke.py -v -s

What it proves, with no mocks anywhere in the graph/LLM/DB/organizer path:
  1. A real sample W-2 PDF (`sample-data/w2/W2_Cascade_Retail_Group_Jordan_Ellis.pdf`)
     is ingested, classified by a real `gpt-4o-mini` call, its boxes
     extracted by a second real `gpt-4o-mini` call, and cross-checked
     against the REAL client checklist (seeded from
     `sample-data/organizer/jordan_ellis.json`) -- reaching `review` and
     genuinely pausing there (`interrupt()`).
  2. The checkpointer can be torn down and a BRAND NEW `AsyncPostgresSaver`
     + freshly-compiled graph (standing in for "a new process", e.g. the
     preparer coming back to their review queue the next day, or even next
     week as more of this client's documents trickle in) can resume that
     exact thread and finish the run (`finalize`), adding it to the
     client's organizer.

Cost note: this makes exactly TWO small `gpt-4o-mini` structured-output
calls (classification + W-2 field extraction) and zero embedding calls.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop;
    # it needs a selector-based loop. This only matters for local dev on
    # Windows -- the backend Docker image (and CI) run on Linux, where this
    # is a no-op. See: https://www.psycopg.org/psycopg3/docs/advanced/async.html
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from alembic import command
from alembic.config import Config
from langgraph.types import Command

from app.config import get_settings
from app.db.checkpointer import build_checkpointer
from app.graph.graph import build_graph
from app.prompts.seed_prompts import seed as seed_prompts
from scripts.seed_clients import seed as seed_clients

pytestmark = pytest.mark.live

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_migrations() -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "app", "db", "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module", autouse=True)
def _prepare_schema():
    assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY must be set for the live smoke test"
    assert os.environ.get("DATABASE_URL"), "DATABASE_URL must point at a real reachable Postgres"
    _run_migrations()
    seed_prompts()
    seed_clients()
    yield


async def test_live_w2_survives_checkpointer_restart_and_is_added_to_organizer():
    settings = get_settings()
    w2_path = os.path.join(settings.sample_data_dir, "w2", "W2_Cascade_Retail_Group_Jordan_Ellis.pdf")
    assert os.path.exists(w2_path), f"sample W-2 not found at {w2_path}"

    thread_id = "live-smoke-thread"
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {
        "file_path": w2_path,
        "original_filename": "W2_Cascade_Retail_Group_Jordan_Ellis.pdf",
        "client_id": "jordan-ellis",
    }

    # --- Phase 1: run until it pauses at review --------------------------
    async with build_checkpointer() as checkpointer_1:
        graph_1 = build_graph(checkpointer=checkpointer_1)

        saw_interrupt = False
        async for event in graph_1.astream(graph_input, config=config, stream_mode="updates"):
            print("EVENT:", list(event.keys()))
            if "__interrupt__" in event:
                saw_interrupt = True
                payload = event["__interrupt__"][0].value
                print("\n--- CLASSIFICATION + EXTRACTED FIELDS AT REVIEW ---")
                print("doc_type:", payload["doc_type"], "confidence:", payload["classification_confidence"])
                print("extracted_fields:", payload["extracted_fields"])
                print("cross_check_flags:", payload["cross_check_flags"])
                assert payload["doc_type"] == "W-2"
                assert payload["extracted_fields"]["employer_name"], "expected a non-empty employer name"
                assert payload["extracted_fields"]["box1_wages"] > 0
        assert saw_interrupt, "graph should have paused at review"

        state = await graph_1.aget_state(config)
        assert state.next == ("review",)
    # `async with` exits here -> checkpointer_1's connection pool is fully
    # closed, simulating the backend process shutting down.

    # --- Phase 2: brand new checkpointer + graph, standing in for a ----
    # --- freshly-started process, resumes the SAME thread_id -----------
    async with build_checkpointer() as checkpointer_2:
        graph_2 = build_graph(checkpointer=checkpointer_2)

        # Prove the state genuinely persisted in Postgres, not in memory.
        resumed_state = await graph_2.aget_state(config)
        assert resumed_state.next == ("review",)
        assert resumed_state.values["extracted_fields"]["employer_name"]

        finished = False
        async for event in graph_2.astream(
            Command(resume={"decision": "approve", "feedback": "Approved by live smoke test."}),
            config=config,
            stream_mode="updates",
        ):
            print("RESUME EVENT:", list(event.keys()))
            if "finalize" in event:
                finished = True

        assert finished, "graph should have reached finalize after resume"
        final_state = await graph_2.aget_state(config)
        assert final_state.next == ()
        assert final_state.values["status"] == "completed"
        assert final_state.values["final_status"] == "added_to_organizer"
        print(
            "\n--- FINAL STATE ---\n",
            {k: final_state.values[k] for k in ("doc_type", "final_status")},
        )
