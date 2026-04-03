"""Normalize salary strings, locations, remote status, and posted dates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Final

# Remote indicators in title/location/description (lowercased match)
_REMOTE_TOKENS: Final[tuple[str, ...]] = (
    "remote",
    "work from home",
    "wfh",
    "anywhere",
    "distributed",
    "fully remote",
)

_HYBRID_TOKENS: Final[tuple[str, ...]] = ("hybrid",)


@dataclass(frozen=True)
class SalaryRange:
    """Annual salary in minor units is NOT used — store whole dollars as int."""

    min: int | None
    max: int | None
    currency: str | None
    period: str  # "annual" | "hourly" | "unknown"


def _parse_money_number(s: str) -> float | None:
    s = s.strip().lower().replace(",", "")
    mult = 1.0
    if s.endswith("k"):
        mult = 1000.0
        s = s[:-1].strip()
    try:
        return float(s) * mult
    except ValueError:
        return None


def parse_salary(salary_raw: str | None) -> SalaryRange | None:
    """Parse strings like $150k-$180k, 150-180K CAD, $25/hr into SalaryRange (annual dollars when possible)."""
    if not salary_raw or not str(salary_raw).strip():
        return None
    text = str(salary_raw).strip()
    lower = text.lower()
    currency = None
    if "cad" in lower or "cdn" in lower:
        currency = "CAD"
    elif "usd" in lower or "$" in text:
        currency = "USD"
    period = "annual"
    if "hr" in lower or "/hr" in lower or "hour" in lower:
        period = "hourly"

    # Remove currency words/symbols for number extraction
    cleaned = re.sub(r"[^\d\.\-kK,]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = re.split(r"\s*[-–—]\s*", cleaned)
    nums: list[float] = []
    for p in parts:
        n = _parse_money_number(p)
        if n is not None:
            nums.append(n)
    if not nums:
        return SalaryRange(min=None, max=None, currency=currency, period=period)
    lo = int(min(nums))
    hi = int(max(nums))
    if period == "hourly":
        return SalaryRange(min=lo, max=hi, currency=currency, period="hourly")
    return SalaryRange(min=lo, max=hi, currency=currency, period="annual")


def detect_remote_status(
    title: str,
    location: str,
    description: str,
) -> str:
    """Return remote | hybrid | onsite | unknown."""
    blob = f"{title} {location} {description}".lower()
    if any(t in blob for t in _HYBRID_TOKENS):
        return "hybrid"
    if any(t in blob for t in _REMOTE_TOKENS):
        return "remote"
    loc = location.lower()
    if "remote" in loc:
        return "remote"
    return "unknown"


def extract_city_country(location_raw: str | None) -> tuple[str | None, str | None]:
    """
    Best-effort city/country from a raw location string.
    Heuristic: comma-separated — first segment often city, last often country/region.
    """
    if not location_raw or not str(location_raw).strip():
        return None, None
    parts = [p.strip() for p in str(location_raw).split(",") if p.strip()]
    if not parts:
        return None, None
    city = parts[0]
    country = parts[-1] if len(parts) > 1 else None
    # Normalize obvious duplicates
    if country and country.lower() == city.lower():
        country = None
    return city, country


def normalize_text_for_hash(s: str) -> str:
    """Lowercase, strip, remove punctuation for dedup components."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_posted_date(relative_or_abs: str | None, now: datetime | None = None) -> str | None:
    """
    Parse relative phrases into ISO date string (date only) or pass through if parse fails.
    """
    if not relative_or_abs or not str(relative_or_abs).strip():
        return None
    raw = str(relative_or_abs).strip().lower()
    now = now or datetime.now(timezone.utc)
    today = now.date()
    if "today" in raw or "just posted" in raw:
        return today.isoformat()
    if "yesterday" in raw:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*days?\s*ago", raw)
    if m:
        d = int(m.group(1))
        return (today - timedelta(days=d)).isoformat()
    m = re.search(r"(\d+)\s*weeks?\s*ago", raw)
    if m:
        w = int(m.group(1))
        return (today - timedelta(weeks=w)).isoformat()
    # Try ISO
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return relative_or_abs


def parse_posted_date_to_date(relative_or_abs: str | None, now: datetime | None = None) -> date | None:
    """
    Best-effort posted date as a calendar date for age filtering.
    Returns None if the string cannot be interpreted (do not treat as stale).
    """
    if not relative_or_abs or not str(relative_or_abs).strip():
        return None
    raw_s = str(relative_or_abs).strip().lower()
    now = now or datetime.now(timezone.utc)
    today = now.date()
    if "today" in raw_s or "just posted" in raw_s:
        return today
    if "yesterday" in raw_s:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\s*days?\s*ago", raw_s)
    if m:
        return today - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*weeks?\s*ago", raw_s)
    if m:
        return today - timedelta(weeks=int(m.group(1)))
    try:
        return datetime.fromisoformat(raw_s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def is_posted_older_than_days(
    posted_raw: str | None,
    max_age_days: int,
    now: datetime | None = None,
) -> bool:
    """
    True if posted date is strictly more than max_age_days before today.
    Unknown/unparseable posted date → False (keep listing).
    """
    if max_age_days < 0:
        return False
    posted = parse_posted_date_to_date(posted_raw, now=now)
    if posted is None:
        return False
    today = (now or datetime.now(timezone.utc)).date()
    return (today - posted).days > max_age_days
