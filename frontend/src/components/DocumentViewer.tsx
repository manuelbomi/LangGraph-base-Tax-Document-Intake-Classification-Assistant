import { documentFileUrl } from "../api/client";

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg"]);

/** Shows the original source document (mostly PDFs, sometimes a photographed
 * PNG/JPG) next to its extracted fields in the organizer detail view. */
export function DocumentViewer({ documentId, filename }: { documentId: string; filename: string }) {
  const url = documentFileUrl(documentId);
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";

  if (IMAGE_EXTENSIONS.has(ext)) {
    return (
      <div className="flex justify-center rounded-lg border border-slate-200 bg-slate-50 p-3">
        <img src={url} alt={filename} className="max-h-[600px] rounded shadow-sm" />
      </div>
    );
  }

  return (
    <iframe title={filename} src={url} className="h-[600px] w-full rounded-lg border border-slate-200" />
  );
}
