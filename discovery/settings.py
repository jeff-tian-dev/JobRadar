"""Discovery-related settings helpers (read from settings.yaml discovery block)."""

from __future__ import annotations

from typing import Any


def discovery_enabled(settings: dict[str, Any]) -> bool:
    """False only when discovery.enabled is explicitly false; missing key → true."""
    disc = settings.get("discovery")
    if not isinstance(disc, dict):
        return True
    if "enabled" not in disc:
        return True
    return bool(disc.get("enabled"))


def max_companies_per_source(settings: dict[str, Any]) -> int | None:
    """Upper bound per source run. None = no cap. Default 100 when key omitted."""
    disc = settings.get("discovery")
    if not isinstance(disc, dict):
        return 100
    if "max_companies_per_source" not in disc:
        return 100
    raw = disc["max_companies_per_source"]
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 100
    if n <= 0:
        return None
    return n


def enabled_discovery_sources(source_cfg: dict[str, Any]) -> list[str]:
    """Resolve which sources are on; accepts legacy key github_trending as alias for github."""
    _ALL = ["seed", "hn_hiring", "yc", "github", "wellfound"]
    out: list[str] = []
    for s in _ALL:
        if s == "github":
            if source_cfg.get("github") or source_cfg.get("github_trending"):
                out.append("github")
        elif source_cfg.get(s, False):
            out.append(s)
    return out
