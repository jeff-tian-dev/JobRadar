"""Ollama-based job listing scorer."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ollama
import yaml

from pipeline.config_paths import load_settings, prompts_dir
from pipeline.models import log_ollama_metrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoreResult:
    fit_score: int
    fit_reason: str
    pref_score: int
    pref_reason: str
    comp_score: int
    comp_reason: str
    overall_score: float


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _apply_user_template(
    template: str,
    profile_text: str,
    title: str,
    company: str,
    location: str,
    salary_display: str,
    remote_display: str,
    description: str,
) -> str:
    """Replace {{placeholders}}; escape accidental {{ in description by splitting known keys first."""
    out = template
    replacements = {
        "profile": profile_text,
        "title": title,
        "company": company,
        "location": location,
        "salary_display": salary_display,
        "remote_display": remote_display,
        "description": description,
    }
    for key, val in replacements.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _validate_scores(obj: dict[str, Any]) -> ScoreResult | None:
    try:
        fit = int(obj["fit_score"])
        pref = int(obj["pref_score"])
        comp = int(obj["comp_score"])
    except (KeyError, TypeError, ValueError):
        return None
    for n, name in ((fit, "fit"), (pref, "pref"), (comp, "comp")):
        if not 0 <= n <= 100:
            logger.warning("Score %s out of range: %s", name, n)
            return None
    return ScoreResult(
        fit_score=fit,
        fit_reason=str(obj.get("fit_reason", "")),
        pref_score=pref,
        pref_reason=str(obj.get("pref_reason", "")),
        comp_score=comp,
        comp_reason=str(obj.get("comp_reason", "")),
        overall_score=0.0,
    )


def weighted_overall(
    fit: int,
    pref: int,
    comp: int,
    weights: dict[str, float],
) -> float:
    w_fit = float(weights.get("fit", 0.4))
    w_pref = float(weights.get("preference", 0.35))
    w_comp = float(weights.get("competitiveness", 0.25))
    return w_fit * fit + w_pref * pref + w_comp * comp


def score_listing(
    profile: dict[str, Any],
    title: str,
    company: str,
    location: str,
    salary_display: str,
    remote_display: str,
    description: str,
    settings: dict[str, Any] | None = None,
) -> ScoreResult | None:
    """
    Call ollama once (retry once on JSON parse failure). Returns None on failure.
    """
    settings = settings or load_settings()
    model = str(settings.get("ollama_model", "qwen3:14b"))
    host = str(settings.get("ollama_host", "http://127.0.0.1:11434"))
    timeout = float(settings.get("ollama_timeout_seconds", 30))

    system_prompt = _read_text(prompts_dir() / "scoring_system.txt")
    user_template = _read_text(prompts_dir() / "scoring_user.txt")
    profile_text = yaml.dump(profile, default_flow_style=False, allow_unicode=True, sort_keys=False)
    user_prompt = _apply_user_template(
        user_template,
        profile_text,
        title,
        company,
        location,
        salary_display,
        remote_display,
        description,
    )

    client = ollama.Client(host=host, timeout=timeout)
    weights = profile.get("scoring_weights") or {}
    if not isinstance(weights, dict):
        weights = {}

    def _call() -> str | None:
        try:
            resp = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                format="json",
                options={"temperature": 0.1},
            )
        except Exception:
            logger.exception("Ollama request failed for listing: %s at %s", title, company)
            return None
        log_ollama_metrics(resp, f"score {title[:60]}@{company[:40]}")
        msg = getattr(resp, "message", None)
        content = getattr(msg, "content", None) if msg is not None else None
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            content = msg.get("content", content)
        if not content:
            logger.error("Empty ollama response for %s", title)
            return None
        return str(content)

    raw = _call()
    if raw is None:
        return None

    def _parse(content: str) -> ScoreResult | None:
        content = content.strip()
        # Strip markdown fences if model disobeys
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        try:
            obj = json.loads(content)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        res = _validate_scores(obj)
        if res is None:
            return None
        overall = weighted_overall(res.fit_score, res.pref_score, res.comp_score, weights)
        return ScoreResult(
            fit_score=res.fit_score,
            fit_reason=res.fit_reason,
            pref_score=res.pref_score,
            pref_reason=res.pref_reason,
            comp_score=res.comp_score,
            comp_reason=res.comp_reason,
            overall_score=overall,
        )

    result = _parse(raw)
    if result is not None:
        return result

    logger.warning("JSON parse failed; retrying once. Raw (truncated): %s", raw[:500])
    raw2 = _call()
    if raw2 is None:
        return None
    result2 = _parse(raw2)
    if result2 is None:
        logger.error("Scoring failed after retry. Raw (truncated): %s", raw2[:500])
    return result2


def scores_to_db_dict(sr: ScoreResult) -> dict[str, Any]:
    return {
        "fit_score": sr.fit_score,
        "fit_reason": sr.fit_reason,
        "pref_score": sr.pref_score,
        "pref_reason": sr.pref_reason,
        "comp_score": sr.comp_score,
        "comp_reason": sr.comp_reason,
        "overall_score": sr.overall_score,
    }
