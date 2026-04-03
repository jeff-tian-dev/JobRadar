"""One-time script to import companies from SimplifyJobs/Summer2026-Internships.

Fetches the listings.json, extracts platform + slug from ATS job URLs,
deduplicates against the existing seed list, and appends new entries to
config/seed_companies.yaml.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import httpx
import yaml

_LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships"
    "/dev/.github/scripts/listings.json"
)

_SEED_PATH = Path(__file__).parent.parent / "config" / "seed_companies.yaml"

_CATEGORY_TO_INDUSTRY: dict[str, str] = {
    "Software": "software",
    "Software Engineering": "software",
    "AI/ML/Data": "AI/ML",
    "Quant": "finance/quant",
    "Hardware": "hardware",
}


def extract_platform_slug(url: str) -> tuple[str, str] | None:
    # Greenhouse (two URL variants)
    m = re.search(r"(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)", url)
    if m:
        return "greenhouse", m.group(1)
    # Lever
    m = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
    if m:
        return "lever", m.group(1)
    # Ashby
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", url)
    if m:
        return "ashby", m.group(1)
    return None


def load_existing_slugs(seed_path: Path) -> set[tuple[str, str]]:
    """Return set of (platform, slug) pairs already in the seed file."""
    if not seed_path.exists():
        return set()
    with seed_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    existing: set[tuple[str, str]] = set()
    for company in data.get("companies", []):
        platform = company.get("platform", "")
        slug = company.get("slug", "")
        if platform and slug:
            existing.add((platform, slug))
    return existing


def main() -> None:
    print(f"Fetching listings from {_LISTINGS_URL} ...")
    with httpx.Client(timeout=60.0) as client:
        r = client.get(_LISTINGS_URL)
        r.raise_for_status()
        listings: list[dict] = r.json()

    print(f"Fetched {len(listings)} total entries.")

    # Group active entries by company name → collect (platform, slug) votes
    company_votes: dict[str, Counter[tuple[str, str]]] = {}
    company_category: dict[str, str] = {}

    for entry in listings:
        name = (entry.get("company_name") or "").strip()
        url = (entry.get("url") or "").strip()
        category = (entry.get("category") or "").strip()
        if not name or not url:
            continue
        result = extract_platform_slug(url)
        if result is None:
            continue
        platform, slug = result
        if name not in company_votes:
            company_votes[name] = Counter()
        company_votes[name][(platform, slug)] += 1
        if name not in company_category:
            company_category[name] = category

    print(f"Found {len(company_votes)} unique companies on supported platforms.")

    existing_slugs = load_existing_slugs(_SEED_PATH)
    print(f"Existing seed list has {len(existing_slugs)} entries.")

    new_entries: list[dict] = []
    skipped = 0

    for name, votes in sorted(company_votes.items()):
        (platform, slug), _ = votes.most_common(1)[0]
        if (platform, slug) in existing_slugs:
            skipped += 1
            continue
        category = company_category.get(name, "")
        industry = _CATEGORY_TO_INDUSTRY.get(category, "software")
        new_entries.append({
            "name": name,
            "slug": slug,
            "platform": platform,
            "website": "",
            "industry": industry,
        })
        existing_slugs.add((platform, slug))  # prevent intra-run duplicates

    print(f"Adding {len(new_entries)} new companies, skipping {skipped} already present.")

    if not new_entries:
        print("Nothing to add.")
        return

    # Append to seed file
    lines: list[str] = ["\n  # --- Imported from SimplifyJobs/Summer2026-Internships ---\n"]
    for e in new_entries:
        lines.append(
            f"  - name: {e['name']}\n"
            f"    slug: {e['slug']}\n"
            f"    platform: {e['platform']}\n"
            f"    website: \"{e['website']}\"\n"
            f"    industry: {e['industry']}\n"
        )

    with _SEED_PATH.open("a", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Done. {len(new_entries)} companies appended to {_SEED_PATH}.")


if __name__ == "__main__":
    main()
