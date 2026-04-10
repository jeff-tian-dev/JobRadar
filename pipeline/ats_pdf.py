"""Render ATS resume HTML to PDF via Playwright (Chromium)."""

from __future__ import annotations

import logging
from typing import Any

from pipeline.ats_resume_html import ats_template_base_url

logger = logging.getLogger(__name__)

_MARGIN_IN = "0.6in"


def html_to_pdf_bytes(html: str, page_format: str) -> bytes:
    """Return PDF bytes. ``page_format`` is ``letter`` or ``a4``."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from e

    fmt = "Letter" if page_format == "letter" else "A4"
    base_url = ats_template_base_url()
    margin = {
        "top": _MARGIN_IN,
        "right": _MARGIN_IN,
        "bottom": _MARGIN_IN,
        "left": _MARGIN_IN,
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle", base_url=base_url)
            try:
                page.evaluate("() => document.fonts.ready")
            except Exception:
                logger.debug("document.fonts.ready wait skipped", exc_info=True)
            return page.pdf(
                format=fmt,
                print_background=True,
                margin=margin,
                prefer_css_page_size=False,
            )
        finally:
            browser.close()


def tailored_json_to_pdf_bytes(
    llm_data: dict[str, Any],
    profile_id: str,
    settings: dict[str, Any],
) -> bytes:
    """Build HTML from tailor JSON + profile and return PDF bytes."""
    from pipeline.ats_resume_html import build_ats_resume_html, load_profile_dict, resolve_ats_pdf_format

    profile = load_profile_dict(profile_id, settings)
    fmt = resolve_ats_pdf_format(profile, settings)
    html = build_ats_resume_html(llm_data, profile_id, settings)
    return html_to_pdf_bytes(html, fmt)
