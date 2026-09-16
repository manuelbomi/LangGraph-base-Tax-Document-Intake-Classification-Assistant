"""FastAPI application entrypoint.

Wires up (for the lifetime of the process):
  - a single `AsyncPostgresSaver` (LangGraph's durable Postgres checkpointer)
  - the compiled tax-intake graph, built against that checkpointer
  - in-memory registries for active SSE queues / background run tasks

This is what makes `review` resumable across restarts: the checkpointer's
connection pool is opened once here, `saver.setup()` ensures its tables
exist, and every graph invocation anywhere in the app uses `app.state.graph`,
which is bound to that one durable checkpointer.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.clients import router as clients_router
from app.api.routers.documents import router as documents_router
from app.config import get_settings
from app.db.checkpointer import build_checkpointer
from app.graph.graph import build_graph

logging.basicConfig(level=logging.INFO)

if sys.platform == "win32":
    # psycopg's async mode requires a selector-based event loop; Windows'
    # default ProactorEventLoop doesn't support it. No-op on Linux/macOS
    # (i.e. inside the backend Docker image and in CI).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.run_queues = {}
    app.state.run_tasks = {}

    async with build_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        app.state.graph = build_graph(checkpointer=checkpointer)
        logging.info("Tax document intake graph compiled with AsyncPostgresSaver checkpointer.")
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Tax Document Intake & Classification Assistant API",
        description=(
            "LangGraph-powered tax document intake assistant: ingest -> "
            "classify -> extract_fields (per document type) -> cross_check "
            "-> review -> finalize, with durable Postgres checkpointing and "
            "a human-in-the-loop interrupt before anything is added to a "
            "client's organizer."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(clients_router)
    app.include_router(documents_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
