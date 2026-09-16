import type { CrossCheckFlag, TraceEventOut } from "../api/types";
import { ExtractedFieldsCard } from "./ExtractedFieldsCard";
import { FlagsList } from "./FlagsList";

interface NodePanelProps {
  docType: string | null;
  classificationConfidence: number | null;
  classificationReasoning: string | null;
  extractionSchemaUsed: string | null;
  extractedFields: Record<string, unknown>;
  crossCheckFlags: CrossCheckFlag[];
  trace: TraceEventOut[];
}

/** Side panel rendering each node's intermediate output as it streams in:
 * classification + confidence from `classify`, extracted fields from
 * whichever `extract_*` node ran, flags from `cross_check`, and the
 * running trace log. */
export function NodePanel({
  docType,
  classificationConfidence,
  classificationReasoning,
  extractionSchemaUsed,
  extractedFields,
  crossCheckFlags,
  trace,
}: NodePanelProps) {
  const hasExtractedFields = Object.keys(extractedFields).length > 0;

  return (
    <div className="flex h-[560px] flex-col gap-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Live node output</h3>

      {docType && (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-slate-800">Classification</h4>
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-800">{docType}</span>
            {classificationConfidence !== null &&
              ` (${(classificationConfidence * 100).toFixed(0)}% confidence)`}
          </p>
          {classificationReasoning && (
            <p className="mt-1 text-xs text-slate-500">{classificationReasoning}</p>
          )}
          {extractionSchemaUsed && (
            <p className="mt-1 text-xs text-slate-400">Extraction schema: {extractionSchemaUsed}</p>
          )}
        </section>
      )}

      {hasExtractedFields && (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-slate-800">Extracted fields</h4>
          <ExtractedFieldsCard fields={extractedFields} />
        </section>
      )}

      <FlagsList flags={crossCheckFlags} />

      <section className="mt-auto">
        <h4 className="mb-1 text-sm font-semibold text-slate-800">Trace</h4>
        <ul className="space-y-1 text-xs text-slate-500">
          {trace.map((t, i) => (
            <li key={`${t.node}-${i}`}>
              <span className="font-mono text-slate-400">{new Date(t.timestamp).toLocaleTimeString()}</span>{" "}
              <span className="font-semibold text-slate-600">{t.node}</span>: {t.summary}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
