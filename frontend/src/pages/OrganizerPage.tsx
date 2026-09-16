import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { getClient, listClients } from "../api/client";
import { ChecklistCard } from "../components/ChecklistCard";
import { DocumentsTable } from "../components/DocumentsTable";

export function OrganizerPage() {
  const [clientId, setClientId] = useState("");

  const { data: clientsData } = useQuery({ queryKey: ["clients"], queryFn: listClients });

  // Default to the first client once the list loads, so this page works
  // standing alone against the seeded example clients without any action.
  useEffect(() => {
    if (!clientId && clientsData && clientsData.clients.length > 0) {
      setClientId(clientsData.clients[0].id);
    }
  }, [clientId, clientsData]);

  const {
    data: client,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["client", clientId],
    queryFn: () => getClient(clientId),
    enabled: clientId !== "",
  });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Client organizer / example analyses</h2>
        <p className="text-sm text-slate-500">
          Pick a client to see their expected-vs-received document checklist and every document
          processed for them, including the seeded example analyses.
        </p>
      </div>

      <label className="block text-sm">
        <span className="mb-1 block font-medium text-slate-700">Client</span>
        <select
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          aria-label="Choose a client"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm sm:w-80"
        >
          <option value="">Choose a client...</option>
          {clientsData?.clients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.tax_year})
            </option>
          ))}
        </select>
      </label>

      {isLoading && <p className="text-sm text-slate-500">Loading client...</p>}
      {isError && <p className="text-sm text-rose-600">{(error as Error).message}</p>}

      {client && (
        <>
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4">
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                {client.name} &middot; Tax year {client.tax_year}
              </h3>
              {client.notes && <p className="mt-1 text-sm text-slate-500">{client.notes}</p>}
              <p className="mt-1 text-xs text-slate-400">
                {client.documents_received} of {client.documents_expected} expected documents received
              </p>
            </div>
            <span
              className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
                client.completeness_status === "complete"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-amber-100 text-amber-800"
              }`}
            >
              {client.completeness_status === "complete" ? "Complete" : "Incomplete"}
            </span>
          </div>

          <ChecklistCard client={client} />

          <div>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Documents
            </h3>
            <DocumentsTable documents={client.documents} />
          </div>
        </>
      )}
    </div>
  );
}
