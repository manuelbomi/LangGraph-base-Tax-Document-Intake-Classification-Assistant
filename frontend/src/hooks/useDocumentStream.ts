import { useEffect, useState } from "react";

import { streamUrl } from "../api/client";
import type {
  CrossCheckFlag,
  DocumentStatus,
  GraphNodeName,
  InterruptPayload,
  TraceEventOut,
} from "../api/types";

export interface DocumentStreamState {
  status: DocumentStatus | "connecting";
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  docType: string | null;
  classificationConfidence: number | null;
  classificationReasoning: string | null;
  extractionSchemaUsed: string | null;
  extractedFields: Record<string, unknown>;
  crossCheckFlags: CrossCheckFlag[];
  trace: TraceEventOut[];
  interrupt: InterruptPayload | null;
  finalStatus: string | null;
  error: string | null;
}

const INITIAL_STATE: DocumentStreamState = {
  status: "connecting",
  currentNode: null,
  completedNodes: [],
  docType: null,
  classificationConfidence: null,
  classificationReasoning: null,
  extractionSchemaUsed: null,
  extractedFields: {},
  crossCheckFlags: [],
  trace: [],
  interrupt: null,
  finalStatus: null,
  error: null,
};

const TERMINAL_STATUSES = new Set(["completed", "rejected", "error"]);

/**
 * Subscribes to `GET /documents/{id}/stream` (Server-Sent Events) and folds
 * the incoming events into a single state object a component can render
 * directly -- driving both the live GraphView highlighting and the
 * classification/extraction/cross-check output panels.
 */
export function useDocumentStream(documentId: string | null, generation = 0): DocumentStreamState {
  const [state, setState] = useState<DocumentStreamState>(INITIAL_STATE);

  useEffect(() => {
    if (!documentId) {
      setState(INITIAL_STATE);
      return;
    }

    setState({ ...INITIAL_STATE, status: "connecting" });
    const source = new EventSource(streamUrl(documentId));

    source.addEventListener("node", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        node: GraphNodeName;
        output: Record<string, unknown>;
        trace: TraceEventOut[];
      };
      setState((prev) => ({
        ...prev,
        status: "running",
        currentNode: data.node,
        completedNodes: prev.completedNodes.includes(data.node)
          ? prev.completedNodes
          : [...prev.completedNodes, data.node],
        docType: (data.output.doc_type as string | undefined) ?? prev.docType,
        classificationConfidence:
          (data.output.classification_confidence as number | undefined) ?? prev.classificationConfidence,
        classificationReasoning:
          (data.output.classification_reasoning as string | undefined) ?? prev.classificationReasoning,
        extractionSchemaUsed:
          (data.output.extraction_schema_used as string | undefined) ?? prev.extractionSchemaUsed,
        extractedFields:
          (data.output.extracted_fields as Record<string, unknown> | undefined) ?? prev.extractedFields,
        crossCheckFlags:
          (data.output.cross_check_flags as CrossCheckFlag[] | undefined) ?? prev.crossCheckFlags,
        trace: [...prev.trace, ...data.trace],
      }));
    });

    source.addEventListener("interrupt", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as InterruptPayload;
      setState((prev) => ({
        ...prev,
        status: "awaiting_human",
        currentNode: "review",
        completedNodes: prev.completedNodes.includes("review")
          ? prev.completedNodes
          : [...prev.completedNodes, "review"],
        docType: data.doc_type ?? prev.docType,
        classificationConfidence: data.classification_confidence ?? prev.classificationConfidence,
        classificationReasoning: data.classification_reasoning ?? prev.classificationReasoning,
        extractionSchemaUsed: data.extraction_schema_used ?? prev.extractionSchemaUsed,
        extractedFields: data.extracted_fields ?? prev.extractedFields,
        crossCheckFlags: data.cross_check_flags ?? prev.crossCheckFlags,
        interrupt: data,
      }));
    });

    source.addEventListener("done", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: DocumentStatus;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        finalStatus: data.final_status,
        currentNode: TERMINAL_STATUSES.has(data.status) ? "finalize" : prev.currentNode,
        completedNodes:
          TERMINAL_STATUSES.has(data.status) && !prev.completedNodes.includes("finalize")
            ? [...prev.completedNodes, "finalize"]
            : prev.completedNodes,
      }));
      source.close();
    });

    source.addEventListener("replay", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: DocumentStatus;
        trace: TraceEventOut[];
        state_snapshot: Record<string, unknown>;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        trace: data.trace,
        docType: (data.state_snapshot.doc_type as string | undefined) ?? prev.docType,
        classificationConfidence:
          (data.state_snapshot.classification_confidence as number | undefined) ?? prev.classificationConfidence,
        classificationReasoning:
          (data.state_snapshot.classification_reasoning as string | undefined) ?? prev.classificationReasoning,
        extractionSchemaUsed:
          (data.state_snapshot.extraction_schema_used as string | undefined) ?? prev.extractionSchemaUsed,
        extractedFields:
          (data.state_snapshot.extracted_fields as Record<string, unknown> | undefined) ?? prev.extractedFields,
        crossCheckFlags:
          (data.state_snapshot.cross_check_flags as CrossCheckFlag[] | undefined) ?? prev.crossCheckFlags,
        finalStatus: data.final_status,
      }));
    });

    source.addEventListener("error", (evt) => {
      // Only MessageEvents carry a backend-emitted `error` payload; a plain
      // connection failure fires this same listener with no `.data`.
      const data = (evt as MessageEvent).data;
      if (typeof data === "string") {
        const parsed = JSON.parse(data) as { message: string };
        setState((prev) => ({ ...prev, status: "error", error: parsed.message }));
        source.close();
      }
    });

    source.onerror = () => {
      setState((prev) =>
        TERMINAL_STATUSES.has(prev.status)
          ? prev
          : { ...prev, error: prev.error ?? "Connection to the document stream was lost." },
      );
    };

    return () => {
      source.close();
    };
    // `generation` is bumped by callers (e.g. after POST /resume) to force
    // a fresh EventSource connection against the new background task.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, generation]);

  return state;
}
