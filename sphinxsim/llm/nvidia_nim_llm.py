"""NVIDIA NIM-backed LLM provider for SPHinXsim config generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict
from urllib import error, request

from pydantic import ValidationError

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.config.update_patch import UpdatePatch
from sphinxsim.llm.ollama_llm import OllamaLLM


@dataclass
class NvidiaNIMLLM:
    """Generate and update SimulationConfig using NVIDIA NIM's OpenAI-compatible API."""

    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "z-ai/glm-5.2"
    fallback_models: tuple[str, ...] = ()
    api_key: str | None = None
    timeout: float = 60.0
    _BODY_TYPE_RULES: str = (
        "STRICT RULES — you must follow these exactly: "
        "(1) fluid_bodies may ONLY contain entries whose material.type is 'weakly_compressible_fluid'. "
        "(2) solid_bodies may ONLY contain entries whose material.type is 'rigid_body'. "
        "(3) observers[].variable.real_type must be a plain string such as 'Pressure', never a list. "
        "(4) Return ONLY the JSON object — no markdown fences, no comments, no extra keys."
    )

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "NVIDIA NIM API key is required. Set NVIDIA_NIM_API_KEY or NVIDIA_API_KEY."
            )
        self.model = self.model.strip()
        self.fallback_models = tuple(
            m.strip() for m in self.fallback_models if isinstance(m, str) and m.strip() and m.strip() != self.model
        )

    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @staticmethod
    def _extract_error_detail(raw_detail: str) -> str:
        text = (raw_detail or "").strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except Exception:
            return text
        if isinstance(parsed, dict):
            detail = parsed.get("detail")
            if isinstance(detail, str):
                return detail
        return text

    @staticmethod
    def _is_degraded_model_error(http_code: int, detail: str) -> bool:
        if http_code != 400:
            return False
        normalized = detail.lower()
        return "degraded" in normalized and "cannot be invoked" in normalized

    def _post_chat(self, *, messages: list[dict[str, Any]], temperature: float = 0.0) -> str:
        model_candidates = (self.model,) + self.fallback_models
        last_http_error: tuple[int, str] | None = None

        for model_name in model_candidates:
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "top_p": 1,
                "stream": False,
            }
            body = json.dumps(payload).encode("utf-8")
            req = request.Request(
                self._endpoint(),
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )

            try:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                break
            except error.HTTPError as exc:
                detail_raw = exc.read().decode("utf-8", errors="ignore")
                detail = self._extract_error_detail(detail_raw)
                last_http_error = (exc.code, detail)
                if self._is_degraded_model_error(exc.code, detail) and model_name != model_candidates[-1]:
                    continue
                if self._is_degraded_model_error(exc.code, detail):
                    raise RuntimeError(
                        "NVIDIA NIM model is currently unavailable (degraded). "
                        "Set NVIDIA_NIM_MODEL to an available model and optionally set "
                        "NVIDIA_NIM_FALLBACK_MODELS with comma-separated alternatives. "
                        f"Detail: {detail}"
                    ) from exc
                raise RuntimeError(f"NVIDIA NIM request failed with HTTP {exc.code}: {detail}") from exc
            except error.URLError as exc:
                raise RuntimeError(
                    "Failed to contact NVIDIA NIM. Ensure NVIDIA_NIM_BASE_URL is correct and network is available."
                ) from exc
            except TimeoutError as exc:
                raise RuntimeError(
                    "NVIDIA NIM request timed out. Increase NVIDIA_NIM_TIMEOUT or use a smaller prompt/model."
                ) from exc
            except OSError as exc:
                raise RuntimeError("Failed during NVIDIA NIM request.") from exc
        else:
            if last_http_error is not None:
                code, detail = last_http_error
                raise RuntimeError(f"NVIDIA NIM request failed with HTTP {code}: {detail}")
            raise RuntimeError("NVIDIA NIM request failed before sending request.")

        data = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("NVIDIA NIM returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            content = "".join(parts)

        if not isinstance(content, str) or not content.strip():
            raise ValueError("NVIDIA NIM returned an empty response")

        return content.strip()

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return text

    @staticmethod
    def _dict_diff(base: Any, updated: Any) -> Any:
        if isinstance(base, dict) and isinstance(updated, dict):
            changed: Dict[str, Any] = {}
            for key in updated.keys():
                if key not in base:
                    changed[key] = updated[key]
                    continue
                child = NvidiaNIMLLM._dict_diff(base[key], updated[key])
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

    def _load_json_content(self, content: str) -> Dict[str, Any]:
        cleaned = self._strip_code_fences(content)
        return json.loads(cleaned)

    @staticmethod
    def _example_config(description: str) -> Dict[str, Any]:
        return OllamaLLM._example_config(description)

    @staticmethod
    def _merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        return OllamaLLM._merge_dicts(base, updates)

    @staticmethod
    def _sanitize_config_dict(cfg: Dict[str, Any]) -> Dict[str, Any]:
        return OllamaLLM._sanitize_config_dict(cfg)

    @staticmethod
    def _infer_requested_simulation_type(description: str) -> str | None:
        text = (description or "").lower()
        if not text:
            return None

        asks_for_type_change = bool(
            re.search(r"\b(simulation|simulaiton|type|switch|change|convert)\b", text)
        )
        if not asks_for_type_change:
            return None

        if "continuum" in text:
            return "continuum_dynamics"
        if "fluid" in text:
            return "fluid_dynamics"
        return None

    @staticmethod
    def _coerce_simulation_type(existing: Dict[str, Any], target_type: str) -> Dict[str, Any]:
        updated = json.loads(json.dumps(existing))
        updated["simulation_type"] = target_type
        updated.setdefault("solver_parameters", {})

        if target_type == "continuum_dynamics":
            updated["solver_parameters"].setdefault("continuum_dynamics", {})
            if not updated.get("continuum_bodies"):
                shape_names: list[str] = []
                for shape in updated.get("geometries", {}).get("shapes", []):
                    if isinstance(shape, dict) and isinstance(shape.get("name"), str):
                        shape_names.append(shape["name"])

                if not shape_names and updated.get("fluid_bodies"):
                    shape_names = [
                        body.get("name")
                        for body in updated.get("fluid_bodies", [])
                        if isinstance(body, dict) and isinstance(body.get("name"), str)
                    ]

                if shape_names:
                    updated["continuum_bodies"] = [
                        {
                            "name": shape_names[0],
                            "material": {
                                "type": "general_continuum",
                                "density": 1000.0,
                                "sound_speed": 100.0,
                                "youngs_modulus": 1000000.0,
                                "poisson_ratio": 0.3,
                            },
                        }
                    ]

        if target_type == "fluid_dynamics":
            updated["solver_parameters"].setdefault("fluid_dynamics", {})
            if not updated.get("fluid_bodies"):
                shape_names: list[str] = []
                for shape in updated.get("geometries", {}).get("shapes", []):
                    if isinstance(shape, dict) and isinstance(shape.get("name"), str):
                        shape_names.append(shape["name"])
                if shape_names:
                    updated["fluid_bodies"] = [
                        {
                            "name": shape_names[0],
                            "material": {
                                "type": "weakly_compressible_fluid",
                                "density": 1000.0,
                            },
                        }
                    ]

        return updated

    @staticmethod
    def _infer_requested_shape_rename(description: str) -> tuple[str, str] | None:
        text = (description or "").strip()
        if not text:
            return None

        # Prefer quoted rename targets first to support broader shape names.
        quoted_patterns = [
            r"(?:shape\s+name|shape|rename|change)\s+[\"']([^\"']+)[\"']\s+(?:to|as)\s+[\"']([^\"']+)[\"']",
            r"rename\s+[\"']([^\"']+)[\"']\s+to\s+[\"']([^\"']+)[\"']",
        ]
        for pattern in quoted_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            old_name = match.group(1).strip()
            new_name = match.group(2).strip()
            if old_name and new_name and old_name != new_name:
                return old_name, new_name

        patterns = [
            r"(?:shape\s+name|shape|rename)\s+['\"]?([A-Za-z_][\w]*)['\"]?\s+(?:to|as)\s+['\"]?([A-Za-z_][\w]*)['\"]?",
            r"change\s+['\"]?([A-Za-z_][\w]*)['\"]?\s+to\s+['\"]?([A-Za-z_][\w]*)['\"]?",
        ]
        lowered = text.lower()
        if "shape" not in lowered and "rename" not in lowered and "change" not in lowered:
            return None

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            old_name = match.group(1)
            new_name = match.group(2)
            if old_name != new_name:
                return old_name, new_name
        return None

    @staticmethod
    def _apply_shape_rename(config_dict: Dict[str, Any], old_name: str, new_name: str) -> Dict[str, Any]:
        updated = json.loads(json.dumps(config_dict))

        for shape in updated.get("geometries", {}).get("shapes", []):
            if not isinstance(shape, dict):
                continue
            if shape.get("name") == old_name:
                shape["name"] = new_name
            if shape.get("original") == old_name:
                shape["original"] = new_name
            sub_shapes = shape.get("sub_shapes")
            if isinstance(sub_shapes, list):
                shape["sub_shapes"] = [new_name if item == old_name else item for item in sub_shapes]

        for section in ("fluid_bodies", "continuum_bodies", "solid_bodies"):
            for body in updated.get(section, []):
                if isinstance(body, dict) and body.get("name") == old_name:
                    body["name"] = new_name

        settings = updated.get("particle_generation", {}).get("settings", {})
        for body in settings.get("bodies", []):
            if isinstance(body, dict) and body.get("name") == old_name:
                body["name"] = new_name
        for constraint in settings.get("relaxation_constraints", []):
            if isinstance(constraint, dict) and constraint.get("body_name") == old_name:
                constraint["body_name"] = new_name

        for observer in updated.get("observers", []):
            if isinstance(observer, dict) and observer.get("observed_body") == old_name:
                observer["observed_body"] = new_name

        for bc in updated.get("fluid_boundary_conditions", []):
            if isinstance(bc, dict) and bc.get("body_name") == old_name:
                bc["body_name"] = new_name

        for constraint in updated.get("body_constraints", []):
            if isinstance(constraint, dict) and constraint.get("body_name") == old_name:
                constraint["body_name"] = new_name

        for initial_condition in updated.get("initial_conditions", []):
            if isinstance(initial_condition, dict) and initial_condition.get("body_name") == old_name:
                initial_condition["body_name"] = new_name

        for entry in updated.get("extra_state_recording", []):
            if isinstance(entry, dict) and entry.get("name") == old_name:
                entry["name"] = new_name

        return updated

    def generate(self, description: str) -> SimulationConfig:
        if not description or not description.strip():
            raise ValueError("description must not be empty")

        system = (
            "You are a simulator configuration generator. "
            "Return ONLY valid JSON in exactly the same structure as 'example_output', "
            "with values adapted for the new description. "
            "Choose the correct simulation type and body/material families for the requested physics. "
        ) + self._BODY_TYPE_RULES
        example_cfg = self._example_config(description)
        user = {
            "description": description,
            "example_output": example_cfg,
        }

        content = self._post_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            temperature=0.0,
        )

        data = self._load_json_content(content)
        if not isinstance(data, dict):
            raise ValueError("NVIDIA NIM returned an invalid generation response")

        merged = self._merge_dicts(example_cfg, data)
        merged = self._sanitize_config_dict(merged)
        try:
            return SimulationConfig(**merged)
        except Exception:
            repaired = self._merge_dicts(merged, example_cfg)
            repaired = self._sanitize_config_dict(repaired)
            return SimulationConfig(**repaired)

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

        content = self._post_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": existing_json},
            ],
            temperature=0.0,
        )

        data = self._load_json_content(content)
        if not isinstance(data, dict):
            raise ValueError("NVIDIA NIM returned an invalid update response")

        merged = self._merge_dicts(existing_dict, data)
        requested_type = self._infer_requested_simulation_type(description)
        requested_shape_rename = self._infer_requested_shape_rename(description)
        if requested_type is not None:
            merged = self._coerce_simulation_type(merged, requested_type)
        if requested_shape_rename is not None:
            merged = self._apply_shape_rename(merged, requested_shape_rename[0], requested_shape_rename[1])
        merged = self._sanitize_config_dict(merged)
        try:
            return SimulationConfig(**merged)
        except ValidationError as exc:
            safe_validation_errors = json.loads(json.dumps(exc.errors(), default=str))
            retry_system = (
                "You are repairing a simulator config update that failed schema validation. "
                f"Apply this instruction: \"{description}\". "
                "Return ONLY full valid JSON. Preserve existing structure and non-target fields. "
                "Fix all reported validation errors. "
            ) + self._BODY_TYPE_RULES
            retry_user = {
                "instruction": description,
                "existing_config": existing_dict,
                "candidate_config": merged,
                "validation_errors": safe_validation_errors,
                "example_output": self._example_config(description),
            }
            retry_content = self._post_chat(
                messages=[
                    {"role": "system", "content": retry_system},
                    {"role": "user", "content": json.dumps(retry_user)},
                ],
                temperature=0.0,
            )
            retry_data = self._load_json_content(retry_content)
            if isinstance(retry_data, dict):
                retried = self._merge_dicts(existing_dict, retry_data)
                if requested_type is not None:
                    retried = self._coerce_simulation_type(retried, requested_type)
                if requested_shape_rename is not None:
                    retried = self._apply_shape_rename(retried, requested_shape_rename[0], requested_shape_rename[1])
                retried = self._sanitize_config_dict(retried)
                try:
                    return SimulationConfig(**retried)
                except ValidationError:
                    pass

            if requested_type is not None:
                coerced = self._coerce_simulation_type(existing_dict, requested_type)
                if requested_shape_rename is not None:
                    coerced = self._apply_shape_rename(coerced, requested_shape_rename[0], requested_shape_rename[1])
                coerced = self._sanitize_config_dict(coerced)
                return SimulationConfig(**coerced)

            if requested_shape_rename is not None:
                renamed = self._apply_shape_rename(existing_dict, requested_shape_rename[0], requested_shape_rename[1])
                renamed = self._sanitize_config_dict(renamed)
                return SimulationConfig(**renamed)

            raise

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

        content = self._post_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            temperature=0.0,
        )
        answer = self._strip_code_fences(content).strip()
        if not answer:
            raise ValueError("NVIDIA NIM returned an empty exploration answer")
        return answer
