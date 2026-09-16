import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { InterruptPayload } from "../api/types";
import { ReviewForm } from "../components/ReviewForm";

const INTERRUPT: InterruptPayload = {
  original_filename: "W2_Cascade_Retail_Group_Jordan_Ellis.pdf",
  doc_type: "W-2",
  classification_confidence: 0.97,
  classification_reasoning: "Document has W-2 box labels and an employer EIN.",
  extraction_schema_used: "W2Fields",
  extracted_fields: {
    employer_name: "Cascade Retail Group",
    employer_ein: "12-3456789",
    employee_name: "Jordan Ellis",
    tax_year: 2025,
    box1_wages: 18450.32,
    box2_federal_tax_withheld: 1200.5,
  },
  cross_check_flags: [
    {
      code: "counterparty_matched",
      severity: "info",
      message: "Matched expected employer 'Cascade Retail Group'.",
      details: {},
    },
  ],
};

describe("ReviewForm", () => {
  it("pre-fills the form with the extracted fields", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);

    expect(screen.getByLabelText(/^employer name$/i)).toHaveValue("Cascade Retail Group");
    expect(screen.getByLabelText(/^box1 wages$/i)).toHaveValue("18450.32");
  });

  it("calls onDecision with approve and no corrected fields when Approve is clicked", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(onDecision).toHaveBeenCalledWith({ decision: "approve", feedback: "" });
  });

  it("calls onDecision with reject and the reviewer note as feedback", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.type(screen.getByLabelText(/reviewer note/i), "Wrong employer, rejecting.");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    expect(onDecision).toHaveBeenCalledWith({ decision: "reject", feedback: "Wrong employer, rejecting." });
  });

  it("sends edited fields as corrected_fields (with numeric coercion) when Correct & Approve is clicked", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    const wagesInput = screen.getByLabelText(/^box1 wages$/i);
    await user.clear(wagesInput);
    await user.type(wagesInput, "19000.00");
    await user.click(screen.getByRole("button", { name: /correct & approve/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: "correct",
        corrected_fields: expect.objectContaining({
          employer_name: "Cascade Retail Group",
          box1_wages: 19000,
        }),
      }),
    );
  });

  it("renders the cross-check flags", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);

    expect(screen.getByText(/matched expected employer/i)).toBeInTheDocument();
  });

  it("disables the buttons while submitting", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} submitting />);

    expect(screen.getByRole("button", { name: /^approve$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /correct & approve/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeDisabled();
  });
});
