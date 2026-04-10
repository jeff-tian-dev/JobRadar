"""Profile resolution tests."""

import pytest

from pipeline import config_paths


def test_effective_profile_id_cli_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_SEARCH_PROFILE", raising=False)
    assert config_paths.effective_profile_id("alice") == "alice"


def test_effective_profile_id_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_SEARCH_PROFILE", "bob")
    assert config_paths.effective_profile_id(None) == "bob"


def test_profile_yaml_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_SEARCH_PROFILE", raising=False)
    p = config_paths.profile_yaml_path("jeff", {"profiles_dir": "config/profiles"})
    assert p.name == "profile.yaml"
    assert "jeff" in str(p)


def test_read_ollama_repeat_penalty_default() -> None:
    assert config_paths.read_ollama_repeat_penalty({}) == 1.1
    assert config_paths.read_ollama_repeat_penalty(None) == 1.1


def test_read_ollama_repeat_penalty_from_settings() -> None:
    assert config_paths.read_ollama_repeat_penalty({"ollama_repeat_penalty": 1.15}) == 1.15
    assert config_paths.read_ollama_repeat_penalty({"ollama_repeat_penalty": "1.2"}) == 1.2


def test_read_ollama_repeat_penalty_invalid_falls_back() -> None:
    assert config_paths.read_ollama_repeat_penalty({"ollama_repeat_penalty": "nope"}) == 1.1
    assert config_paths.read_ollama_repeat_penalty({"ollama_repeat_penalty": 0.0}) == 1.1
    assert config_paths.read_ollama_repeat_penalty({"ollama_repeat_penalty": -1.0}) == 1.1
