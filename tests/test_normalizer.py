"""Normalizer tests."""

from datetime import date, datetime, timezone

from pipeline.normalizer import (
    detect_remote_status,
    is_posted_older_than_days,
    parse_posted_date,
    parse_posted_date_to_date,
    parse_salary,
)


def test_parse_salary_range_k() -> None:
    s = parse_salary("$150k-$180k USD")
    assert s is not None
    assert s.min == 150000
    assert s.max == 180000
    assert s.currency == "USD"


def test_parse_salary_cad() -> None:
    s = parse_salary("150k-180k CAD")
    assert s is not None
    assert s.min == 150000
    assert s.max == 180000


def test_remote_detection() -> None:
    assert detect_remote_status("Engineer", "Remote", "") == "remote"
    assert detect_remote_status("Engineer", "Toronto", "Hybrid role in office 2d/wk") == "hybrid"


def test_posted_relative() -> None:
    d = parse_posted_date("2 days ago")
    assert d is not None


def test_parse_posted_date_to_date_days_ago() -> None:
    fixed = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
    d = parse_posted_date_to_date("8 days ago", now=fixed)
    assert d == date(2026, 3, 21)


def test_is_posted_older_than_days() -> None:
    fixed = datetime(2026, 3, 29, tzinfo=timezone.utc)
    assert is_posted_older_than_days("8 days ago", 7, now=fixed) is True
    assert is_posted_older_than_days("7 days ago", 7, now=fixed) is False
    assert is_posted_older_than_days("6 days ago", 7, now=fixed) is False
    assert is_posted_older_than_days(None, 7, now=fixed) is False
    assert is_posted_older_than_days("not a date", 7, now=fixed) is False
