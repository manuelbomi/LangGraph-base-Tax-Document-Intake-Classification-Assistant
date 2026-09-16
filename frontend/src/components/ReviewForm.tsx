import { useState } from "react";

import type { HumanDecisionRequest, InterruptPayload } from "../api/types";
import { labelizeFieldKey } from "../lib/fields";
import { FlagsList } from "./FlagsList";

interface ReviewFormProps {
  interrupt: InterruptPayload;
  onDecision: (decision: HumanDecisionRequest) => void;
  submitting?: boolean;
}

function toEditableStrings(fields: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, value === null || value === undefined ? "" : String(value)]),
  );
}

/** Human-in-the-loop review: shows the classification + extracted fields as
 * an editable form (the field set varies by doc_type, so rows are generated
 * generically from whatever keys `extracted_fields` has) alongside the
 * cross-check flags, with Approve / Correct-and-Approve / Reject actions
 * that call `onDecision` -- the page wires that to
 * `POST /documents/{id}/resume`. Nothing is added to the client's organizer
 * without one of these three explicit decisions. */
export function ReviewForm({ interrupt, onDecision, submitting }: ReviewFormProps) {
  const [fieldValues, setFieldValues] = useState<Record<string, string>>(() =>
    toEditableStrings(interrupt.extracted_fields),
  );
  const [feedback, setFeedback] = useState("");

  const updateField = (key: string, value: string) => {
    setFieldValues((prev) => ({ ...prev, [key]: value }));
  };

  const correctedFields = (): Record<string, unknown> => {
    const original = interrupt.extracted_fields;
    const result: Record<string, unknown> = {};
    for (const [key, strValue] of Object.entries(fieldValues)) {
      const originalValue = original[key];
      if (typeof originalValue === "number") {
        const parsed = Number(strValue);
        result[key] = Number.isNaN(parsed) ? originalValue : parsed;
      } else {
        result[key] = strValue;
      }
    }
    return result;
  };

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-amber-700">
        Human review required
      </h3>
      <p className="mb-1 text-sm text-amber-900">
        This document was classified as <strong>{interrupt.doc_type}</strong>
        {interrupt.classification_confidence !== undefined &&
          ` (${(interrupt.classification_confidence * 100).toFixed(0)}% confidence)`}
        . Confirm or correct the fields below, then Approve, Correct &amp; Approve, or Reject. Nothing
        is added to the client's organizer until you decide.
      </p>
      {(interrupt.classification_reasoning || interrupt.extraction_schema_used) && (
        <p className="mb-4 text-xs text-amber-800">
          {interrupt.classification_reasoning}
          {interrupt.extraction_schema_used && <> &middot; Schema used: {interrupt.extraction_schema_used}</>}
        </p>
      )}

      <div className="mb-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-amber-200 bg-white p-4">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
            Extracted fields (editable)
          </h4>
          <div className="space-y-2 text-sm">
            {Object.entries(fieldValues).map(([key, value]) => {
              const label = labelizeFieldKey(key);
              return (
                <label className="block" key={key}>
                  <span className="text-xs text-slate-500">{label}</span>
                  <input
                    className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                    value={value}
                    onChange={(e) => updateField(key, e.target.value)}
                    aria-label={label}
                  />
                </label>
              );
            })}
          </div>
        </div>

        <div className="space-y-3">
          <FlagsList flags={interrupt.cross_check_flags} />
        </div>
      </div>

      <textarea
        className="mb-3 w-full rounded-md border border-slate-300 p-2 text-sm"
        rows={2}
        placeholder="Reviewer note (optional) -- why you approved, corrected, or rejected this"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        aria-label="Reviewer note"
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={submitting}
          onClick={() => onDecision({ decision: "approve", feedback })}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => onDecision({ decision: "correct", feedback, corrected_fields: correctedFields() })}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Correct &amp; Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => onDecision({ decision: "reject", feedback })}
          className="rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
