/**
 * Hand-written TypeScript mirror of `backend/app/api/schemas.py`.
 * Keep these two files in sync when the API contract changes.
 */

export type DocumentStatus = "pending" | "running" | "awaiting_human" | "completed" | "rejected" | "error";

export type DocType =
  | "W-2"
  | "1099-NEC"
  | "1099-INT"
  | "1099-DIV"
  | "K-1"
  | "bank-statement"
  | "other-unknown"
  | "unknown";

export interface ExpectedDocumentItem {
  doc_type: string;
  counterparty_name: string;
  notes: string;
}

export interface ClientSummary {
  id: string;
  name: string;
  tax_year: number;
  documents_expected: number;
  documents_received: number;
  completeness_status: "complete" | "incomplete";
}

export interface DocumentSummary {
  id: string;
  client_id: string;
  original_filename: string;
  doc_type: DocType;
  classification_confidence: number;
  status: DocumentStatus;
  final_status: string | null;
  /** True if any cross_check_flags entry has severity warning/error. */
  flagged: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClientDetail extends ClientSummary {
  notes: string;
  expected_documents: ExpectedDocumentItem[];
  documents: DocumentSummary[];
}

export interface ClientListResponse {
  clients: ClientSummary[];
}

export interface SampleDocument {
  id: string;
  label: string;
  doc_type: DocType;
  suggested_client_id: string | null;
}

export interface SamplesResponse {
  samples: SampleDocument[];
}

export interface DocumentCreateResponse {
  id: string;
  client_id: string;
  status: DocumentStatus;
  original_filename: string;
  doc_type: DocType;
}

export interface HumanDecisionRequest {
  decision: "approve" | "correct" | "reject";
  feedback: string;
  corrected_fields?: Record<string, unknown> | null;
}

export interface TraceEventOut {
  node: string;
  timestamp: string;
  summary: string;
}

export type FlagSeverity = "info" | "warning" | "error";

export interface CrossCheckFlag {
  code: string;
  severity: FlagSeverity;
  message: string;
  details: Record<string, unknown>;
}

export interface DocumentDetail extends DocumentSummary {
  extraction_schema_used: string | null;
  /** Keys vary by doc_type -- see `backend/app/graph/extraction_schema.py`. */
  extracted_fields: Record<string, unknown>;
  cross_check_flags: CrossCheckFlag[];
  trace: TraceEventOut[];
  state_snapshot: Record<string, unknown>;
  error: string | null;
}

export interface DocumentListResponse {
  documents: DocumentSummary[];
}

/** Payload of the `interrupt` SSE event -- what `review_node` pauses with. */
export interface InterruptPayload {
  original_filename: string;
  doc_type: DocType;
  classification_confidence: number;
  classification_reasoning: string;
  extraction_schema_used: string | null;
  extracted_fields: Record<string, unknown>;
  cross_check_flags: CrossCheckFlag[];
}

/** Shapes of the SSE events emitted by GET /documents/{id}/stream. */
export type StreamEvent =
  | { type: "node"; node: string; output: Record<string, unknown>; trace: TraceEventOut[] }
  | { type: "interrupt"; data: InterruptPayload }
  | { type: "done"; status: DocumentStatus; final_status: string | null }
  | { type: "error"; message: string }
  | {
      type: "replay";
      status: DocumentStatus;
      trace: TraceEventOut[];
      state_snapshot: Record<string, unknown>;
      final_status: string | null;
    };

/** The graph node names, in the order they appear in the LangGraph
 * StateGraph (backend/app/graph/graph.py) -- used to drive the GraphView.
 * Every document visits `ingest` -> `classify` -> exactly one of the seven
 * `extract_*` nodes -> `cross_check` -> `review` -> `finalize`. */
export const GRAPH_NODES = [
  "ingest",
  "classify",
  "extract_w2",
  "extract_1099nec",
  "extract_1099int",
  "extract_1099div",
  "extract_k1",
  "extract_bank_statement",
  "extract_other",
  "cross_check",
  "review",
  "finalize",
] as const;

export type GraphNodeName = (typeof GRAPH_NODES)[number];

export const EXTRACTION_NODES: GraphNodeName[] = [
  "extract_w2",
  "extract_1099nec",
  "extract_1099int",
  "extract_1099div",
  "extract_k1",
  "extract_bank_statement",
  "extract_other",
];

/** Maps a classified doc_type to the extraction node that handles it, so
 * the GraphView can highlight only the matching branch. */
export const EXTRACTION_NODE_BY_DOC_TYPE: Record<string, GraphNodeName> = {
  "W-2": "extract_w2",
  "1099-NEC": "extract_1099nec",
  "1099-INT": "extract_1099int",
  "1099-DIV": "extract_1099div",
  "K-1": "extract_k1",
  "bank-statement": "extract_bank_statement",
  "other-unknown": "extract_other",
};
