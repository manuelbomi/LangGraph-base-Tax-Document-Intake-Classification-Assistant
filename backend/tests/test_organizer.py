"""Unit tests for the deterministic cross-check / completeness logic in
`app/tools/organizer.py`. Uses a fake SQLAlchemy session (no real Postgres)
returning canned `Client`/`Document`-shaped rows."""
from __future__ import annotations

from app.tools import organizer


class _FakeClient:
    def __init__(self, id, name="Test Client", tax_year=2025, expected_documents=None):
        self.id = id
        self.name = name
        self.tax_year = tax_year
        self.expected_documents = expected_documents or []


class _FakeDocument:
    def __init__(self, id, doc_type, extracted_fields, status="completed"):
        self.id = id
        self.doc_type = doc_type
        self.extracted_fields = extracted_fields
        self.status = status
        self.documents_expected = 0
        self.documents_received = 0
        self.completeness_status = "incomplete"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, client, documents):
        self._client = client
        self._documents = documents

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, _model, _id):
        return self._client

    def execute(self, _stmt):
        return _FakeResult(self._documents)

    def commit(self):
        pass


def _patch(monkeypatch, client, documents):
    monkeypatch.setattr(organizer, "SessionLocal", lambda: _FakeSession(client, documents))


def test_name_similarity_ignores_case_punctuation_and_suffixes():
    assert organizer.name_similarity("Cascade Retail Group", "cascade retail group inc") > 0.95


def test_name_similarity_low_for_unrelated_names():
    assert organizer.name_similarity("Cascade Retail Group", "Crestline Investments") < 0.5


def test_get_counterparty_w2():
    name, tax_id = organizer.get_counterparty("W-2", {"employer_name": "Cascade Retail Group", "employer_ein": "84-1234567"})
    assert name == "Cascade Retail Group"
    assert tax_id == "84-1234567"


def test_cross_check_flags_missing_expected_documents(monkeypatch):
    client = _FakeClient(
        "jordan-ellis",
        expected_documents=[
            {"doc_type": "W-2", "counterparty_name": "Cascade Retail Group"},
            {"doc_type": "1099-NEC", "counterparty_name": "Bluepeak Design Studio"},
        ],
    )
    _patch(monkeypatch, client, [])  # nothing received yet

    flags = organizer.cross_check_document("jordan-ellis", "W-2", {"employer_name": "Cascade Retail Group"})

    codes = [f["code"] for f in flags]
    assert "missing_expected_document" in codes
    # the W-2 itself is satisfied by this very document, so only the NEC is missing
    missing = [f for f in flags if f["code"] == "missing_expected_document"]
    assert len(missing) == 1
    assert missing[0]["details"]["expected"]["doc_type"] == "1099-NEC"


def test_cross_check_flags_duplicate_document(monkeypatch):
    client = _FakeClient("morgan-alvarez", expected_documents=[{"doc_type": "W-2", "counterparty_name": "Fenwick Logistics Inc"}])
    existing = _FakeDocument("doc-1", "W-2", {"employer_name": "Fenwick Logistics Inc", "employer_ein": "27-9876543"})
    _patch(monkeypatch, client, [existing])

    flags = organizer.cross_check_document(
        "morgan-alvarez", "W-2", {"employer_name": "Fenwick Logistics Inc", "employer_ein": "27-9876543"}
    )

    codes = [f["code"] for f in flags]
    assert "duplicate_document" in codes


def test_cross_check_flags_unexpected_document(monkeypatch):
    client = _FakeClient("jordan-ellis", expected_documents=[{"doc_type": "W-2", "counterparty_name": "Cascade Retail Group"}])
    existing = _FakeDocument("doc-1", "W-2", {"employer_name": "Cascade Retail Group"})
    _patch(monkeypatch, client, [existing])

    flags = organizer.cross_check_document(
        "jordan-ellis", "bank-statement", {"bank_name": "Harborview Savings Bank"}
    )

    codes = [f["code"] for f in flags]
    assert "unexpected_document" in codes
    assert "missing_expected_document" not in codes


def test_cross_check_flags_invalid_ssn_and_negative_amount(monkeypatch):
    client = _FakeClient("jordan-ellis", expected_documents=[])
    _patch(monkeypatch, client, [])

    flags = organizer.cross_check_document(
        "jordan-ellis",
        "W-2",
        {"employer_name": "Cascade Retail Group", "employee_ssn": "not-a-ssn", "box1_wages": -100.0},
    )

    codes = [f["code"] for f in flags]
    assert "invalid_ssn_format" in codes
    assert "negative_amount" in codes


def test_cross_check_flags_tax_year_mismatch(monkeypatch):
    client = _FakeClient("jordan-ellis", tax_year=2025, expected_documents=[])
    _patch(monkeypatch, client, [])

    flags = organizer.cross_check_document("jordan-ellis", "W-2", {"employer_name": "X", "tax_year": 2024})

    codes = [f["code"] for f in flags]
    assert "tax_year_mismatch" in codes


def test_cross_check_clean_document_no_flags(monkeypatch):
    client = _FakeClient("jordan-ellis", tax_year=2025, expected_documents=[{"doc_type": "W-2", "counterparty_name": "Cascade Retail Group"}])
    _patch(monkeypatch, client, [])

    flags = organizer.cross_check_document(
        "jordan-ellis",
        "W-2",
        {
            "employer_name": "Cascade Retail Group",
            "employer_ein": "84-1234567",
            "employee_ssn": "412-34-5678",
            "tax_year": 2025,
            "box1_wages": 28450.0,
        },
    )

    assert flags == []


def test_recompute_client_completeness(monkeypatch):
    client = _FakeClient(
        "jordan-ellis",
        expected_documents=[
            {"doc_type": "W-2", "counterparty_name": "Cascade Retail Group"},
            {"doc_type": "1099-NEC", "counterparty_name": "Bluepeak Design Studio"},
        ],
    )
    existing = _FakeDocument("doc-1", "W-2", {"employer_name": "Cascade Retail Group"})
    _patch(monkeypatch, client, [existing])

    result = organizer.recompute_client_completeness("jordan-ellis")

    assert result["documents_expected"] == 2
    assert result["documents_received"] == 1
    assert result["completeness_status"] == "incomplete"
    assert client.documents_received == 1
