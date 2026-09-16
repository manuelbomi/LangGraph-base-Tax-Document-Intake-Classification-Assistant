import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getDocument } from "../api/client";
import { DocumentViewer } from "../components/DocumentViewer";
import { ExtractedFieldsCard } from "../components/ExtractedFieldsCard";
import { FlagsList } from "../components/FlagsList";

const FINAL_STATUS_LABEL: Record<string, string> = {
  added_to_organizer: "Added to organizer",
  corrected_and_added: "Added to organizer (corrected)",
  rejected: "Rejected",
};

/** Per-document detail view: the original source file alongside its
 * extracted fields, cross-check flags, and full trace. Reached from the
 * organizer's documents table (and from a just-finished upload run). */
export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const documentId = id ?? null;

  const {
    data: doc,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId as string),
    enabled: documentId !== null,
  });

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <Link to="/organizer" className="text-sm text-brand-600 hover:underline">
          &larr; Back to client organizer
        </Link>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading document...</p>}
      {isError && <p className="text-sm text-rose-600">{(error as Error).message}</p>}

      {doc && (
        <>
          <div>
            <h2 className="text-xl font-semibold text-slate-900">{doc.original_filename}</h2>
            <p className="text-sm text-slate-500">
              <span className="font-medium text-slate-700">{doc.doc_type}</span> &middot; status{" "}
              {doc.status.replace("_", " ")} &middot; confidence{" "}
              {(doc.classification_confidence * 100).toFixed(0)}%
              {doc.final_status && (
                <> &middot; {FINAL_STATUS_LABEL[doc.final_status] ?? doc.final_status}</>
              )}
            </p>
            {doc.error && <p className="mt-1 text-sm text-rose-600">{doc.error}</p>}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Source document
              </h3>
              <DocumentViewer documentId={doc.id} filename={doc.original_filename} />
            </div>
            <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
              <div>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Extracted fields
                </h3>
                {doc.extraction_schema_used && (
                  <p className="mb-2 text-xs text-slate-400">Schema used: {doc.extraction_schema_used}</p>
                )}
                <ExtractedFieldsCard fields={doc.extracted_fields} />
              </div>
              <FlagsList flags={doc.cross_check_flags} />
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Trace
            </h3>
            <ul className="space-y-1 text-xs text-slate-500">
              {doc.trace.map((t, i) => (
                <li key={`${t.node}-${i}`}>
                  <span className="font-mono text-slate-400">
                    {new Date(t.timestamp).toLocaleString()}
                  </span>{" "}
                  <span className="font-semibold text-slate-600">{t.node}</span>: {t.summary}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
