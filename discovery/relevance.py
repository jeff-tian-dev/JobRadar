"""LLM-based relevance pre-filter for discovered companies."""

from __future__ import annotations

import json
import logging
from typing import Any

import ollama

from pipeline.config_paths import prompts_dir

logger = logging.getLogger(__name__)


def _load_prompt() -> str:
    """Load the relevance filter system prompt."""
    path = prompts_dir() / "relevance_filter.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        "Given a candidate profile and a company description, determine if this company "
        "is likely to have roles the candidate would be interested in. "
        "Return ONLY valid JSON: "
        '{"relevant": true/false, "score": <int 0-100>, "reason": "<one sentence>"}'
    )


def score_company_relevance(
    company_name: str,
    company_description: str | None,
    industry: str | None,
    profile: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[int, str]:
    """Ask the local LLM whether this company is relevant to the candidate profile.

    Returns (score 0-100, reason string). Returns (50, "LLM unavailable") on failure.
    """
    model = settings.get("ollama_model", "qwen3:14b")
    host = settings.get("ollama_host", "http://127.0.0.1:11434")

    prompt = _load_prompt()

    # Build a compact profile summary to keep the prompt short
    prefs = profile.get("preferences", {})
    profile_summary = (
        f"Candidate summary: {profile.get('summary', '')[:500]}\n"
        f"Target titles: {prefs.get('target_titles', [])}\n"
        f"Industries preferred: {prefs.get('industries_preferred', [])}\n"
        f"Deal breakers: {prefs.get('deal_breakers', [])}\n"
        f"Skills: {list(profile.get('skills', {}).get('expert', []))[:10]}"
    )

    company_info = (
        f"Company: {company_name}\n"
        f"Industry: {industry or 'unknown'}\n"
        f"Description: {(company_description or 'No description available')[:400]}"
    )

    user_message = f"{profile_summary}\n\n---\n\n{company_info}"

    for attempt in range(2):
        try:
            client = ollama.Client(host=host)
            response = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message},
                ],
                format="json",
                options={"temperature": 0.1},
            )
            raw = response["message"]["content"]
            data = json.loads(raw)
            score = int(data.get("score", 50))
            score = max(0, min(100, score))
            reason = str(data.get("reason", ""))
            return score, reason
        except Exception as e:
            if attempt == 0:
                logger.debug("Relevance scoring attempt 1 failed for %s: %s", company_name, e)
            else:
                logger.warning("Relevance scoring failed for %s: %s", company_name, e)

    return 50, "LLM unavailable"
