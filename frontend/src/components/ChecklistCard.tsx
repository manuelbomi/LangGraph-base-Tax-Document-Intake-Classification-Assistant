import type { ClientDetail } from "../api/types";
import { buildChecklist } from "../lib/checklist";

/** Compares a client's `expected_documents` checklist against what has
 * actually been received (a completed document whose doc_type and filename
 * match), and visually flags anything still missing -- the key
 * "missing document" warning UI for the organizer. */
export function ChecklistCard({ client }: { client: ClientDetail }) {
  const items = buildChecklist(client.expected_documents, client.documents);
  const missingCount = items.filter((item) => !item.received).length;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Expected documents checklist
        </h3>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${
            missingCount === 0 ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
          }`}
        >
          {missingCount === 0 ? "Complete" : `${missingCount} missing`}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-slate-500">No expected documents on file for this client.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li
              key={i}
              className={`flex items-start gap-3 rounded-lg border px-3 py-2 text-sm ${
                item.received ? "border-emerald-200 bg-emerald-50" : "border-amber-300 bg-amber-50"
              }`}
            >
              <span
                className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  item.received ? "bg-emerald-600 text-white" : "bg-amber-500 text-white"
                }`}
              >
                {item.received ? "Received" : "Missing"}
              </span>
              <span className="flex-1">
                <span className="font-medium text-slate-800">{item.expected.doc_type}</span>
                {item.expected.counterparty_name && (
                  <span className="text-slate-600"> &middot; {item.expected.counterparty_name}</span>
                )}
                {item.expected.notes && <p className="text-xs text-slate-500">{item.expected.notes}</p>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
