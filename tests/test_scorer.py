"""Scorer tests with mocked ollama."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.scorer import score_listing, weighted_overall


def test_weighted_overall_defaults() -> None:
    w = {"fit": 0.4, "preference": 0.35, "competitiveness": 0.25}
    assert weighted_overall(100, 100, 100, w) == 100.0
    assert weighted_overall(80, 80, 80, w) == 80.0


@patch("pipeline.scorer.ollama.Client")
def test_score_listing_parses_json(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    content = (
        '{"fit_score": 72, "fit_reason": "ok", "pref_score": 80, "pref_reason": "ok", '
        '"comp_score": 65, "comp_reason": "ok"}'
    )
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    mock_client.chat.return_value = resp

    profile = {
        "name": "Test",
        "scoring_weights": {"fit": 0.4, "preference": 0.35, "competitiveness": 0.25},
    }
    settings = {
        "ollama_model": "dummy",
        "ollama_host": "http://127.0.0.1:11434",
        "ollama_timeout_seconds": 5,
    }
    out = score_listing(
        profile,
        "Title",
        "Co",
        "Remote",
        "Not specified",
        "remote",
        "Do Python and SQL.",
        settings=settings,
    )
    assert out is not None
    assert out.fit_score == 72
    assert out.pref_score == 80
    assert out.comp_score == 65
    assert out.overall_score > 0
