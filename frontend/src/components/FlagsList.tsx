import type { CrossCheckFlag } from "../api/types";

const SEVERITY_LABEL: Record<string, string> = {
  error: "Error",
  warning: "Warning",
  info: "Info",
};

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={`severity-${severity} shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide`}
    >
      {SEVERITY_LABEL[severity] ?? severity}
    </span>
  );
}

/** Renders `cross_check_flags` (each `{code, severity, message, details}`)
 * as a severity-colored list -- shared by the live run view, the review
 * form, and the organizer document detail view. */
export function FlagsList({
  flags,
  title = "Cross-check flags",
  emptyMessage = "No cross-check flags -- nothing to review.",
}: {
  flags: CrossCheckFlag[];
  title?: string;
  emptyMessage?: string;
}) {
  return (
    <section>
      <h4 className="mb-2 text-sm font-semibold text-slate-800">{title}</h4>
      {flags.length === 0 ? (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800">{emptyMessage}</p>
      ) : (
        <ul className="space-y-2">
          {flags.map((flag, i) => (
            <li
              key={`${flag.code}-${i}`}
              className={`severity-${flag.severity} flex items-start gap-2 rounded-md border px-3 py-2 text-xs`}
            >
              <SeverityBadge severity={flag.severity} />
              <span className="flex-1">
                <span className="mr-1 font-mono text-[10px] opacity-70">{flag.code}</span>
                {flag.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
