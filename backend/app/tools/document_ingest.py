"""Real (non-stub) document ingestion helpers: PDF text extraction and
image base64 encoding for vision-LLM fallback.

Why a vision LLM instead of Tesseract OCR for scanned/photographed
documents: `pytesseract` requires the native Tesseract binary to be
installed on the host/image, which is one more moving part to get right
across Windows dev machines, CI runners, and the Docker image -- and a
scanned tax form (skewed, low-contrast, phone-photographed) is exactly the
input Tesseract tends to do worst on without real image preprocessing.
`gpt-4o-mini` accepts image input directly and, given a schema-constrained
extraction prompt, reads a document image reliably with zero extra system
dependencies -- the same approach `langgraph-tutorial-02` uses for receipt
photos.

This tutorial's bundled sample documents are all text-layer PDFs (see
`sample-data/README.md`), so the live/default path is `extract_pdf_text`.
The vision fallback triggers automatically whenever a PDF's extracted text
is implausibly short (a scanned page with no text layer) or when the
uploaded file is an image outright (.png/.jpg/.jpeg) -- exercising it end
to end just requires uploading a photo of a document instead of a PDF.
"""
from __future__ import annotations

import base64
import os

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}

# A text-layer PDF page of a real tax form typically yields at least a few
# hundred characters of text; anything drastically shorter than this is
# almost certainly a scanned image with no text layer.
MIN_PLAUSIBLE_TEXT_LENGTH = 40


def detect_file_kind(file_path: str) -> str:
    """Classify a file purely from its extension: "pdf" or "image".

    A production system might sniff file content/magic bytes too, but for
    this tutorial's two supported input kinds the extension is unambiguous
    and this stays fully deterministic and free.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    raise ValueError(
        f"Unsupported file extension {ext!r}. Supported: {sorted(PDF_EXTENSIONS | IMAGE_EXTENSIONS)}"
    )


def extract_pdf_text(file_path: str) -> str:
    """Extract all text from a PDF using `pdfplumber` (pure Python, no
    native/system dependency -- unlike Tesseract, this works identically on
    Windows, macOS, Linux, and inside the Docker image)."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def encode_image_base64(file_path: str) -> str:
    """Read an image file and return its base64-encoded bytes, ready to
    embed in a LangChain `image_url` data-URI content block."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def image_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".png":
        return "image/png"
    return "image/jpeg"
