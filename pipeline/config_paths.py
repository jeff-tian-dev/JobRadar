"""Resolve repo paths, settings, and active profile (CLI > env > settings)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def settings_path() -> Path:
    """Path to gitignored settings file."""
    return REPO_ROOT / "config" / "settings.yaml"


def settings_example_path() -> Path:
    return REPO_ROOT / "config" / "settings.example.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file; return empty dict if missing (for optional files)."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_settings() -> dict[str, Any]:
    """Load settings.yaml, falling back to settings.example.yaml for missing keys only if main absent."""
    main = settings_path()
    example = settings_example_path()
    if main.is_file():
        return load_yaml(main)
    if example.is_file():
        return load_yaml(example)
    return {}


def effective_profile_id(cli_profile: str | None) -> str:
    """Precedence: --profile > JOB_SEARCH_PROFILE > active_profile in settings."""
    if cli_profile:
        return cli_profile.strip()
    env_p = os.environ.get("JOB_SEARCH_PROFILE", "").strip()
    if env_p:
        return env_p
    settings = load_settings()
    ap = settings.get("active_profile")
    if isinstance(ap, str) and ap.strip():
        return ap.strip()
    return "jeff"


def profiles_dir(settings: dict[str, Any] | None = None) -> Path:
    settings = settings or load_settings()
    raw = settings.get("profiles_dir", "config/profiles")
    p = Path(str(raw))
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


def profile_yaml_path(profile_id: str, settings: dict[str, Any] | None = None) -> Path:
    """Resolved path to config/profiles/<id>/profile.yaml."""
    return profiles_dir(settings) / profile_id / "profile.yaml"


def sources_path() -> Path:
    return REPO_ROOT / "config" / "sources.yaml"


def load_sources() -> dict[str, Any]:
    return load_yaml(sources_path())


def load_profile_for_scoring(profile_id: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load merged profile dict for the scorer."""
    path = profile_yaml_path(profile_id, settings)
    data = load_yaml(path)
    if not data:
        raise FileNotFoundError(f"Profile not found or empty: {path}")
    return data


def profile_text_for_prompt(profile: dict[str, Any]) -> str:
    """Serialize profile to YAML for injection into the user prompt."""
    return yaml.dump(profile, default_flow_style=False, allow_unicode=True, sort_keys=False)


def db_path(settings: dict[str, Any] | None = None) -> Path:
    settings = settings or load_settings()
    raw = settings.get("db_path", "db/jobs.db")
    p = Path(str(raw))
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


def prompts_dir() -> Path:
    return REPO_ROOT / "prompts"


def seed_companies_path() -> Path:
    """Path to the manually-curated seed companies YAML."""
    return REPO_ROOT / "config" / "seed_companies.yaml"


def load_seed_companies() -> list[dict[str, Any]]:
    """Load the list of seed companies from config/seed_companies.yaml."""
    data = load_yaml(seed_companies_path())
    return data.get("companies", [])
