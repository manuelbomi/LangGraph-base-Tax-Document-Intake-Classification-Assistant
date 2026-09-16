"""Wiring for LangGraph's Postgres checkpointer.

This is what makes a document's intake run durable: `AsyncPostgresSaver`
persists the full graph state after every node executes, keyed by
`thread_id` (one thread per document being processed). A run paused at
`review` (via `interrupt()`) -- a preparer's queue item waiting for their
attention -- can be resumed hours, days, or weeks later, even from a brand
new process, by opening a fresh `AsyncPostgresSaver` against the same
Postgres database and calling
`graph.astream(Command(resume=...), config={"configurable": {"thread_id": ...}})`.

That durability matters specifically for tax document intake: a client's
documents trickle in over the whole span of tax season, and nothing here
should ever be added to a client's organizer without a preparer explicitly
confirming the classification and extracted values -- tax data entry
mistakes have real financial/compliance consequences.

We open ONE saver for the lifetime of the FastAPI process (see
`app/main.py` lifespan) rather than one per request, since it owns a
connection pool.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


def _psycopg_dsn(database_url: str) -> str:
    """Strip the SQLAlchemy "+psycopg" driver suffix -> a plain psycopg DSN."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def build_checkpointer():
    """Yield a ready-to-use (schema already set up) AsyncPostgresSaver."""
    settings = get_settings()
    dsn = _psycopg_dsn(settings.database_url)
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        yield saver
