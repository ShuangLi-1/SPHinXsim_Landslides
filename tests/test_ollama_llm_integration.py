"""Integration tests for OllamaLLM against a live Ollama server.

These tests are:
- Skipped automatically when the Ollama server is unreachable.
- Skipped in CI environments (GitHub Actions, etc.) where Ollama is not available.
- Run locally after sourcing setup-local-env.sh with SPHINXSIM_LLM_PROVIDER=ollama.

To run locally:
    SPHINXSIM_LLM_PROVIDER=ollama pytest tests/test_ollama_llm_integration.py -v

To run all tests including mocked ones:
    pytest tests/ -v
"""

from __future__ import annotations

import os
from urllib import error, request

import pytest

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.llm import get_llm
from sphinxsim.llm.ollama_llm import OllamaLLM


def _ollama_reachable() -> bool:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=3):
            return True
    except (error.URLError, OSError):
        return False


def _is_ci_environment() -> bool:
    """Detect if running in a CI environment."""
    return bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS") or os.getenv("GITLAB_CI"))


skip_if_no_ollama = pytest.mark.skipif(
    not _ollama_reachable() or _is_ci_environment(),
    reason="Ollama server not reachable or running in CI environment",
)


@skip_if_no_ollama
@pytest.mark.integration
class TestOllamaLLMIntegration:
    def setup_method(self):
        self.llm = OllamaLLM(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            timeout=120.0,
        )

    def test_generate_returns_valid_config(self):
        cfg = self.llm.generate("simulate water flowing through a pipe")
        assert isinstance(cfg, SimulationConfig)

    def test_generate_schema_roundtrip(self):
        cfg = self.llm.generate("dam break simulation")
        restored = SimulationConfig.model_validate_json(cfg.model_dump_json())
        assert restored == cfg

    def test_update_returns_valid_config(self):
        base = self.llm.generate("water flow")
        updated = self.llm.update(base, "set end time to 2 s")
        assert isinstance(updated, SimulationConfig)

    def test_get_llm_returns_ollama_when_env_set(self, monkeypatch):
        """get_llm() must resolve to OllamaLLM when SPHINXSIM_LLM_PROVIDER=ollama."""
        monkeypatch.setenv("SPHINXSIM_LLM_PROVIDER", "ollama")
        llm = get_llm()
        assert isinstance(llm, OllamaLLM)
