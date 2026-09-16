"""SQLAlchemy models: the `prompts` registry, `clients` (each with a
tax-year expected-documents checklist), and `documents` (every document ever
processed for a client -- this doubles as both the "run history" and the
durable organizer record).

Note: LangGraph's `AsyncPostgresSaver` manages its own checkpoint tables
(`checkpoints`, `checkpoint_writes`, ...) via `checkpointer.setup()` -- those
are NOT modeled here and are intentionally left out of Alembic's autogenerate
scope (see `db/migrations/env.py`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Prompt(Base):
    """A versioned prompt template.

    Only one version per `name` is `is_active` at a time; `get_prompt(name)`
    (see `app/prompts/registry.py`) resolves to that active version. There
    is one prompt per graph LLM call: `classify_document`, plus one
    `extract_*` prompt per supported document type.
    """

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prompt name={self.name!r} v{self.version} active={self.is_active}>"


class Client(Base):
    """One fictitious tax client for a given tax year.

    `expected_documents` is the "prior-year organizer checklist" carried
    forward: a JSON list of `{doc_type, counterparty_name, notes}` objects
    describing what this client's situation implies they should receive
    this year (e.g. a W-2 job + freelance 1099 income + one savings
    account). `cross_check_node` (see `app/graph/nodes.py`) compares each
    newly processed document against this list; `finalize_node` recomputes
    `documents_received`/`documents_expected`/`completeness_status` (via
    `app/tools/organizer.py::recompute_client_completeness`) every time a
    document is finalized, so the organizer view always reflects "what's
    still missing" without the frontend having to recompute it.
    """

    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    expected_documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{"doc_type": "W-2", "counterparty_name": "Cascade Retail Group", "notes": "..."}]

    documents_expected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completeness_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="incomplete"
    )  # "incomplete" | "complete"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Document.created_at"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Client name={self.name!r} tax_year={self.tax_year}>"


class Document(Base):
    """One end-to-end document intake run, keyed by the LangGraph
    `thread_id`. Every document a client ever uploads gets a row here --
    this is both the "run history" for the frontend and the durable
    organizer record `finalize_node` writes to.
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    doc_type: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    # W-2 | 1099-NEC | 1099-INT | 1099-DIV | K-1 | bank-statement | other-unknown
    classification_confidence: Mapped[float] = mapped_column(default=0.0)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | running | awaiting_human | completed | rejected | error
    final_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # added_to_organizer | corrected_and_added | rejected

    extracted_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cross_check_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    trace: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    client: Mapped[Client] = relationship(back_populates="documents")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Document id={self.id} doc_type={self.doc_type!r} status={self.status!r}>"
