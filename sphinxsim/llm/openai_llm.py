# sphinxsim/llm/openai_llm.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.config.update_patch import UpdatePatch

# OpenAI SDK (new-style)
from openai import OpenAI


@dataclass
class OpenAILLM:
    model: str = "gpt-4.1-mini"  # pick what you want
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        self.client = OpenAI(api_key=self.api_key)

    def generate(self, description: str) -> SimulationConfig:
        if not description or not description.strip():
            raise ValueError("description must not be empty")

        # If SimulationConfig is Pydantic v2, you can use model_json_schema()
        schema = SimulationConfig.model_json_schema()

        system = (
            "You are a simulator configuration generator. "
            "Return ONLY valid JSON that conforms to the provided JSON Schema. "
            "Do not include markdown, comments, or extra keys."
        )

        user = {
            "description": description,
            "json_schema": schema,
        }

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            temperature=0,  # deterministic-ish
        )

        content = resp.choices[0].message.content or ""
        data: Dict[str, Any] = json.loads(content)

        # Final safety: schema validation on your side
        return SimulationConfig(**data)

    def update(self, existing: SimulationConfig, description: str) -> SimulationConfig:
        if not description or not description.strip():
            raise ValueError("description must not be empty")

        schema = SimulationConfig.model_json_schema()

        system = (
            "You revise simulator configurations. "
            "Given an existing config and an update instruction, return ONLY the full updated JSON "
            "that conforms to the provided JSON Schema. "
            "Do not include markdown, comments, or extra keys."
        )

        user = {
            "instruction": description,
            "existing_config": existing.model_dump(),
            "json_schema": schema,
        }

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            temperature=0,
        )

        content = resp.choices[0].message.content or ""
        data: Dict[str, Any] = json.loads(content)
        return SimulationConfig(**data)

    @staticmethod
    def _dict_diff(base: Any, updated: Any) -> Any:
        if isinstance(base, dict) and isinstance(updated, dict):
            changed: Dict[str, Any] = {}
            for key in updated.keys():
                if key not in base:
                    changed[key] = updated[key]
                    continue
                child = OpenAILLM._dict_diff(base[key], updated[key])
                if child is not None:
                    changed[key] = child
            return changed if changed else None

        if isinstance(base, list) and isinstance(updated, list):
            if base != updated:
                return updated
            return None

        if base != updated:
            return updated
        return None

    def update_patch(self, existing: SimulationConfig, description: str, strict: bool = True) -> Dict[str, Any]:
        updated = self.update(existing, description)
        base = existing.model_dump(exclude_none=True)
        target = updated.model_dump(exclude_none=True)
        delta = self._dict_diff(base, target) or {}
        patch = UpdatePatch(
            strict=strict,
            operations=[
                {
                    "op": "merge_object",
                    "path": "",
                    "value": delta,
                }
            ],
        )
        return patch.model_dump(exclude_none=True)

    def explore(self, question: str, context: str | None = None) -> str:
        if not question or not question.strip():
            raise ValueError("question must not be empty")

        system = (
            "You explain SPHinXsim schema and simulator functionality. "
            "Be accurate, concise, and practical."
        )
        user = {
            "question": question,
            "context": context or "",
        }

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            temperature=0,
        )

        content = resp.choices[0].message.content or ""
        answer = content.strip()
        if not answer:
            raise ValueError("OpenAI returned an empty exploration answer")
        return answer
    