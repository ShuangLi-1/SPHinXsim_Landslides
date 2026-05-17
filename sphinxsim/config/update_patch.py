"""Patch schema and executor for config updates.

This module defines a constrained, operation-based patch format for
updating SimulationConfig JSON payloads in a deterministic way.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class PatchPrecondition(BaseModel):
    type: Literal["path_exists", "path_absent", "array_unique_key", "type_is"]
    path: Optional[str] = None
    key: Optional[str] = None
    expected_type: Optional[Literal["object", "array", "string", "number", "boolean", "null"]] = None


class SetValueOperation(BaseModel):
    op: Literal["set_value"]
    path: str
    value: Any
    preconditions: List[PatchPrecondition] = Field(default_factory=list)


class MergeObjectOperation(BaseModel):
    op: Literal["merge_object"]
    path: str
    value: Dict[str, Any]
    preconditions: List[PatchPrecondition] = Field(default_factory=list)


class AppendItemOperation(BaseModel):
    op: Literal["append_item"]
    path: str
    value: Any
    preconditions: List[PatchPrecondition] = Field(default_factory=list)


class UpsertItemOperation(BaseModel):
    op: Literal["upsert_item"]
    path: str
    match: Dict[str, Any]
    value: Dict[str, Any]
    on_match: Literal["merge_object", "set_value"] = "merge_object"
    on_missing: Literal["append_item", "error"] = "append_item"
    preconditions: List[PatchPrecondition] = Field(default_factory=list)


class RenameItemKeyOperation(BaseModel):
    op: Literal["rename_item_key"]
    path: str
    match: Dict[str, Any]
    key: str
    new_value: Any
    preconditions: List[PatchPrecondition] = Field(default_factory=list)


PatchOperation = Union[
    SetValueOperation,
    MergeObjectOperation,
    AppendItemOperation,
    UpsertItemOperation,
    RenameItemKeyOperation,
]


class UpdatePatch(BaseModel):
    schema_version: str = "1.0"
    intent: str = "update simulation config from natural language"
    idempotency_key: Optional[str] = None
    strict: bool = True
    operations: List[PatchOperation] = Field(default_factory=list)


class PatchApplyResult(BaseModel):
    applied: bool
    changed: bool
    summary: Dict[str, int]
    warnings: List[str]
    errors: List[str]
    diff_stats: Dict[str, int]
    updated: Dict[str, Any]


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _split_path(path: str) -> List[str]:
    if path in {"", "."}:
        return []
    return [segment for segment in path.split(".") if segment]


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _resolve_path(root: Dict[str, Any], path: str) -> tuple[bool, Any]:
    parts = _split_path(path)
    current: Any = root
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set_path(root: Dict[str, Any], path: str, value: Any) -> None:
    parts = _split_path(path)
    if not parts:
        if isinstance(value, dict):
            root.clear()
            root.update(deepcopy(value))
            return
        raise ValueError("Root assignment requires an object value")

    current: Dict[str, Any] = root
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValueError(f"Cannot traverse non-object path segment: {part}")
        current = child
    current[parts[-1]] = deepcopy(value)


def _find_array_match(items: List[Any], matcher: Dict[str, Any]) -> tuple[int, Optional[Dict[str, Any]]]:
    matches: List[tuple[int, Dict[str, Any]]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if all(item.get(key) == value for key, value in matcher.items()):
            matches.append((idx, item))

    if len(matches) == 1:
        return matches[0][0], matches[0][1]
    if not matches:
        return -1, None
    return -2, None  # ambiguous sentinel


def _check_preconditions(root: Dict[str, Any], preconditions: List[PatchPrecondition], strict: bool) -> tuple[bool, List[str]]:
    errors: List[str] = []
    for condition in preconditions:
        if condition.type == "path_exists":
            exists, _ = _resolve_path(root, condition.path or "")
            if not exists:
                errors.append(f"Precondition failed: path does not exist: {condition.path}")

        elif condition.type == "path_absent":
            exists, _ = _resolve_path(root, condition.path or "")
            if exists:
                errors.append(f"Precondition failed: path exists: {condition.path}")

        elif condition.type == "array_unique_key":
            exists, target = _resolve_path(root, condition.path or "")
            if not exists or not isinstance(target, list):
                errors.append(f"Precondition failed: array path invalid: {condition.path}")
            elif condition.key:
                seen = set()
                for item in target:
                    if isinstance(item, dict) and condition.key in item:
                        value = item[condition.key]
                        if value in seen:
                            errors.append(
                                f"Precondition failed: duplicate value for {condition.key} in {condition.path}: {value}"
                            )
                            break
                        seen.add(value)

        elif condition.type == "type_is":
            exists, target = _resolve_path(root, condition.path or "")
            if not exists:
                errors.append(f"Precondition failed: path does not exist: {condition.path}")
            elif condition.expected_type and _type_name(target) != condition.expected_type:
                errors.append(
                    f"Precondition failed: type mismatch at {condition.path}: "
                    f"expected {condition.expected_type}, got {_type_name(target)}"
                )

    if errors and strict:
        return False, errors
    return True, errors


def _operation_name(operation: PatchOperation) -> str:
    return operation.op


def _nested_diff_stats(before: Any, after: Any) -> Dict[str, int]:
    stats = {"fields_changed": 0, "items_added": 0, "items_updated": 0}

    if isinstance(before, dict) and isinstance(after, dict):
        keys = set(before.keys()) | set(after.keys())
        for key in keys:
            if key not in before:
                stats["fields_changed"] += 1
            elif key not in after:
                stats["fields_changed"] += 1
            else:
                child = _nested_diff_stats(before[key], after[key])
                for name, value in child.items():
                    stats[name] += value
        return stats

    if isinstance(before, list) and isinstance(after, list):
        if len(after) > len(before):
            stats["items_added"] += len(after) - len(before)
        if before != after:
            stats["items_updated"] += 1
            stats["fields_changed"] += 1
        return stats

    if before != after:
        stats["fields_changed"] += 1
    return stats


def apply_update_patch(existing: Dict[str, Any], patch: Union[UpdatePatch, Dict[str, Any]], *, strict: Optional[bool] = None) -> PatchApplyResult:
    parsed_patch = patch if isinstance(patch, UpdatePatch) else UpdatePatch.model_validate(patch)
    effective_strict = parsed_patch.strict if strict is None else strict

    updated = deepcopy(existing)
    warnings: List[str] = []
    errors: List[str] = []
    summary: Dict[str, int] = {
        "set_value": 0,
        "merge_object": 0,
        "append_item": 0,
        "upsert_item": 0,
        "rename_item_key": 0,
    }

    for operation in parsed_patch.operations:
        ok, precondition_errors = _check_preconditions(updated, operation.preconditions, effective_strict)
        if precondition_errors:
            if effective_strict:
                errors.extend(precondition_errors)
                break
            warnings.extend(precondition_errors)
        if not ok:
            continue

        try:
            if operation.op == "set_value":
                _set_path(updated, operation.path, operation.value)

            elif operation.op == "merge_object":
                exists, target = _resolve_path(updated, operation.path)
                if not exists:
                    if effective_strict:
                        raise ValueError(f"Path does not exist for merge_object: {operation.path}")
                    _set_path(updated, operation.path, operation.value)
                elif operation.path in {"", "."}:
                    merged = _deep_merge(updated, operation.value)
                    updated.clear()
                    updated.update(merged)
                elif not isinstance(target, dict):
                    raise ValueError(f"merge_object requires object target at path: {operation.path}")
                else:
                    merged = _deep_merge(target, operation.value)
                    _set_path(updated, operation.path, merged)

            elif operation.op == "append_item":
                exists, target = _resolve_path(updated, operation.path)
                if not exists:
                    if effective_strict:
                        raise ValueError(f"Array path does not exist for append_item: {operation.path}")
                    _set_path(updated, operation.path, [operation.value])
                elif not isinstance(target, list):
                    raise ValueError(f"append_item requires array target at path: {operation.path}")
                else:
                    target.append(deepcopy(operation.value))

            elif operation.op == "upsert_item":
                exists, target = _resolve_path(updated, operation.path)
                if not exists:
                    if effective_strict:
                        raise ValueError(f"Array path does not exist for upsert_item: {operation.path}")
                    _set_path(updated, operation.path, [operation.value])
                elif not isinstance(target, list):
                    raise ValueError(f"upsert_item requires array target at path: {operation.path}")
                else:
                    idx, matched = _find_array_match(target, operation.match)
                    if idx == -2:
                        raise ValueError(f"Ambiguous upsert_item match at path: {operation.path}")
                    if idx == -1:
                        if operation.on_missing == "error":
                            raise ValueError(f"No upsert_item match at path: {operation.path}")
                        target.append(deepcopy(operation.value))
                    elif operation.on_match == "set_value":
                        target[idx] = deepcopy(operation.value)
                    else:
                        assert matched is not None
                        target[idx] = _deep_merge(matched, operation.value)

            elif operation.op == "rename_item_key":
                exists, target = _resolve_path(updated, operation.path)
                if not exists or not isinstance(target, list):
                    raise ValueError(f"rename_item_key requires array target at path: {operation.path}")
                idx, matched = _find_array_match(target, operation.match)
                if idx == -2:
                    raise ValueError(f"Ambiguous rename_item_key match at path: {operation.path}")
                if idx == -1 or matched is None:
                    raise ValueError(f"No rename_item_key match at path: {operation.path}")
                updated_item = deepcopy(matched)
                updated_item[operation.key] = deepcopy(operation.new_value)
                target[idx] = updated_item

            summary[_operation_name(operation)] += 1

        except Exception as exc:
            message = f"Operation {operation.op} failed: {exc}"
            if effective_strict:
                errors.append(message)
                break
            warnings.append(message)

    changed = updated != existing
    applied = not errors
    diff_stats = _nested_diff_stats(existing, updated)

    return PatchApplyResult(
        applied=applied,
        changed=changed,
        summary=summary,
        warnings=warnings,
        errors=errors,
        diff_stats=diff_stats,
        updated=updated,
    )
