"""Listing deduplication hash (title + company + city with fallback)."""

from __future__ import annotations

import hashlib

from pipeline.normalizer import extract_city_country, normalize_text_for_hash


def listing_dedup_hash(title: str, company: str, location_raw: str | None) -> str:
    """
    Stable hash from normalized title, company, and city.
    If city cannot be extracted, use normalized full location_raw (documented fallback).
    """
    city, _ = extract_city_country(location_raw)
    city_part = city if city else (location_raw or "")
    parts = "|".join(
        [
            normalize_text_for_hash(title),
            normalize_text_for_hash(company),
            normalize_text_for_hash(city_part),
        ]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()
