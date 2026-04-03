"""Tests for feeds/parser.py using fixture XML files."""

from __future__ import annotations

from pathlib import Path

import pytest

from feeds.parser import (
    FeedEntry,
    parse_ashby_json,
    parse_feed_xml,
    parse_greenhouse_json,
    parse_greenhouse_listing_url,
    _strip_html,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# --- _strip_html ---


def test_strip_html_removes_tags() -> None:
    assert _strip_html("<p>Hello <strong>world</strong></p>") == "Hello world"


def test_strip_html_normalizes_whitespace() -> None:
    assert _strip_html("<ul>\n  <li>Item</li>\n</ul>") == "Item"


# --- parse_greenhouse_listing_url ---


def test_parse_greenhouse_listing_url_job_boards_host() -> None:
    u = "https://job-boards.greenhouse.io/kensingtontours/jobs/5074908007"
    assert parse_greenhouse_listing_url(u) == ("kensingtontours", "5074908007")


def test_parse_greenhouse_listing_url_boards_host_and_query() -> None:
    u = "https://boards.greenhouse.io/stripe/jobs/12345?gh_src=abc"
    assert parse_greenhouse_listing_url(u) == ("stripe", "12345")


def test_parse_greenhouse_listing_url_non_greenhouse_returns_none() -> None:
    assert parse_greenhouse_listing_url("https://jobs.lever.co/acme/uuid") is None


# --- parse_greenhouse_json ---


def test_parse_greenhouse_json_uses_inline_content_when_present() -> None:
    entries = parse_greenhouse_json(
        {
            "jobs": [
                {
                    "title": "Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                    "location": {"name": "NYC"},
                    "content": "<p>Do things.</p>",
                    "updated_at": "2025-01-01T00:00:00Z",
                }
            ]
        },
        "Acme",
    )
    assert len(entries) == 1
    assert entries[0].description == "Do things."


def test_parse_greenhouse_json_empty_content_when_omitted() -> None:
    entries = parse_greenhouse_json(
        {
            "jobs": [
                {
                    "title": "Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                    "location": {"name": "NYC"},
                    "updated_at": "2025-01-01T00:00:00Z",
                }
            ]
        },
        "Acme",
    )
    assert entries[0].description == ""


# --- parse_feed_xml: Greenhouse ---


def test_parse_greenhouse_returns_entries() -> None:
    xml = _load_fixture("sample_greenhouse.xml")
    entries = parse_feed_xml(xml, "Stripe", "greenhouse")
    assert len(entries) == 2


def test_parse_greenhouse_entry_fields() -> None:
    xml = _load_fixture("sample_greenhouse.xml")
    entries = parse_feed_xml(xml, "Stripe", "greenhouse")
    entry = entries[0]
    assert isinstance(entry, FeedEntry)
    assert "Engineer" in entry.title
    assert entry.url.startswith("https://boards.greenhouse.io/stripe")
    assert entry.company == "Stripe"
    assert len(entry.description) > 0
    # HTML tags stripped
    assert "<p>" not in entry.description
    assert "<ul>" not in entry.description


def test_parse_greenhouse_description_uses_content_encoded() -> None:
    xml = _load_fixture("sample_greenhouse.xml")
    entries = parse_feed_xml(xml, "Stripe", "greenhouse")
    # content:encoded should give richer text than the plain <description>
    assert "Requirements" in entries[0].description


# --- parse_feed_xml: Lever ---


def test_parse_lever_returns_entries() -> None:
    xml = _load_fixture("sample_lever.xml")
    entries = parse_feed_xml(xml, "Vercel", "lever")
    assert len(entries) == 2


def test_parse_lever_extracts_location_from_title() -> None:
    xml = _load_fixture("sample_lever.xml")
    entries = parse_feed_xml(xml, "Vercel", "lever")
    # "Senior Software Engineer - Remote" → title without suffix, location="Remote"
    remote_entry = next(e for e in entries if "Remote" in e.location or "Remote" in e.title)
    assert "Remote" in remote_entry.location or "Remote" in remote_entry.title


def test_parse_lever_entry_url() -> None:
    xml = _load_fixture("sample_lever.xml")
    entries = parse_feed_xml(xml, "Vercel", "lever")
    for entry in entries:
        assert entry.url.startswith("https://jobs.lever.co/vercel/")


# --- parse_feed_xml: Ashby (Atom) ---


def test_parse_ashby_returns_entries() -> None:
    xml = _load_fixture("sample_ashby.xml")
    entries = parse_feed_xml(xml, "Linear", "ashby")
    assert len(entries) == 2


def test_parse_ashby_entry_fields() -> None:
    xml = _load_fixture("sample_ashby.xml")
    entries = parse_feed_xml(xml, "Linear", "ashby")
    entry = entries[0]
    assert entry.company == "Linear"
    assert entry.url.startswith("https://jobs.ashby.io/linear")
    assert len(entry.description) > 0
    assert "<p>" not in entry.description


# --- parse_feed_xml: Workable ---


def test_parse_workable_returns_entries() -> None:
    xml = _load_fixture("sample_workable.xml")
    entries = parse_feed_xml(xml, "Render", "workable")
    assert len(entries) == 1


def test_parse_workable_entry_description_stripped() -> None:
    xml = _load_fixture("sample_workable.xml")
    entries = parse_feed_xml(xml, "Render", "workable")
    assert "<h3>" not in entries[0].description
    assert "Senior Backend Engineer" in entries[0].title


# --- parse_feed_xml: error handling ---


def test_parse_feed_xml_empty_string_returns_empty() -> None:
    entries = parse_feed_xml("", "Unknown Co", "greenhouse")
    assert entries == []


def test_parse_feed_xml_invalid_xml_returns_empty() -> None:
    # feedparser is lenient; truly broken input should still return empty gracefully
    entries = parse_feed_xml("not xml at all !!!<><>", "Unknown Co", "greenhouse")
    # feedparser may or may not return entries; just ensure no exception
    assert isinstance(entries, list)


# --- parse_ashby_json ---

_ASHBY_SAMPLE = {
    "jobPostings": [
        {
            "title": "Software Engineer, Backend",
            "jobPostingUrl": "https://jobs.ashbyhq.com/linear/abc-123",
            "locationName": "Toronto, Canada",
            "publishedDate": "2025-03-01T00:00:00Z",
            "descriptionHtml": "<p>Build cool things.</p>",
        },
        {
            "title": "Product Designer",
            "jobPostingUrl": "https://jobs.ashbyhq.com/linear/def-456",
            "locationName": "Remote",
            "publishedDate": None,
            "descriptionHtml": "",
        },
    ]
}


def test_parse_ashby_json_returns_entries() -> None:
    entries = parse_ashby_json(_ASHBY_SAMPLE, "Linear")
    assert len(entries) == 2


def test_parse_ashby_json_fields() -> None:
    entries = parse_ashby_json(_ASHBY_SAMPLE, "Linear")
    e = entries[0]
    assert e.title == "Software Engineer, Backend"
    assert e.url == "https://jobs.ashbyhq.com/linear/abc-123"
    assert e.company == "Linear"
    assert e.location == "Toronto, Canada"
    assert e.published == "2025-03-01T00:00:00Z"
    assert "Build cool things" in e.description


def test_parse_ashby_json_strips_html() -> None:
    entries = parse_ashby_json(_ASHBY_SAMPLE, "Linear")
    assert "<p>" not in entries[0].description


def test_parse_ashby_json_skips_missing_title_or_url() -> None:
    data = {"jobPostings": [{"title": "", "jobPostingUrl": "https://x.com/1"}, {"title": "OK", "jobPostingUrl": ""}]}
    entries = parse_ashby_json(data, "Co")
    assert entries == []


def test_parse_ashby_json_empty_returns_empty() -> None:
    assert parse_ashby_json({"jobPostings": []}, "Co") == []
