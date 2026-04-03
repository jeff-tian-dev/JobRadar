"""Shared domain objects for the job search pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

_ollama_metrics_file_handler_installed = False
_ollama_metrics_file_handler_skipped = False


def _ensure_ollama_metrics_file_handler() -> None:
    """Attach a rotating file handler once so Ollama metrics are persisted (dashboard + pipeline)."""
    global _ollama_metrics_file_handler_installed, _ollama_metrics_file_handler_skipped
    if _ollama_metrics_file_handler_installed or _ollama_metrics_file_handler_skipped:
        return
    log_dir = Path.home() / "Library/Logs/job-search-agent"
    log_file = log_dir / "ollama_metrics.log"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)
        if logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
        _ollama_metrics_file_handler_installed = True
    except OSError:
        _ollama_metrics_file_handler_skipped = True


def log_tailor_session_ollama_summary(summary: dict[str, Any]) -> None:
    """Write one JSON line with aggregate token/time stats after a resume tailor session."""
    _ensure_ollama_metrics_file_handler()
    logger.info("Tailor session ollama summary: %s", json.dumps(summary, ensure_ascii=False))


def ollama_response_metrics_dict(resp: Any) -> dict[str, Any]:
    """Structured metrics from one ollama ``chat`` response (tokens, wall time, throughput)."""
    def _get_int(key: str) -> int | None:
        v = resp.get(key) if isinstance(resp, dict) else getattr(resp, key, None)
        return int(v) if isinstance(v, (int, float)) else None

    prompt_tokens = _get_int("prompt_eval_count")
    eval_tokens = _get_int("eval_count")
    total_ns = _get_int("total_duration")
    prompt_ns = _get_int("prompt_eval_duration")
    eval_ns = _get_int("eval_duration")
    load_ns = _get_int("load_duration")

    out: dict[str, Any] = {}
    if prompt_tokens is not None:
        out["prompt_tokens"] = prompt_tokens
    if eval_tokens is not None:
        out["output_tokens"] = eval_tokens
    if total_ns is not None:
        out["total_seconds"] = round(total_ns / 1e9, 3)
    if prompt_ns and prompt_ns > 0:
        out["prompt_eval_seconds"] = round(prompt_ns / 1e9, 3)
        if prompt_tokens is not None:
            out["prompt_tokens_per_second"] = round(prompt_tokens / (prompt_ns / 1e9), 1)
    if eval_ns and eval_ns > 0:
        out["eval_seconds"] = round(eval_ns / 1e9, 3)
        if eval_tokens is not None:
            out["output_tokens_per_second"] = round(eval_tokens / (eval_ns / 1e9), 1)
    if load_ns is not None and load_ns > 0:
        out["model_load_seconds"] = round(load_ns / 1e9, 3)
    return out


def log_ollama_metrics(resp: Any, label: str) -> None:
    """Log token counts, durations, and throughput from an ollama chat response."""
    _ensure_ollama_metrics_file_handler()
    d = ollama_response_metrics_dict(resp)
    if not d:
        return
    parts: list[str] = [f"[{label}]"]
    if "prompt_tokens" in d:
        parts.append(f"prompt_tokens={d['prompt_tokens']}")
    if "output_tokens" in d:
        parts.append(f"output_tokens={d['output_tokens']}")
    if "prompt_tokens" in d and "output_tokens" in d:
        parts.append(f"total_tokens={d['prompt_tokens'] + d['output_tokens']}")
    if "total_seconds" in d:
        parts.append(f"total={d['total_seconds']:.1f}s")
    pps = d.get("prompt_tokens_per_second")
    if isinstance(pps, (int, float)):
        parts.append(f"prompt_speed={pps:.1f} tok/s")
    gps = d.get("output_tokens_per_second")
    if isinstance(gps, (int, float)):
        parts.append(f"gen_speed={gps:.1f} tok/s")
    if "model_load_seconds" in d:
        parts.append(f"model_load={d['model_load_seconds']:.1f}s")
    logger.info("Ollama metrics: %s", " | ".join(parts))

USER_AGENTS: Final[tuple[str, ...]] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)


@dataclass
class RawListing:
    """Single job listing before normalization and scoring."""

    source: str
    source_url: str
    title: str
    company: str
    location: str
    description: str
    salary_raw: str | None
    posted_date: str | None
    scraped_at: datetime
    raw_html: str


def random_delay_seconds(low: float = 2.0, high: float = 5.0) -> float:
    """Return a random delay in seconds."""
    return random.uniform(low, high)


async def polite_delay(low: float = 2.0, high: float = 5.0) -> None:
    """Sleep for a random duration to be polite to servers."""
    await asyncio.sleep(random_delay_seconds(low, high))


async def fetch_url_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    backoff_seconds: tuple[float, ...] = (5.0, 15.0, 45.0),
    timeout: float = 30.0,
) -> httpx.Response:
    """GET with exponential backoff on failure (3 attempts after first)."""
    last_exc: Exception | None = None
    attempts = 1 + len(backoff_seconds)
    for i in range(attempts):
        try:
            logger.info("HTTP GET %s (attempt %s)", url, i + 1)
            r = await client.get(url, timeout=timeout)
            logger.info("HTTP %s %s", r.status_code, url)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            logger.warning("Request failed %s: %s", url, e)
            if i < len(backoff_seconds):
                await asyncio.sleep(backoff_seconds[i])
    assert last_exc is not None
    raise last_exc
