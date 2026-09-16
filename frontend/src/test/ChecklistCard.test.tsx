import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ClientDetail } from "../api/types";
import { ChecklistCard } from "../components/ChecklistCard";

// Shaped after the seeded example client `morgan-alvarez`
// (sample-data/organizer/morgan_alvarez.json): four expected documents, but
// only the Fenwick Logistics W-2, the Alvarez Family Holdings K-1, and the
// Crestline Investments 1099-DIV have arrived -- the second W-2, from
// Northbridge Analytics, is still missing.
const MORGAN_ALVAREZ_INCOMPLETE: ClientDetail = {
  id: "morgan-alvarez",
  name: "Morgan Alvarez",
  tax_year: 2025,
  documents_expected: 4,
  documents_received: 3,
  completeness_status: "incomplete",
  notes: "Changed jobs mid-year.",
  expected_documents: [
    { doc_type: "W-2", counterparty_name: "Fenwick Logistics Inc", notes: "Employer January-June 2025." },
    { doc_type: "W-2", counterparty_name: "Northbridge Analytics LLC", notes: "Employer July-December 2025 (new job)." },
    { doc_type: "K-1", counterparty_name: "Alvarez Family Holdings LLC", notes: "Family investment partnership." },
    { doc_type: "1099-DIV", counterparty_name: "Crestline Investments", notes: "Taxable brokerage account dividends." },
  ],
  documents: [
    {
      id: "doc-1",
      client_id: "morgan-alvarez",
      original_filename: "W2_Fenwick_Logistics_Inc_Morgan_Alvarez.pdf",
      doc_type: "W-2",
      classification_confidence: 0.96,
      status: "completed",
      final_status: "added_to_organizer",
      flagged: false,
      created_at: "2026-01-05T10:00:00Z",
      updated_at: "2026-01-05T10:06:00Z",
    },
    {
      id: "doc-2",
      client_id: "morgan-alvarez",
      original_filename: "K1_Alvarez_Family_Holdings_LLC_Morgan_Alvarez.pdf",
      doc_type: "K-1",
      classification_confidence: 0.92,
      status: "completed",
      final_status: "added_to_organizer",
      flagged: false,
      created_at: "2026-01-06T10:00:00Z",
      updated_at: "2026-01-06T10:06:00Z",
    },
    {
      id: "doc-3",
      client_id: "morgan-alvarez",
      original_filename: "1099DIV_Crestline_Investments_Morgan_Alvarez.pdf",
      doc_type: "1099-DIV",
      classification_confidence: 0.95,
      status: "completed",
      final_status: "added_to_organizer",
      flagged: false,
      created_at: "2026-01-07T10:00:00Z",
      updated_at: "2026-01-07T10:06:00Z",
    },
  ],
};

// Shaped after the seeded example client `jordan-ellis`
// (sample-data/organizer/jordan_ellis.json): all three expected documents
// have arrived.
const JORDAN_ELLIS_COMPLETE: ClientDetail = {
  id: "jordan-ellis",
  name: "Jordan Ellis",
  tax_year: 2025,
  documents_expected: 3,
  documents_received: 3,
  completeness_status: "complete",
  notes: "Single filer.",
  expected_documents: [
    { doc_type: "W-2", counterparty_name: "Cascade Retail Group", notes: "Primary employer." },
    { doc_type: "1099-NEC", counterparty_name: "Bluepeak Design Studio", notes: "Freelance work." },
    { doc_type: "1099-INT", counterparty_name: "Harborview Savings Bank", notes: "Savings interest." },
  ],
  documents: [
    {
      id: "doc-4",
      client_id: "jordan-ellis",
      original_filename: "W2_Cascade_Retail_Group_Jordan_Ellis.pdf",
      doc_type: "W-2",
      classification_confidence: 0.97,
      status: "completed",
      final_status: "added_to_organizer",
      flagged: false,
      created_at: "2026-01-05T10:00:00Z",
      updated_at: "2026-01-05T10:06:00Z",
    },
    {
      id: "doc-5",
      client_id: "jordan-ellis",
      original_filename: "1099NEC_Bluepeak_Design_Studio_Jordan_Ellis.pdf",
      doc_type: "1099-NEC",
      classification_confidence: 0.94,
      status: "completed",
      final_status: "added_to_organizer",
      flagged: false,
      created_at: "2026-01-06T10:00:00Z",
      updated_at: "2026-01-06T10:06:00Z",
    },
    {
      id: "doc-6",
      client_id: "jordan-ellis",
      original_filename: "1099INT_Harborview_Savings_Bank_Jordan_Ellis.pdf",
      doc_type: "1099-INT",
      classification_confidence: 0.93,
      status: "completed",
      final_status: "added_to_organizer",
      flagged: false,
      created_at: "2026-01-07T10:00:00Z",
      updated_at: "2026-01-07T10:06:00Z",
    },
  ],
};

describe("ChecklistCard", () => {
  it("shows a missing-document warning for the expected item with no matching completed document", () => {
    render(<ChecklistCard client={MORGAN_ALVAREZ_INCOMPLETE} />);

    // The three received items show a "Received" badge.
    expect(screen.getAllByText(/^received$/i)).toHaveLength(3);
    // The Northbridge Analytics W-2 is still missing.
    expect(screen.getByText(/northbridge analytics llc/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^missing$/i)).toHaveLength(1);
    expect(screen.getByText(/1 missing/i)).toBeInTheDocument();
  });

  it("does not flag the Fenwick Logistics W-2 as missing just because another W-2 is also expected", () => {
    render(<ChecklistCard client={MORGAN_ALVAREZ_INCOMPLETE} />);

    const fenwickRow = screen.getByText(/fenwick logistics inc/i).closest("li");
    expect(fenwickRow).not.toBeNull();
    expect(fenwickRow).toHaveTextContent(/received/i);
  });

  it("shows Complete with no missing items when every expected document has arrived", () => {
    render(<ChecklistCard client={JORDAN_ELLIS_COMPLETE} />);

    expect(screen.getByText(/^complete$/i)).toBeInTheDocument();
    expect(screen.queryByText(/^missing$/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^received$/i)).toHaveLength(3);
  });
});
