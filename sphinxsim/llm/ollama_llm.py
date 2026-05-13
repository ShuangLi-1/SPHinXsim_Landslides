"""Ollama-backed LLM provider for SPHinXsim config generation."""

from __future__ import annotations

import json
import re
from difflib import get_close_matches
from dataclasses import dataclass
from pathlib import Path
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

    def _post_chat(self, *, messages: list, format_json: bool = True) -> Any:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": messages,
        }
        if format_json:
            payload["format"] = "json"

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

        if not format_json:
            return text

        return json.loads(text)

    @staticmethod
    def _example_config(description: str) -> Dict[str, Any]:
        """Return a validated fixture-backed example config for few-shot prompting."""
        project_root = Path(__file__).resolve().parents[2]
        fluid_fixture = (
            project_root
            / "tests"
            / "test_simulation"
            / "test_2d_simulation"
            / "data"
            / "dambreak.json"
        )
        solid_fixture = (
            project_root
            / "tests"
            / "test_simulation"
            / "test_2d_simulation"
            / "data"
            / "milling.json"
        )

        desc = (description or "").lower()
        is_solid_like = any(
            token in desc for token in ("solid", "elastic", "beam", "continuum", "milling")
        )

        preferred = solid_fixture if is_solid_like else fluid_fixture
        fallback = fluid_fixture if preferred == solid_fixture else solid_fixture

        for fixture in (preferred, fallback):
            try:
                payload = json.loads(fixture.read_text())
                validated = SimulationConfig.model_validate(payload)
                return json.loads(validated.model_dump_json(exclude_none=True))
            except Exception:
                continue

        # Last resort if fixture files are unavailable/corrupt.
        from sphinxsim.llm.mock_llm import MockLLM

        return json.loads(MockLLM().generate(description).model_dump_json(exclude_none=True))

    @staticmethod
    def _merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = OllamaLLM._merge_dicts(merged[key], value)
            elif isinstance(value, list) and isinstance(merged.get(key), list):
                base_list = merged[key]
                if all(isinstance(item, dict) for item in value) and all(
                    isinstance(item, dict) for item in base_list[: len(value)]
                ):
                    merged[key] = [
                        OllamaLLM._merge_dicts(base_item, update_item)
                        for base_item, update_item in zip(base_list, value)
                    ] + base_list[len(value) :]
                else:
                    merged[key] = value
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _apply_explicit_instruction_overrides(cfg: Dict[str, Any], description: str) -> Dict[str, Any]:
        updated = json.loads(json.dumps(cfg))

        time_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b",
            description,
            re.IGNORECASE,
        )
        if time_match:
            updated.setdefault("solver_parameters", {})["end_time"] = float(time_match.group(1))

        res_match = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+resolution", description, re.IGNORECASE)
        if res_match:
            updated.setdefault("geometries", {}).setdefault("global_resolution", {})["particle_spacing"] = (
                float(res_match.group(1)) / 1000.0
            )

        return updated

    @staticmethod
    def _sanitize_config_dict(cfg: Dict[str, Any]) -> Dict[str, Any]:
        updated = json.loads(json.dumps(cfg))

        # Keep generated/output configs robust for runtime by omitting optional
        # scaling hints that small models frequently corrupt.
        updated.pop("characteristic_dimensions", None)

        shapes = updated.get("geometries", {}).get("shapes", [])
        shape_names = {
            shape.get("name")
            for shape in shapes
            if isinstance(shape, dict) and shape.get("name")
        }

        rename_map: Dict[str, str] = {}
        shape_rename_map: Dict[str, str] = {}

        def _canonical_name(name: str | None) -> str | None:
            if not name:
                return name
            if name in shape_names:
                return name
            candidates = get_close_matches(name, list(shape_names), n=1, cutoff=0.6)
            if candidates:
                return candidates[0]
            return name

        # Build a map of potential typos in shape names themselves
        # by looking for common misspellings (e.g., Wal* → Wall*)
        for shape in shapes:
            if not isinstance(shape, dict):
                continue
            name = shape.get("name")
            if name and "Wal" in name and name not in shape_names:
                # Potential typo like WalInnerBox → WallInnerBox
                corrected = name.replace("Wal", "Wall")
                if corrected in shape_names:
                    shape_rename_map[name] = corrected
                    shape["name"] = corrected
                    # Update shape_names set to reflect the rename
                    shape_names.discard(name)
                    shape_names.add(corrected)

        # Second pass: fix shape references that point to typoed names.
        for shape in shapes:
            if not isinstance(shape, dict):
                continue
            original = shape.get("original")
            if isinstance(original, str):
                original = shape_rename_map.get(original, original)
                shape["original"] = _canonical_name(original)
            sub_shapes = shape.get("sub_shapes")
            if isinstance(sub_shapes, list):
                shape["sub_shapes"] = [
                    _canonical_name(shape_rename_map.get(item, item) if isinstance(item, str) else item)
                    if isinstance(item, str)
                    else item
                    for item in sub_shapes
                ]

        for body in updated.get("fluid_bodies", []):
            if not isinstance(body, dict):
                continue
            old = body.get("name")
            new = _canonical_name(old)
            if old and new and old != new:
                rename_map[old] = new
                body["name"] = new

        for body in updated.get("solid_bodies", []):
            if not isinstance(body, dict):
                continue
            old = body.get("name")
            new = _canonical_name(old)
            if old and new and old != new:
                rename_map[old] = new
                body["name"] = new

        # Also canonicalize body names in extra_state_recording to catch typos from LLM output
        all_body_names = {
            body.get("name")
            for bodies_list in [
                updated.get("fluid_bodies", []),
                updated.get("solid_bodies", []),
                updated.get("continuum_bodies", []),
            ]
            for body in bodies_list
            if isinstance(body, dict) and body.get("name")
        }

        for entry in updated.get("extra_state_recording", []):
            if not isinstance(entry, dict):
                continue
            old_name = entry.get("name")
            if old_name and old_name not in all_body_names:
                candidates = get_close_matches(old_name, list(all_body_names), n=1, cutoff=0.6)
                if candidates:
                    rename_map[old_name] = candidates[0]

        for entry in updated.get("particle_generation", {}).get("settings", {}).get("bodies", []):
            if isinstance(entry, dict) and entry.get("name") in rename_map:
                entry["name"] = rename_map[entry["name"]]

        for entry in updated.get("observers", []):
            if isinstance(entry, dict) and entry.get("observed_body") in rename_map:
                entry["observed_body"] = rename_map[entry["observed_body"]]

        for entry in updated.get("fluid_boundary_conditions", []):
            if isinstance(entry, dict) and entry.get("body_name") in rename_map:
                entry["body_name"] = rename_map[entry["body_name"]]

        for entry in updated.get("body_constraints", []):
            if isinstance(entry, dict) and entry.get("body_name") in rename_map:
                entry["body_name"] = rename_map[entry["body_name"]]

        for entry in updated.get("extra_state_recording", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("name") in rename_map:
                entry["name"] = rename_map[entry["name"]]
            for variable in entry.get("variables", []):
                if not isinstance(variable, dict):
                    continue
                real_type = variable.get("real_type")
                vector_type = variable.get("vector_type")
                if isinstance(real_type, str):
                    variable["real_type"] = [real_type]
                if isinstance(vector_type, str):
                    variable["vector_type"] = [vector_type]

        settings = updated.get("particle_generation", {}).get("settings", {})
        bodies = settings.get("bodies", [])
        fluid_names = {body.get("name") for body in updated.get("fluid_bodies", [])}
        solid_names = {body.get("name") for body in updated.get("solid_bodies", [])}

        for body in bodies:
            if not isinstance(body, dict):
                continue
            name = body.get("name")
            solid_body = body.get("solid_body")

            if name in solid_names:
                body["solid_body"] = {} if not isinstance(solid_body, dict) else solid_body
            elif name in fluid_names and not isinstance(solid_body, dict):
                body.pop("solid_body", None)

        return updated

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
            "Choose the correct simulation type and body/material families for the requested physics. "
        ) + self._BODY_TYPE_RULES
        user = {
            "description": description,
            "example_output": self._example_config(description),
        }

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ]
        data = self._post_chat(messages=messages)
        if not isinstance(data, dict):
            raise ValueError("Ollama returned an invalid generation response")
        merged = self._merge_dicts(self._example_config(description), data)
        merged = self._sanitize_config_dict(merged)
        return SimulationConfig(**merged)

    def update(self, existing: SimulationConfig, description: str) -> SimulationConfig:
        if not description or not description.strip():
            raise ValueError("description must not be empty")

        existing_dict = existing.model_dump(exclude_none=True)
        existing_json = json.dumps(existing_dict)
        system = (
            f"You revise simulator configurations. "
            f"The update instruction is: \"{description}\". "
            f"Apply it to the JSON config the user provides and return ONLY the full updated JSON "
            f"in the same structure, with only the requested changes applied. "
            f"Preserve all existing fields unless the instruction explicitly changes them. "
            f"Do not remove arrays like geometries.shapes or body definitions. "
        ) + self._BODY_TYPE_RULES

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": existing_json},
        ]
        data = self._post_chat(messages=messages)
        if not isinstance(data, dict):
            raise ValueError("Ollama returned an invalid update response")
        merged = self._merge_dicts(existing_dict, data)
        if merged == existing_dict:
            patch_system = (
                f"You revise simulator configurations. The instruction is: \"{description}\". "
                f"Return ONLY a minimal JSON patch object containing changed fields. "
                f"Examples: {{\"solver_parameters\": {{\"end_time\": 2.0}}}} or "
                f"{{\"geometries\": {{\"global_resolution\": {{\"particle_spacing\": 0.005}}}}}}."
            )
            patch_user = {
                "instruction": description,
                "existing_config": existing_dict,
            }
            patch_data = self._post_chat(
                messages=[
                    {"role": "system", "content": patch_system},
                    {"role": "user", "content": json.dumps(patch_user)},
                ]
            )
            if isinstance(patch_data, dict):
                merged = self._merge_dicts(existing_dict, patch_data)
        merged = self._apply_explicit_instruction_overrides(merged, description)
        merged = self._sanitize_config_dict(merged)
        return SimulationConfig(**merged)

    def explore(self, question: str, context: str | None = None) -> str:
        if not question or not question.strip():
            raise ValueError("question must not be empty")

        system = (
            "You explain SPHinXsim schema and simulator functionality. "
            "Answer in plain text. Be concise, accurate, and practical."
        )
        user = {
            "question": question,
            "context": context or "",
        }

        answer = self._post_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            format_json=False,
        )
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Ollama returned an invalid exploration answer")
        return answer.strip()
