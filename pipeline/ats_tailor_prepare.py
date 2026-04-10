"""Clamp ATS tailor JSON lists (skills + per-block technologies) after LLM parse."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_PROJECT_TECHNOLOGIES = 7
_SKILL_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Languages", 4, 6),
    ("Frameworks & Libraries", 5, 7),
    ("Tools & Technologies", 5, 7),
)


def _skill_line_tokens(line: str) -> list[str]:
    return [p.strip() for p in line.split(",") if p.strip()]


def _join_skill_tokens(tokens: list[str]) -> str:
    return ", ".join(tokens)


def _clamp_block_technologies(block: dict[str, Any]) -> None:
    t = block.get("technologies")
    if not isinstance(t, str):
        return
    toks = _skill_line_tokens(t)
    if len(toks) > _MAX_PROJECT_TECHNOLOGIES:
        block["technologies"] = _join_skill_tokens(toks[:_MAX_PROJECT_TECHNOLOGIES])
        logger.info(
            "ATS tailor: trimmed technologies from %s to %s items",
            len(toks),
            _MAX_PROJECT_TECHNOLOGIES,
        )


def _clamp_skills_dict(skills: dict[str, Any]) -> None:
    for key, _lo, hi in _SKILL_BANDS:
        v = skills.get(key)
        if not isinstance(v, str):
            continue
        toks = _skill_line_tokens(v)
        if len(toks) > hi:
            skills[key] = _join_skill_tokens(toks[:hi])
            logger.info("ATS tailor skills: trimmed %s from %s to %s items", key, len(toks), hi)


def _normalize_date_range(s: str) -> str:
    t = str(s).strip()
    if not t:
        return t
    t = re.sub(r"\s+to\s+", " - ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*[–—]\s*", " - ", t)
    t = re.sub(r"\bpresent\b", "Present", t)
    return t


def normalize_ats_date_ranges(data: dict[str, Any]) -> None:
    """Normalize ``date_range`` on each experience/project block."""
    for key in ("experience", "projects"):
        arr = data.get(key)
        if not isinstance(arr, list):
            continue
        for p in arr:
            if not isinstance(p, dict):
                continue
            dr = p.get("date_range")
            if isinstance(dr, str) and dr.strip():
                p["date_range"] = _normalize_date_range(dr)


def prepare_ats_tailor_lists(data: dict[str, Any]) -> None:
    """Mutate ``data`` in place: trim skills lines and each experience/project technologies."""
    sk = data.get("skills")
    if isinstance(sk, dict):
        _clamp_skills_dict(sk)
    for key in ("experience", "projects"):
        arr = data.get(key)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if isinstance(item, dict):
                _clamp_block_technologies(item)
