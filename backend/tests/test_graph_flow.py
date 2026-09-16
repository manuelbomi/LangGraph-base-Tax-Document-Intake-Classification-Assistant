"""End-to-end graph flow tests using LangGraph's in-memory checkpointer.

This proves the interrupt/resume *mechanics* (the same API the FastAPI app
uses against Postgres in `app/db/checkpointer.py`) without needing a real
database or LLM. The equivalent test against a *real* Postgres checkpointer
and a *real* OpenAI key lives in `tests/live/test_live_smoke.py`.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.extraction_schema import DocClassification, W2Fields
from app.graph.graph import build_graph


async def test_w2_pauses_at_review_and_resumes_to_completion(
    fake_chat_model, fake_prompts, no_organizer_io, monkeypatch
):
    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "pdf")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "w-2 wage and tax statement")
    no_organizer_io.cross_check_flags = []

    fake_chat_model(
        [
            DocClassification(doc_type="W-2", confidence=0.95, reasoning="Has W-2 box layout."),
            W2Fields(
                employer_name="Cascade Retail Group",
                employee_name="Jordan Ellis",
                tax_year=2025,
                box1_wages=28450.0,
            ),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-w2"}}

    result = None
    async for event in graph.astream(
        {"file_path": "w2.pdf", "original_filename": "w2.pdf", "client_id": "jordan-ellis"},
        config=config,
        stream_mode="updates",
    ):
        result = event

    assert result is not None
    assert "__interrupt__" in result, "graph should pause at review"
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["doc_type"] == "W-2"
    assert interrupt_payload["extracted_fields"]["employer_name"] == "Cascade Retail Group"

    state_before_resume = await graph.aget_state(config)
    assert state_before_resume.next == ("review",)

    final_event = None
    async for event in graph.astream(
        Command(resume={"decision": "approve", "feedback": "Looks correct."}),
        config=config,
        stream_mode="updates",
    ):
        final_event = event

    assert "finalize" in final_event
    final_state = await graph.aget_state(config)
    assert final_state.next == ()  # graph reached END
    assert final_state.values["status"] == "completed"
    assert final_state.values["final_status"] == "added_to_organizer"


async def test_correct_and_approve_applies_corrected_fields(
    fake_chat_model, fake_prompts, no_organizer_io, monkeypatch
):
    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "pdf")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "w-2 wage and tax statement")
    no_organizer_io.cross_check_flags = []

    fake_chat_model(
        [
            DocClassification(doc_type="W-2", confidence=0.95, reasoning="Has W-2 box layout."),
            W2Fields(
                employer_name="Cascade Retail Gruop",  # typo, to be corrected
                employee_name="Jordan Ellis",
                tax_year=2025,
                box1_wages=28450.0,
            ),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-correct"}}

    async for _ in graph.astream(
        {"file_path": "w2.pdf", "original_filename": "w2.pdf", "client_id": "jordan-ellis"},
        config=config,
        stream_mode="updates",
    ):
        pass

    async for _ in graph.astream(
        Command(
            resume={
                "decision": "correct",
                "feedback": "Fixed employer name typo.",
                "corrected_fields": {"employer_name": "Cascade Retail Group"},
            }
        ),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["extracted_fields"]["employer_name"] == "Cascade Retail Group"
    assert final_state.values["final_status"] == "corrected_and_added"


async def test_reject_decision_does_not_add_to_organizer(fake_chat_model, fake_prompts, no_organizer_io, monkeypatch):
    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "pdf")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "w-2 wage and tax statement")
    no_organizer_io.cross_check_flags = [
        {"code": "duplicate_document", "severity": "error", "message": "duplicate", "details": {}}
    ]

    fake_chat_model(
        [
            DocClassification(doc_type="W-2", confidence=0.95, reasoning="Has W-2 box layout."),
            W2Fields(employer_name="Fenwick Logistics Inc", employee_name="Morgan Alvarez", tax_year=2025, box1_wages=41200.0),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-reject"}}

    async for _ in graph.astream(
        {"file_path": "w2.pdf", "original_filename": "w2.pdf", "client_id": "morgan-alvarez"},
        config=config,
        stream_mode="updates",
    ):
        pass

    async for _ in graph.astream(
        Command(resume={"decision": "reject", "feedback": "Duplicate of an existing W-2."}),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["final_status"] == "rejected"
    assert final_state.values["status"] == "rejected"


async def test_bank_statement_routes_to_extract_bank_statement(
    fake_chat_model, fake_prompts, no_organizer_io, monkeypatch
):
    from app.graph.extraction_schema import BankStatementFields

    monkeypatch.setattr("app.graph.nodes.detect_file_kind", lambda p: "pdf")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "bank statement text")
    no_organizer_io.cross_check_flags = []

    fake_chat_model(
        [
            DocClassification(doc_type="bank-statement", confidence=0.88, reasoning="Looks like a bank statement."),
            BankStatementFields(
                bank_name="Harborview Savings Bank",
                account_holder_name="Jordan Ellis",
                statement_period_start="2025-01-01",
                statement_period_end="2025-12-31",
                total_interest_earned=184.32,
            ),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-bank"}}

    async for event in graph.astream(
        {"file_path": "stmt.pdf", "original_filename": "stmt.pdf", "client_id": "jordan-ellis"},
        config=config,
        stream_mode="updates",
    ):
        if "extract_bank_statement" in event:
            assert event["extract_bank_statement"]["extraction_schema_used"] == "BankStatementFields"
