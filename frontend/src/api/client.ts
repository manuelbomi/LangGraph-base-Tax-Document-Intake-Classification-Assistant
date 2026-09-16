import type {
  ClientDetail,
  ClientListResponse,
  DocumentCreateResponse,
  DocumentDetail,
  DocumentListResponse,
  HumanDecisionRequest,
  SamplesResponse,
} from "./types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function listClients(): Promise<ClientListResponse> {
  const res = await fetch(`${API_BASE_URL}/clients`);
  return handle<ClientListResponse>(res);
}

export async function getClient(clientId: string): Promise<ClientDetail> {
  const res = await fetch(`${API_BASE_URL}/clients/${encodeURIComponent(clientId)}`);
  return handle<ClientDetail>(res);
}

export async function listSamples(): Promise<SamplesResponse> {
  const res = await fetch(`${API_BASE_URL}/documents/samples`);
  return handle<SamplesResponse>(res);
}

export async function runSampleDocument(sampleId: string, clientId: string): Promise<DocumentCreateResponse> {
  const formData = new FormData();
  formData.append("client_id", clientId);
  const res = await fetch(`${API_BASE_URL}/documents/samples/${encodeURIComponent(sampleId)}/run`, {
    method: "POST",
    body: formData,
  });
  return handle<DocumentCreateResponse>(res);
}

export async function uploadDocument(file: File, clientId: string): Promise<DocumentCreateResponse> {
  const formData = new FormData();
  formData.append("client_id", clientId);
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/documents/upload`, { method: "POST", body: formData });
  return handle<DocumentCreateResponse>(res);
}

export async function resumeDocument(
  documentId: string,
  payload: HumanDecisionRequest,
): Promise<DocumentCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<DocumentCreateResponse>(res);
}

export async function listDocuments(clientId?: string): Promise<DocumentListResponse> {
  const url = clientId
    ? `${API_BASE_URL}/documents?client_id=${encodeURIComponent(clientId)}`
    : `${API_BASE_URL}/documents`;
  const res = await fetch(url);
  return handle<DocumentListResponse>(res);
}

export async function getDocument(documentId: string): Promise<DocumentDetail> {
  const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}`);
  return handle<DocumentDetail>(res);
}

export function streamUrl(documentId: string): string {
  return `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/stream`;
}

export function documentFileUrl(documentId: string): string {
  return `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/file`;
}
