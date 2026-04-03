"""Dedup hash tests."""

from pipeline.dedup import listing_dedup_hash


def test_same_hash_after_normalization() -> None:
    h1 = listing_dedup_hash("Senior Engineer", "Acme Corp", "Toronto, ON")
    h2 = listing_dedup_hash("  senior engineer  ", "ACME CORP", "toronto, on")
    assert h1 == h2


def test_whitespace_and_case() -> None:
    h1 = listing_dedup_hash("Backend Dev", "Co", "Remote")
    h2 = listing_dedup_hash("backend dev", "co", "remote")
    assert h1 == h2
