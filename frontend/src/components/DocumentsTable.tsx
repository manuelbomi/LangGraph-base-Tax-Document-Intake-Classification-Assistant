import { Link } from "react-router-dom";

import type { DocumentSummary } from "../api/types";

function statusBadge(doc: DocumentSummary): { label: string; className: string } {
  if (doc.status === "rejected") return { label: "Rejected", className: "bg-rose-100 text-rose-800" };
  if (doc.status === "error") return { label: "Error", className: "bg-rose-100 text-rose-800" };
  if (doc.status === "awaiting_human") {
    return { label: "Awaiting review", className: "bg-amber-100 text-amber-800" };
  }
  if (doc.status === "pending" || doc.status === "running") {
    return { label: "Processing", className: "bg-brand-100 text-brand-800" };
  }
  if (doc.flagged) return { label: "Flagged", className: "bg-amber-100 text-amber-800" };
  return { label: "Clean", className: "bg-emerald-100 text-emerald-800" };
}

const FINAL_STATUS_LABEL: Record<string, string> = {
  added_to_organizer: "Added to organizer",
  corrected_and_added: "Added to organizer (corrected)",
  rejected: "Rejected",
};

/** Table of every document processed for a client -- type, status,
 * confidence, flagged badge, final_status, and timestamps -- each row
 * linking to the per-document detail view. */
export function DocumentsTable({ documents }: { documents: DocumentSummary[] }) {
  if (documents.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        No documents processed for this client yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Document</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Flags</th>
            <th className="px-3 py-2">Final status</th>
            <th className="px-3 py-2">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {documents.map((doc) => {
            const badge = statusBadge(doc);
            return (
              <tr key={doc.id} className="hover:bg-slate-50">
                <td className="px-3 py-2">
                  <Link to={`/documents/${doc.id}`} className="font-medium text-brand-700 hover:underline">
                    {doc.original_filename}
                  </Link>
                </td>
                <td className="px-3 py-2 text-slate-600">{doc.doc_type}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${badge.className}`}>
                    {badge.label}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {(doc.classification_confidence * 100).toFixed(0)}%
                </td>
                <td className="px-3 py-2">
                  {doc.flagged ? (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                      Flagged
                    </span>
                  ) : (
                    <span className="text-slate-400">-</span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {doc.final_status ? (FINAL_STATUS_LABEL[doc.final_status] ?? doc.final_status) : "-"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-400">
                  {new Date(doc.updated_at).toLocaleString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
