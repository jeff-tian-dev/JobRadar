"""Soft caps for ATS tailor JSON (Career-Ops–style flexible lists)."""

from __future__ import annotations

from typing import Any


def ats_tailor_caps(settings: dict[str, Any] | None) -> dict[str, int]:
    """Return max list lengths and per-block bullet caps. All values are >= 1."""

    def _i(key: str, default: int, lo: int = 1, hi: int = 20) -> int:
        raw = (settings or {}).get(key)
        if raw is None:
            v = default
        else:
            try:
                v = int(raw)
            except (TypeError, ValueError):
                v = default
        return max(lo, min(hi, v))

    return {
        "max_experience": _i("tailor_max_experience_entries", 5, 1, 12),
        "max_projects": _i("tailor_max_project_entries", 6, 1, 12),
        "max_bullets_experience": _i("tailor_max_bullets_per_experience", 6, 1, 10),
        "max_bullets_project": _i("tailor_max_bullets_per_project", 6, 1, 10),
    }
