"""Re-export PDF helpers; implementation lives in ``pipeline`` for tailoring reuse."""

from pipeline.pdf_convert import docx_bytes_to_pdf, find_soffice

__all__ = ["docx_bytes_to_pdf", "find_soffice"]
