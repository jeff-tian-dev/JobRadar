"""PDF page counting (for one-page resume enforcement)."""

from __future__ import annotations

from io import BytesIO


def count_pdf_pages(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF document."""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    return len(reader.pages)
