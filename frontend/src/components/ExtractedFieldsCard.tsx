import { Fragment } from "react";

import { formatFieldValue, labelizeFieldKey } from "../lib/fields";

/** Read-only, generic display of `extracted_fields` -- the field set varies
 * completely by doc_type (a W-2's boxes have nothing in common with a
 * K-1's), so this just iterates whatever keys are present rather than
 * hard-coding a per-type layout. Shared by the live extraction panel, the
 * review form, and the organizer document detail view. */
export function ExtractedFieldsCard({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields);

  if (entries.length === 0) {
    return <p className="text-sm text-slate-500">No fields extracted yet.</p>;
  }

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
      {entries.map(([key, value]) => (
        <Fragment key={key}>
          <dt className="text-slate-500">{labelizeFieldKey(key)}</dt>
          <dd className="font-medium text-slate-800">{formatFieldValue(key, value)}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
