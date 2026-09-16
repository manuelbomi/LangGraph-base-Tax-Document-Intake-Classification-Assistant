import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { listClients, listSamples, resumeDocument, runSampleDocument, uploadDocument } from "../api/client";
import type { HumanDecisionRequest } from "../api/types";
import { GraphView } from "../components/GraphView";
import { NodePanel } from "../components/NodePanel";
import { ReviewForm } from "../components/ReviewForm";
import { useDocumentStream } from "../hooks/useDocumentStream";

const TERMINAL_STATUSES = new Set(["completed", "rejected", "error"]);

const FINAL_STATUS_LABEL: Record<string, string> = {
  added_to_organizer: "Added to organizer",
  corrected_and_added: "Added to organizer (corrected)",
  rejected: "Rejected",
};

export function UploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [clientId, setClientId] = useState("");
  const [selectedSample, setSelectedSample] = useState("");
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const queryClient = useQueryClient();

  const { data: clientsData } = useQuery({ queryKey: ["clients"], queryFn: listClients });
  const { data: samplesData } = useQuery({ queryKey: ["samples"], queryFn: listSamples });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDocument(file, clientId),
    onSuccess: (data) => {
      setDocumentId(data.id);
      setGeneration(0);
    },
  });

  const sampleMutation = useMutation({
    mutationFn: (sampleId: string) => runSampleDocument(sampleId, clientId),
    onSuccess: (data) => {
      setDocumentId(data.id);
      setGeneration(0);
    },
  });

  const stream = useDocumentStream(documentId, generation);

  const resumeMutation = useMutation({
    mutationFn: (payload: HumanDecisionRequest) => resumeDocument(documentId as string, payload),
    onSuccess: () => {
      setGeneration((g) => g + 1);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["client", clientId] });
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });

  const busy = uploadMutation.isPending || sampleMutation.isPending;
  const hasClient = clientId !== "";
  const isRunActive = documentId !== null;

  const suggestedSamples = samplesData?.samples.filter((s) => s.suggested_client_id === clientId) ?? [];
  const otherSamples = samplesData?.samples.filter((s) => s.suggested_client_id !== clientId) ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h2 className="mb-2 text-xl font-semibold text-slate-900">Upload &amp; process a document</h2>
        <p className="mb-4 text-sm text-slate-500">
          Pick the client this document belongs to, then either upload a file or run one of the
          bundled sample documents. The graph will classify the document, extract its fields with the
          matching IRS-form schema, cross-check it against the client's organizer, then pause for your
          review.
        </p>

        <div className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Client</span>
            <select
              value={clientId}
              onChange={(e) => {
                setClientId(e.target.value);
                setSelectedSample("");
              }}
              aria-label="Choose a client"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm sm:w-80"
            >
              <option value="">Choose a client...</option>
              {clientsData?.clients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.name} ({client.tax_year})
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const file = fileInputRef.current?.files?.[0];
              if (file && hasClient) uploadMutation.mutate(file);
            }}
            className="flex flex-col gap-3 rounded-lg border border-dashed border-slate-300 p-6"
          >
            <h3 className="text-sm font-semibold text-slate-800">Upload a document</h3>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              aria-label="Choose a document to upload"
              className="text-sm"
            />
            <button
              type="submit"
              disabled={busy || !hasClient}
              className="self-start rounded-md bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
            >
              {uploadMutation.isPending ? "Uploading..." : "Upload & process"}
            </button>
            {!hasClient && <p className="text-xs text-slate-400">Choose a client first.</p>}
            {uploadMutation.isError && (
              <p className="text-sm text-rose-600">{(uploadMutation.error as Error).message}</p>
            )}
          </form>

          <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-6">
            <h3 className="text-sm font-semibold text-slate-800">Or run a bundled sample</h3>
            <p className="text-xs text-slate-500">
              Zero-setup demo documents bundled with this repo (see <code>sample-data/README.md</code>).
              Any sample can be run for any client, but samples suggested for the selected client are
              listed first.
            </p>
            <select
              value={selectedSample}
              onChange={(e) => setSelectedSample(e.target.value)}
              aria-label="Choose a sample document"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Choose a sample document...</option>
              {suggestedSamples.length > 0 && (
                <optgroup label="Suggested for this client">
                  {suggestedSamples.map((sample) => (
                    <option key={sample.id} value={sample.id}>
                      {sample.label}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label={suggestedSamples.length > 0 ? "Other samples" : "All samples"}>
                {otherSamples.map((sample) => (
                  <option key={sample.id} value={sample.id}>
                    {sample.label}
                  </option>
                ))}
              </optgroup>
            </select>
            <button
              type="button"
              disabled={busy || !selectedSample || !hasClient}
              onClick={() => sampleMutation.mutate(selectedSample)}
              className="self-start rounded-md bg-slate-800 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-900 disabled:opacity-50"
            >
              {sampleMutation.isPending ? "Starting..." : "Run sample document"}
            </button>
            {!hasClient && <p className="text-xs text-slate-400">Choose a client first.</p>}
            {sampleMutation.isError && (
              <p className="text-sm text-rose-600">{(sampleMutation.error as Error).message}</p>
            )}
          </div>
        </div>
      </div>

      {isRunActive && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-900">Live run</h3>
            <p className="text-sm text-slate-500">
              Status:{" "}
              <span className="font-medium text-slate-700">
                {stream.status === "connecting" ? "connecting..." : stream.status.replace("_", " ")}
              </span>
              {stream.finalStatus && (
                <span className="ml-2 text-slate-500">
                  &middot; {FINAL_STATUS_LABEL[stream.finalStatus] ?? stream.finalStatus}
                </span>
              )}
            </p>
          </div>

          {stream.error && (
            <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{stream.error}</p>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <GraphView currentNode={stream.currentNode} completedNodes={stream.completedNodes} docType={stream.docType} />
            <NodePanel
              docType={stream.docType}
              classificationConfidence={stream.classificationConfidence}
              classificationReasoning={stream.classificationReasoning}
              extractionSchemaUsed={stream.extractionSchemaUsed}
              extractedFields={stream.extractedFields}
              crossCheckFlags={stream.crossCheckFlags}
              trace={stream.trace}
            />
          </div>

          {stream.status === "awaiting_human" && stream.interrupt && (
            <ReviewForm
              interrupt={stream.interrupt}
              submitting={resumeMutation.isPending}
              onDecision={(decision) => resumeMutation.mutate(decision)}
            />
          )}

          {TERMINAL_STATUSES.has(stream.status) && documentId && (
            <p className="rounded-md bg-slate-100 p-3 text-sm text-slate-600">
              Done.{" "}
              <Link to={`/documents/${documentId}`} className="font-medium text-brand-700 hover:underline">
                View this document in the client organizer
              </Link>
              .
            </p>
          )}
        </div>
      )}
    </div>
  );
}
