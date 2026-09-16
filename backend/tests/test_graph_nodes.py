"""Unit tests for individual graph nodes and routing functions.

Everything here is mocked: LLM calls go through `FakeChatModel` (see
conftest.py), and organizer (Postgres) I/O is monkeypatched via the
`no_organizer_io` fixture. No network, no Postgres, no API key spend.
"""
from __future__ import annotations

from app.graph import nodes
from app.graph.extraction_schema import (
    DocClassification,
    Form1099NECFields,
    Form1099INTFields,
    K1Fields,
    W2Fields,
)


# ---------------------------------------------------------------------
# ingest_node
# ---------------------------------------------------------------------
async def test_ingest_node_pdf(monkeypatch):
    monkeypatch.setattr(nodes, "detect_file_kind", lambda p: "pdf")
    monkeypatch.setattr(nodes, "extract_pdf_text", lambda p: "W-2 WAGE AND TAX STATEMENT " * 5)

    result = await nodes.ingest_node({"file_path": "some.pdf"})

    assert result["used_vision"] is False
    assert "raw_text" in result
    assert len(result["trace"]) == 1


async def test_ingest_node_image(monkeypatch):
    monkeypatch.setattr(nodes, "detect_file_kind", lambda p: "image")
    monkeypatch.setattr(nodes, "encode_image_base64", lambda p: "YmFzZTY0Zm9v")
    monkeypatch.setattr(nodes, "image_mime_type", lambda p: "image/png")

    result = await nodes.ingest_node({"file_path": "some.png"})

    assert result["used_vision"] is True
    assert result["image_base64"] == "YmFzZTY0Zm9v"
    assert result["mime_type"] == "image/png"


# ---------------------------------------------------------------------
# classify_node / route_after_classify
# ---------------------------------------------------------------------
async def test_classify_node_text_path(fake_chat_model, fake_prompts):
    fake_chat_model([DocClassification(doc_type="W-2", confidence=0.94, reasoning="Has W-2 boxes 1-20.")])

    result = await nodes.classify_node({"used_vision": False, "raw_text": "some text"})

    assert result["doc_type"] == "W-2"
    assert result["classification_confidence"] == 0.94
    assert result["trace"][0]["node"] == "classify"


async def test_classify_node_defaults_unknown_type_to_other(fake_chat_model, fake_prompts):
    fake_chat_model([DocClassification(doc_type="something-weird", confidence=0.5, reasoning="not sure")])

    result = await nodes.classify_node({"used_vision": False, "raw_text": "garbled"})

    assert result["doc_type"] == "other-unknown"


async def test_classify_node_handles_failure(fake_chat_model, fake_prompts):
    fake_chat_model([RuntimeError("model refused")])

    result = await nodes.classify_node({"used_vision": False, "raw_text": "garbled"})

    assert result["doc_type"] == "other-unknown"
    assert result["classification_confidence"] == 0.0


def test_route_after_classify():
    assert nodes.route_after_classify({"doc_type": "W-2"}) == "extract_w2"
    assert nodes.route_after_classify({"doc_type": "1099-NEC"}) == "extract_1099nec"
    assert nodes.route_after_classify({"doc_type": "1099-INT"}) == "extract_1099int"
    assert nodes.route_after_classify({"doc_type": "1099-DIV"}) == "extract_1099div"
    assert nodes.route_after_classify({"doc_type": "K-1"}) == "extract_k1"
    assert nodes.route_after_classify({"doc_type": "bank-statement"}) == "extract_bank_statement"
    assert nodes.route_after_classify({"doc_type": "other-unknown"}) == "extract_other"
    assert nodes.route_after_classify({"doc_type": "nonsense"}) == "extract_other"


# ---------------------------------------------------------------------
# extract_*_node
# ---------------------------------------------------------------------
async def test_extract_w2_node_text_path(fake_chat_model, fake_prompts):
    fields = W2Fields(
        employer_name="Cascade Retail Group",
        employer_ein="84-1234567",
        employee_name="Jordan Ellis",
        employee_ssn="412-34-5678",
        tax_year=2025,
        box1_wages=28450.0,
        box2_federal_tax_withheld=2100.0,
    )
    fake_chat_model([fields])

    result = await nodes.extract_w2_node({"used_vision": False, "raw_text": "w2 text"})

    assert result["extracted_fields"]["employer_name"] == "Cascade Retail Group"
    assert result["extraction_schema_used"] == "W2Fields"
    assert result["trace"][0]["node"] == "extract_w2"


async def test_extract_1099nec_node_vision_path(fake_chat_model, fake_prompts):
    fields = Form1099NECFields(
        payer_name="Bluepeak Design Studio",
        recipient_name="Jordan Ellis",
        tax_year=2025,
        box1_nonemployee_compensation=6200.0,
    )
    fake_chat_model([fields])

    result = await nodes.extract_1099nec_node(
        {"used_vision": True, "image_base64": "abc123", "mime_type": "image/png"}
    )

    assert result["extracted_fields"]["payer_name"] == "Bluepeak Design Studio"
    assert result["extraction_schema_used"] == "Form1099NECFields"


async def test_extract_1099int_node_handles_failure(fake_chat_model, fake_prompts):
    fake_chat_model([RuntimeError("model refused to comply")])

    result = await nodes.extract_1099int_node({"used_vision": False, "raw_text": "garbled text"})

    assert result["extracted_fields"] == {}
    assert "failed" in result["trace"][0]["summary"].lower()


async def test_extract_k1_node(fake_chat_model, fake_prompts):
    fields = K1Fields(
        partnership_name="Alvarez Family Holdings LLC",
        partner_name="Morgan Alvarez",
        tax_year=2025,
        box1_ordinary_business_income=3200.0,
    )
    fake_chat_model([fields])

    result = await nodes.extract_k1_node({"used_vision": False, "raw_text": "k1 text"})

    assert result["extracted_fields"]["partnership_name"] == "Alvarez Family Holdings LLC"


# ---------------------------------------------------------------------
# cross_check_node (deterministic, organizer I/O mocked)
# ---------------------------------------------------------------------
async def test_cross_check_node_reports_flags(no_organizer_io):
    no_organizer_io.cross_check_flags = [
        {"code": "missing_expected_document", "severity": "warning", "message": "...", "details": {}}
    ]

    result = await nodes.cross_check_node(
        {"client_id": "jordan-ellis", "doc_type": "W-2", "extracted_fields": {"employer_name": "Cascade Retail Group"}}
    )

    assert len(result["cross_check_flags"]) == 1
    assert no_organizer_io.cross_check_calls == [("jordan-ellis", "W-2", {"employer_name": "Cascade Retail Group"})]


async def test_cross_check_node_clean(no_organizer_io):
    no_organizer_io.cross_check_flags = []

    result = await nodes.cross_check_node({"client_id": "jordan-ellis", "doc_type": "W-2", "extracted_fields": {}})

    assert result["cross_check_flags"] == []


# ---------------------------------------------------------------------
# finalize_node
# ---------------------------------------------------------------------
async def test_finalize_node_approved(no_organizer_io):
    no_organizer_io.completeness_result = {
        "documents_expected": 3,
        "documents_received": 3,
        "completeness_status": "complete",
    }

    result = await nodes.finalize_node(
        {
            "client_id": "jordan-ellis",
            "doc_type": "1099-NEC",
            "extracted_fields": {"payer_name": "Bluepeak Design Studio"},
            "human_decision": "approve",
        }
    )

    assert result["final_status"] == "added_to_organizer"
    assert result["status"] == "completed"


async def test_finalize_node_corrected(no_organizer_io):
    result = await nodes.finalize_node(
        {"client_id": "jordan-ellis", "doc_type": "W-2", "extracted_fields": {}, "human_decision": "correct"}
    )
    assert result["final_status"] == "corrected_and_added"
    assert result["status"] == "completed"


async def test_finalize_node_rejected(no_organizer_io):
    result = await nodes.finalize_node(
        {"client_id": "jordan-ellis", "doc_type": "W-2", "extracted_fields": {}, "human_decision": "reject"}
    )
    assert result["final_status"] == "rejected"
    assert result["status"] == "rejected"
