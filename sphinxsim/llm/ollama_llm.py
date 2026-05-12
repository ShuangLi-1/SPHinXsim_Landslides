"""Ollama-backed LLM provider for SPHinXsim config generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict
from urllib import error, request

from sphinxsim.config.schemas import SimulationConfig


@dataclass
class OllamaLLM:
    """Generate and update SimulationConfig using a local Ollama server."""

    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"
    timeout: float = 60.0

    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/chat"

    def _post_chat(self, *, messages: list) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            # Ask Ollama to return a JSON object in message.content.
            "format": "json",
            "messages": messages,
        }

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self._endpoint(),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(
                "Failed to contact Ollama server. "
                "Ensure Ollama is running and OLLAMA_BASE_URL is correct."
            ) from exc

        data = json.loads(raw)
        message = data.get("message") or {}
        content = message.get("content", "")

        if isinstance(content, dict):
            return content

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response")

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()

        return json.loads(text)

    @staticmethod
    def _example_config() -> Dict[str, Any]:
        """Return a canonical example config (via MockLLM) for few-shot prompting."""
        from sphinxsim.llm.mock_llm import MockLLM

        return json.loads(MockLLM().generate("water dam break simulation").model_dump_json(exclude_none=True))

    _BODY_TYPE_RULES: str = (
        "STRICT RULES — you must follow these exactly: "
        "(1) fluid_bodies may ONLY contain entries whose material.type is 'weakly_compressible_fluid'. "
        "(2) solid_bodies may ONLY contain entries whose material.type is 'rigid_body'. "
        "(3) observers[].variable.real_type must be a plain string such as 'Pressure', never a list. "
        "(4) Return ONLY the JSON object — no markdown fences, no comments, no extra keys."
    )

    def generate(self, description: str) -> SimulationConfig:
        if not description or not description.strip():
            raise ValueError("description must not be empty")

        system = (
            "You are a simulator configuration generator. "
            "Return ONLY valid JSON in exactly the same structure as 'example_output', "
            "with values adapted for the new description. "
        ) + self._BODY_TYPE_RULES
        user = {
            "description": description,
            "example_output": self._example_config(),
        }

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ]
        data = self._post_chat(messages=messages)
        return SimulationConfig(**data)

    def update(self, existing: SimulationConfig, description: str) -> SimulationConfig:
        if not description or not description.strip():
            raise ValueError("description must not be empty")

        existing_json = existing.model_dump_json(exclude_none=True)
        system = (
            f"You revise simulator configurations. "
            f"The update instruction is: \"{description}\". "
            f"Apply it to the JSON config the user provides and return ONLY the full updated JSON "
            f"in the same structure, with only the requested changes applied. "
        ) + self._BODY_TYPE_RULES

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": existing_json},
        ]
        data = self._post_chat(messages=messages)
        return SimulationConfig(**data)
