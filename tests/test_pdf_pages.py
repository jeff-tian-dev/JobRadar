"""Tests for PDF page counting."""

from __future__ import annotations

from io import BytesIO

import pytest

from pipeline.pdf_pages import count_pdf_pages


def test_count_pdf_pages_two_pages() -> None:
    from pypdf import PdfWriter

    buf = BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    w.add_blank_page(width=72, height=72)
    w.write(buf)
    raw = buf.getvalue()
    assert count_pdf_pages(raw) == 2


def test_count_pdf_pages_one_page() -> None:
    from pypdf import PdfWriter

    buf = BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    w.write(buf)
    assert count_pdf_pages(buf.getvalue()) == 1


def test_count_pdf_pages_rejects_garbage() -> None:
    with pytest.raises(Exception):
        count_pdf_pages(b"not a pdf")
