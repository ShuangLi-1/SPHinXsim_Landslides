"""Tests for OllamaLLM (HTTP calls are fully mocked)."""

from __future__ import annotations

import io
import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from urllib import error as urllib_error

import pytest
from pydantic import ValidationError

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.llm.mock_llm import MockLLM
from sphinxsim.llm.ollama_llm import OllamaLLM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_raw(config: SimulationConfig) -> Dict[str, Any]:
    """Return the Ollama /api/chat JSON envelope wrapping *config*."""
    return {
        "message": {
            "role": "assistant",
            "content": config.model_dump_json(exclude_none=True),
        }
    }


def _make_response(payload: Dict[str, Any]):
    """Return a context-manager mock that reads *payload* as UTF-8 bytes."""
    raw = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# Canonical valid configs produced by the mock LLM (schema-correct by design).
_FLUID_CONFIG = MockLLM().generate("water dam break simulation")
_SOLID_CONFIG = MockLLM().generate("elastic beam bending under load")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestOllamaLLMInit:
    def test_defaults(self):
        llm = OllamaLLM()
        assert llm.base_url == "http://localhost:11434"
        assert llm.model == "qwen2.5:3b"
        assert llm.timeout == 60.0

    def test_custom_values(self):
        llm = OllamaLLM(base_url="http://myserver:11434", model="llama3", timeout=30.0)
        assert llm.base_url == "http://myserver:11434"
        assert llm.model == "llama3"
        assert llm.timeout == 30.0

    def test_endpoint_strips_trailing_slash(self):
        llm = OllamaLLM(base_url="http://localhost:11434/")
        assert llm._endpoint() == "http://localhost:11434/api/chat"


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestOllamaLLMGenerate:
    def setup_method(self):
        self.llm = OllamaLLM()

    def test_returns_simulation_config(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp):
            cfg = self.llm.generate("water dam break simulation")
        assert isinstance(cfg, SimulationConfig)

    def test_result_is_schema_valid(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp):
            cfg = self.llm.generate("water dam break simulation")
        restored = SimulationConfig.model_validate_json(cfg.model_dump_json())
        assert restored == cfg

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="description must not be empty"):
            self.llm.generate("")

    def test_whitespace_description_raises(self):
        with pytest.raises(ValueError):
            self.llm.generate("   ")

    def test_correct_endpoint_called(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            self.llm.generate("water flow")
        req = mock_open.call_args[0][0]
        assert req.full_url == "http://localhost:11434/api/chat"
        assert req.method == "POST"

    def test_request_contains_description(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            self.llm.generate("water flow through a pipe")
        req = mock_open.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        user_content = json.loads(body["messages"][1]["content"])
        assert "water flow through a pipe" in user_content["description"]

    def test_request_payload_has_format_json(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            self.llm.generate("water flow")
        body = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
        assert body.get("format") == "json"

    def test_request_payload_stream_false(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            self.llm.generate("water flow")
        body = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
        assert body["stream"] is False

    def test_request_includes_example_output(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            self.llm.generate("water flow")
        body = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
        user_content = json.loads(body["messages"][1]["content"])
        assert "example_output" in user_content

    def test_network_error_raises_runtime_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib_error.URLError("connection refused"),
        ):
            with pytest.raises(RuntimeError, match="Failed to contact Ollama server"):
                self.llm.generate("water flow")

    def test_empty_content_raises(self):
        resp = _make_response({"message": {"role": "assistant", "content": ""}})
        with patch("urllib.request.urlopen", return_value=resp):
            with pytest.raises(ValueError, match="Ollama returned an empty response"):
                self.llm.generate("water flow")

    def test_fenced_json_is_stripped(self):
        fenced = "```json\n" + _FLUID_CONFIG.model_dump_json(exclude_none=True) + "\n```"
        resp = _make_response({"message": {"role": "assistant", "content": fenced}})
        with patch("urllib.request.urlopen", return_value=resp):
            cfg = self.llm.generate("water flow")
        assert isinstance(cfg, SimulationConfig)

    def test_dict_content_accepted_directly(self):
        """Ollama may occasionally return JSON already decoded as a dict."""
        raw_dict = json.loads(_FLUID_CONFIG.model_dump_json(exclude_none=True))
        resp = _make_response({"message": {"role": "assistant", "content": raw_dict}})
        with patch("urllib.request.urlopen", return_value=resp):
            cfg = self.llm.generate("water flow")
        assert isinstance(cfg, SimulationConfig)

    def test_custom_model_sent_in_request(self):
        llm = OllamaLLM(model="llama3")
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            llm.generate("water flow")
        body = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
        assert body["model"] == "llama3"


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


class TestOllamaLLMUpdate:
    def setup_method(self):
        self.llm = OllamaLLM()

    def test_returns_simulation_config(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp):
            cfg = self.llm.update(_FLUID_CONFIG, "simulate for 3 s")
        assert isinstance(cfg, SimulationConfig)

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="description must not be empty"):
            self.llm.update(_FLUID_CONFIG, "")

    def test_whitespace_description_raises(self):
        with pytest.raises(ValueError):
            self.llm.update(_FLUID_CONFIG, "   ")

    def test_request_contains_existing_config(self):
        resp = _make_response(_mock_raw(_FLUID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            self.llm.update(_FLUID_CONFIG, "simulate for 3 s")
        body = json.loads(mock_open.call_args_list[0][0][0].data.decode("utf-8"))
        # The instruction is embedded in the system message; the user message is the raw config JSON.
        system_content = body["messages"][0]["content"]
        assert "simulate for 3 s" in system_content
        # User message is the existing config serialised as JSON.
        user_content = json.loads(body["messages"][1]["content"])
        assert "simulation_type" in user_content

    def test_result_is_schema_valid(self):
        resp = _make_response(_mock_raw(_SOLID_CONFIG))
        with patch("urllib.request.urlopen", return_value=resp):
            cfg = self.llm.update(_SOLID_CONFIG, "set end time to 2 s")
        restored = SimulationConfig.model_validate_json(cfg.model_dump_json())
        assert restored == cfg

    def test_network_error_raises_runtime_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib_error.URLError("connection refused"),
        ):
            with pytest.raises(RuntimeError, match="Failed to contact Ollama server"):
                self.llm.update(_FLUID_CONFIG, "change model")
