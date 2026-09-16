/** Shared helpers for rendering the dynamic, doc_type-dependent
 * `extracted_fields` dict generically (its keys differ completely between a
 * W-2 and a K-1 -- see `backend/app/graph/extraction_schema.py`). */

/** "box1_wages" -> "Box1 Wages"; "employer_ein" -> "Employer Ein". */
export function labelizeFieldKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

const CURRENCY_HINT = /box|income|wages|amount|interest|dividend|compensation/i;

/** Formats a raw extracted-field value for display: currency for numeric
 * fields whose key looks like a dollar amount (any IRS box number, or a
 * key mentioning income/wages/amount/interest/dividend/compensation),
 * plain formatted numbers otherwise, and the value's string form for
 * everything else. */
export function formatFieldValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    if (CURRENCY_HINT.test(key)) {
      return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
    }
    return value.toLocaleString("en-US");
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
