"""Shared utilities for SPHinXsim LLM providers.

This module centralizes provider-agnostic logic used by multiple LLM backends:
- robust JSON text cleanup
- dict merge/diff helpers
- fixture-backed example config selection
- config sanitization and typo canonicalization
- instruction intent helpers (simulation type and shape rename)
"""

from __future__ import annotations

import json
import re
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict

from sphinxsim.config.schemas import SimulationConfig

BODY_TYPE_RULES: str = (
    "STRICT RULES — you must follow these exactly: "
    "(1) fluid_bodies may ONLY contain entries whose material.type is 'weakly_compressible_fluid'. "
    "(2) solid_bodies may ONLY contain entries whose material.type is 'rigid_body'. "
    "(3) observers[].variable.real_type must be a plain string such as 'Pressure', never a list. "
    "(4) Return ONLY the JSON object — no markdown fences, no comments, no extra keys."
)


def strip_code_fences(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def json_safe_errors(errors: Any) -> Any:
    return json.loads(json.dumps(errors, default=str))


def dict_diff(base: Any, updated: Any) -> Any:
    if isinstance(base, dict) and isinstance(updated, dict):
        changed: Dict[str, Any] = {}
        for key in updated.keys():
            if key not in base:
                changed[key] = updated[key]
                continue
            child = dict_diff(base[key], updated[key])
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


def merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            base_list = merged[key]
            if all(isinstance(item, dict) for item in value) and all(
                isinstance(item, dict) for item in base_list[: len(value)]
            ):
                merged[key] = [
                    merge_dicts(base_item, update_item)
                    for base_item, update_item in zip(base_list, value)
                ] + base_list[len(value) :]
            else:
                merged[key] = value
        else:
            merged[key] = value
    return merged


def example_config(description: str) -> Dict[str, Any]:
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
    is_solid_like = any(token in desc for token in ("solid", "elastic", "beam", "continuum", "milling"))

    preferred = solid_fixture if is_solid_like else fluid_fixture
    fallback = fluid_fixture if preferred == solid_fixture else solid_fixture

    for fixture in (preferred, fallback):
        try:
            payload = json.loads(fixture.read_text())
            validated = SimulationConfig.model_validate(payload)
            return json.loads(validated.model_dump_json(exclude_none=True))
        except Exception:
            continue

    from sphinxsim.llm.mock_llm import MockLLM

    return json.loads(MockLLM().generate(description).model_dump_json(exclude_none=True))


def apply_explicit_instruction_overrides(cfg: Dict[str, Any], description: str) -> Dict[str, Any]:
    updated = json.loads(json.dumps(cfg))

    time_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b", description, re.IGNORECASE)
    if time_match:
        updated.setdefault("solver_parameters", {})["end_time"] = float(time_match.group(1))

    res_match = re.search(r"(\d+(?:\.\d+)?)\s*mm\s+resolution", description, re.IGNORECASE)
    if res_match:
        updated.setdefault("geometries", {}).setdefault("global_resolution", {})["particle_spacing"] = (
            float(res_match.group(1)) / 1000.0
        )

    return updated


def sanitize_config_dict(cfg: Dict[str, Any]) -> Dict[str, Any]:
    updated = json.loads(json.dumps(cfg))

    geometries = updated.get("geometries")
    if not isinstance(geometries, dict):
        geometries = {}
        updated["geometries"] = geometries

    for key in ("shapes", "oriented_boxes"):
        items = geometries.get(key, [])
        if not isinstance(items, list):
            geometries[key] = []
            continue
        geometries[key] = [item for item in items if isinstance(item, dict)]

    for key in (
        "fluid_bodies",
        "solid_bodies",
        "continuum_bodies",
        "observers",
        "fluid_boundary_conditions",
        "body_constraints",
        "extra_state_recording",
        "initial_conditions",
    ):
        items = updated.get(key, [])
        if not isinstance(items, list):
            updated[key] = []
            continue
        updated[key] = [item for item in items if isinstance(item, dict)]

    updated.pop("characteristic_dimensions", None)

    shapes = updated.get("geometries", {}).get("shapes", [])
    shape_names = {shape.get("name") for shape in shapes if isinstance(shape, dict) and shape.get("name")}

    def _normalize_wall_typo(name: str | None) -> str | None:
        if not name or not isinstance(name, str):
            return name
        if name.startswith("Wal") and not name.startswith("Wall"):
            return "Wall" + name[3:]
        return name

    def _canonical_shape_name(name: str | None) -> str | None:
        name = _normalize_wall_typo(name)
        if not name:
            return name
        if name in shape_names:
            return name
        candidates = get_close_matches(name, [n for n in shape_names if isinstance(n, str)], n=1, cutoff=0.6)
        return candidates[0] if candidates else name

    shape_rename_map: Dict[str, str] = {}
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        name = shape.get("name")
        corrected = _canonical_shape_name(name)
        if name and corrected and corrected != name:
            shape_rename_map[name] = corrected
            shape["name"] = corrected
            shape_names.discard(name)
            shape_names.add(corrected)

    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        original = shape.get("original")
        if isinstance(original, str):
            shape["original"] = _canonical_shape_name(shape_rename_map.get(original, original))
        sub_shapes = shape.get("sub_shapes")
        if isinstance(sub_shapes, list):
            shape["sub_shapes"] = [
                _canonical_shape_name(shape_rename_map.get(item, item) if isinstance(item, str) else item)
                if isinstance(item, str)
                else item
                for item in sub_shapes
            ]

    for section in ("fluid_bodies", "solid_bodies", "continuum_bodies"):
        for body in updated.get(section, []):
            if not isinstance(body, dict):
                continue
            name = body.get("name")
            normalized = _normalize_wall_typo(name)
            if name and normalized and normalized != name:
                body["name"] = normalized

    all_body_names = {
        body.get("name")
        for section in ("fluid_bodies", "solid_bodies", "continuum_bodies")
        for body in updated.get(section, [])
        if isinstance(body, dict) and body.get("name")
    }

    def _canonical_body_name(name: str | None) -> str | None:
        name = _normalize_wall_typo(name)
        if not name:
            return name
        if name in all_body_names:
            return name
        candidates = get_close_matches(name, [n for n in all_body_names if isinstance(n, str)], n=1, cutoff=0.6)
        return candidates[0] if candidates else name

    for entry in updated.get("particle_generation", {}).get("settings", {}).get("bodies", []):
        if isinstance(entry, dict):
            entry["name"] = _canonical_body_name(entry.get("name"))

    for entry in updated.get("observers", []):
        if isinstance(entry, dict):
            entry["observed_body"] = _canonical_body_name(entry.get("observed_body"))

    for entry in updated.get("fluid_boundary_conditions", []):
        if isinstance(entry, dict):
            entry["body_name"] = _canonical_body_name(entry.get("body_name"))

    for entry in updated.get("body_constraints", []):
        if isinstance(entry, dict):
            entry["body_name"] = _canonical_body_name(entry.get("body_name"))

    for entry in updated.get("extra_state_recording", []):
        if not isinstance(entry, dict):
            continue
        entry["name"] = _canonical_body_name(entry.get("name"))
        for variable in entry.get("variables", []):
            if not isinstance(variable, dict):
                continue
            if isinstance(variable.get("real_type"), str):
                variable["real_type"] = [variable["real_type"]]
            if isinstance(variable.get("vector_type"), str):
                variable["vector_type"] = [variable["vector_type"]]

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


def infer_requested_simulation_type(description: str) -> str | None:
    text = (description or "").lower()
    if not text:
        return None

    asks_for_type_change = bool(re.search(r"\b(simulation|simulaiton|type|switch|change|convert)\b", text))
    if not asks_for_type_change:
        return None

    if "continuum" in text:
        return "continuum_dynamics"
    if "fluid" in text:
        return "fluid_dynamics"
    return None


def coerce_simulation_type(config_dict: Dict[str, Any], target_type: str) -> Dict[str, Any]:
    updated = json.loads(json.dumps(config_dict))
    updated["simulation_type"] = target_type
    updated.setdefault("solver_parameters", {})

    if target_type == "continuum_dynamics":
        updated["solver_parameters"].setdefault("continuum_dynamics", {})
        if not updated.get("continuum_bodies"):
            shape_names = [
                shape["name"]
                for shape in updated.get("geometries", {}).get("shapes", [])
                if isinstance(shape, dict) and isinstance(shape.get("name"), str)
            ]
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
            shape_names = [
                shape["name"]
                for shape in updated.get("geometries", {}).get("shapes", [])
                if isinstance(shape, dict) and isinstance(shape.get("name"), str)
            ]
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


def infer_requested_shape_rename(description: str) -> tuple[str, str] | None:
    text = (description or "").strip()
    if not text:
        return None

    quoted_patterns = [
        r"(?:shape\s+name|shape|rename|change)\s+[\"']([^\"']+)[\"']\s+(?:to|as)\s+[\"']([^\"']+)[\"']",
        r"rename\s+[\"']([^\"']+)[\"']\s+to\s+[\"']([^\"']+)[\"']",
    ]
    for pattern in quoted_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            old_name = match.group(1).strip()
            new_name = match.group(2).strip()
            if old_name and new_name and old_name != new_name:
                return old_name, new_name

    token_patterns = [
        r"(?:shape\s+name|shape|rename)\s+['\"]?([A-Za-z_][\w]*)['\"]?\s+(?:to|as)\s+['\"]?([A-Za-z_][\w]*)['\"]?",
        r"change\s+['\"]?([A-Za-z_][\w]*)['\"]?\s+to\s+['\"]?([A-Za-z_][\w]*)['\"]?",
    ]
    lowered = text.lower()
    if "shape" not in lowered and "rename" not in lowered and "change" not in lowered:
        return None
    for pattern in token_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
            if old_name != new_name:
                return old_name, new_name
    return None


def apply_shape_rename(config_dict: Dict[str, Any], old_name: str, new_name: str) -> Dict[str, Any]:
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
