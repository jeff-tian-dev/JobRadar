#!/usr/bin/env python3
"""Discover new companies → resolve ATS feeds → update companies table."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from discovery.runner import run_discovery
from pipeline.config_paths import (
    db_path,
    effective_profile_id,
    load_profile_for_scoring,
    load_settings,
)
from pipeline.db import connect


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path.home() / "Library/Logs/job-search-agent"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "discovery.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)


def main() -> int:
    parser = argparse.ArgumentParser(description="JobRadar company discovery")
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Profile id (overrides env/settings)",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        metavar="SOURCE",
        help="Discovery sources to run (seed, hn_hiring, yc, github, wellfound). "
        "Default: all enabled in settings.yaml",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("run_discovery")

    profile_id = effective_profile_id(args.profile)
    settings = load_settings()

    profile: dict | None = None
    try:
        profile = load_profile_for_scoring(profile_id, settings)
    except FileNotFoundError as e:
        log.warning("Profile not found (%s); relevance filtering disabled", e)

    dpath = db_path(settings)

    with connect(dpath) as conn:
        results = asyncio.run(
            run_discovery(conn, settings, profile=profile, sources=args.sources)
        )

    total_feeds = sum(results.values())
    log.info("Discovery finished. Results: %s. Total new feeds: %d", results, total_feeds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
