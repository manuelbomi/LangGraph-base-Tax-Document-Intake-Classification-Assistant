import type { DocumentSummary, ExpectedDocumentItem } from "../api/types";

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * Client-side "is this expected document satisfied?" check for the
 * organizer checklist. The real fuzzy counterparty-name matching already
 * happened server-side (see `backend/app/tools/organizer.py`) when the
 * document was cross-checked; this is only a display-time heuristic that
 * compares a completed document's doc_type and original filename against
 * an expected-documents entry, since `DocumentSummary` doesn't carry the
 * extracted counterparty name itself.
 */
export function isDocumentMatch(expected: ExpectedDocumentItem, doc: DocumentSummary): boolean {
  if (doc.status !== "completed") return false;
  if (normalize(doc.doc_type) !== normalize(expected.doc_type)) return false;

  const normalizedCounterparty = normalize(expected.counterparty_name);
  if (!normalizedCounterparty) return true;

  const normalizedFilename = normalize(doc.original_filename);
  return normalizedFilename.includes(normalizedCounterparty);
}

export interface ChecklistItem {
  expected: ExpectedDocumentItem;
  received: boolean;
  matchedDocument: DocumentSummary | null;
}

export function buildChecklist(
  expectedDocuments: ExpectedDocumentItem[],
  documents: DocumentSummary[],
): ChecklistItem[] {
  return expectedDocuments.map((expected) => {
    const matchedDocument = documents.find((doc) => isDocumentMatch(expected, doc)) ?? null;
    return { expected, received: matchedDocument !== null, matchedDocument };
  });
}
