"""
PDF text extraction service.

Current implementation: PyMuPDF (fitz) — local, zero-latency, no AWS costs.
Future replacement:     AWS Textract  — swap _extract_with_pymupdf() for
                        _extract_with_textract() and update extract_text_from_pdf()
                        to call the new function.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Entry point for PDF text extraction.

    Args:
        pdf_bytes: Raw bytes of the uploaded PDF file.

    Returns:
        Extracted plain text (pages joined by double newline).

    Raises:
        ValueError: If the bytes cannot be parsed as a PDF.
        RuntimeError: If PyMuPDF is not installed.
    """
    return _extract_with_pymupdf(pdf_bytes)

    # TODO: replace the line above with the call below once Textract is wired up:
    # return _extract_with_textract(pdf_bytes)


# ---------------------------------------------------------------------------
# PyMuPDF implementation (current)
# ---------------------------------------------------------------------------

def _extract_with_pymupdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is not installed. Run: pip install pymupdf"
        ) from exc

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc

    pages: list[str] = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")  # plain-text mode
        if text.strip():
            pages.append(text.strip())
        else:
            logger.debug("Page %d produced no text (possibly image-only).", page_num)

    doc.close()

    if not pages:
        raise ValueError(
            "No extractable text found in the PDF. "
            "It may be a scanned/image-only document — consider enabling Textract OCR."
        )

    return "\n\n".join(pages)


# ---------------------------------------------------------------------------
# AWS Textract stub (future)
# ---------------------------------------------------------------------------

def _extract_with_textract(pdf_bytes: bytes) -> str:  # pragma: no cover
    """
    Extract text from a PDF using AWS Textract.

    Implementation steps when ready:
      1. Upload pdf_bytes to an S3 bucket.
      2. Call textract_client.start_document_text_detection(...)
      3. Poll until the job is SUCCEEDED.
      4. Aggregate all LINE blocks and return joined text.
    """
    raise NotImplementedError(
        "Textract extraction is not yet implemented. "
        "See the docstring in services/pdf_extractor.py for integration steps."
    )

