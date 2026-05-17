"""Tests for operation-based update patch executor."""

from __future__ import annotations

from sphinxsim.config.update_patch import UpdatePatch, apply_update_patch


def _base_config() -> dict:
    return {
        "solver_parameters": {"end_time": 1.0},
        "geometries": {"global_resolution": {"particle_spacing": 0.01}},
        "observers": [
            {
                "name": "ObserverA",
                "observed_body": "WaterBody",
                "positions": [[0.5, 0.2]],
            }
        ],
    }


def test_apply_set_value_changes_scalar() -> None:
    patch = UpdatePatch(
        operations=[
            {"op": "set_value", "path": "solver_parameters.end_time", "value": 2.5},
        ]
    )
    result = apply_update_patch(_base_config(), patch)
    assert result.applied is True
    assert result.changed is True
    assert result.updated["solver_parameters"]["end_time"] == 2.5


def test_apply_append_item_grows_array() -> None:
    patch = UpdatePatch(
        operations=[
            {
                "op": "append_item",
                "path": "observers",
                "value": {
                    "name": "ObserverB",
                    "observed_body": "WaterBody",
                    "positions": [[0.8, 0.3]],
                },
            }
        ]
    )
    result = apply_update_patch(_base_config(), patch)
    assert result.applied is True
    assert len(result.updated["observers"]) == 2
    assert result.updated["observers"][-1]["name"] == "ObserverB"


def test_apply_upsert_item_updates_match() -> None:
    patch = UpdatePatch(
        operations=[
            {
                "op": "upsert_item",
                "path": "observers",
                "match": {"name": "ObserverA"},
                "value": {"positions": [[1.0, 0.4]]},
                "on_match": "merge_object",
                "on_missing": "append_item",
            }
        ]
    )
    result = apply_update_patch(_base_config(), patch)
    assert result.applied is True
    assert result.updated["observers"][0]["positions"] == [[1.0, 0.4]]


def test_apply_rename_item_key() -> None:
    patch = UpdatePatch(
        operations=[
            {
                "op": "rename_item_key",
                "path": "observers",
                "match": {"name": "ObserverA"},
                "key": "name",
                "new_value": "OutletObserver",
            }
        ]
    )
    result = apply_update_patch(_base_config(), patch)
    assert result.applied is True
    assert result.updated["observers"][0]["name"] == "OutletObserver"


def test_strict_mode_fails_on_invalid_append_target() -> None:
    patch = UpdatePatch(
        strict=True,
        operations=[
            {
                "op": "append_item",
                "path": "solver_parameters.end_time",
                "value": 5,
            }
        ],
    )
    result = apply_update_patch(_base_config(), patch)
    assert result.applied is False
    assert result.errors
