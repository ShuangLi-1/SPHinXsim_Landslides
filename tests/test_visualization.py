"""Tests for sphinxsim.visualization (annotations, preview, CLI preview command).

PyVista is *not* required for most tests — mesh-building helpers are tested via
a thin stub.  Tests that do require PyVista are skipped automatically when the
library is not installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typing import Any
import copy
from unittest.mock import MagicMock, patch

import pytest

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.cli import main

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent / "test_simulation" / "test_2d_simulation" / "data"
_HEAT_TRANSFER_JSON = _DATA_DIR / "heat_transfer.json"


def _minimal_fluid_config() -> dict:
    """Minimal valid fluid-dynamics config for 2-D tests."""
    return {
        "simulation_type": "fluid_dynamics",
        "geometries": {
            "system_domain": {"lower_bound": [0.0, 0.0], "upper_bound": [1.0, 1.0]},
            "global_resolution": {"particle_spacing": 0.05},
            "shapes": [
                {
                    "name": "WaterBody",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [0.4, 0.2],
                },
                {
                    "name": "WallBoundary",
                    "type": "bounding_box",
                    "lower_bound": [-0.05, -0.05],
                    "upper_bound": [1.05, 1.05],
                },
            ],
            "oriented_boxes": [
                {
                    "name": "Inlet",
                    "type": "in_outlet",
                    "center": [0.0, 0.1],
                    "normal": [1.0, 0.0],
                    "radius": 0.1,
                }
            ],
        },
        "particle_generation": {
            "build_and_run": True,
            "settings": {
                "bodies": [
                    {"name": "WaterBody"},
                    {"name": "WallBoundary", "solid_body": {}},
                ],
                "relaxation_parameters": {"total_iterations": 1},
            },
        },
        "fluid_bodies": [
            {
                "name": "WaterBody",
                "material": {
                    "type": "weakly_compressible_fluid",
                    "density": 1000.0,
                },
            }
        ],
        "solid_bodies": [{"name": "WallBoundary", "material": {"type": "rigid_body"}}],
        "gravity": [0.0, -9.81],
        "fluid_boundary_conditions": [
            {
                "body_name": "WaterBody",
                "oriented_box": "Inlet",
                "type": "emitter",
                "inflow_speed": 1.5,
            }
        ],
        "solver_parameters": {
            "end_time": 1.0,
            "fluid_dynamics": {
                "acoustic_cfl": 0.6,
                "advection_cfl": 0.25,
                "surface_type": "free_surface",
            },
        },
    }


@pytest.fixture
def fluid_config() -> SimulationConfig:
    return SimulationConfig(**_minimal_fluid_config())


@pytest.fixture
def heat_config() -> SimulationConfig:
    data = json.loads(_HEAT_TRANSFER_JSON.read_text())
    return SimulationConfig(**data)


# ---------------------------------------------------------------------------
# Annotations tests
# ---------------------------------------------------------------------------

class TestBodyLabel:
    def test_fluid_body_label_includes_density(self, fluid_config):
        from sphinxsim.visualization.annotations import body_label

        label = body_label("WaterBody", fluid_config)
        assert "Fluid: WaterBody" in label
        assert "1000.0" in label

    def test_fluid_body_label_omits_sound_speed(self, fluid_config):
        from sphinxsim.visualization.annotations import body_label

        label = body_label("WaterBody", fluid_config)
        assert "c=" not in label

    def test_solid_body_label(self, fluid_config):
        from sphinxsim.visualization.annotations import body_label

        label = body_label("WallBoundary", fluid_config)
        assert "Solid: WallBoundary" in label
        assert "rigid" in label

    def test_unknown_body_returns_name(self, fluid_config):
        from sphinxsim.visualization.annotations import body_label

        label = body_label("NonExistent", fluid_config)
        assert label == "NonExistent"

    def test_thermal_boundary_shown_in_fluid_label(self, heat_config):
        from sphinxsim.visualization.annotations import body_label

        # WaterBody in heat_transfer has thermal_properties
        label = body_label("WaterBody", heat_config)
        assert "Fluid: WaterBody" in label


class TestOrientedBoxLabel:
    def test_label_includes_name_and_type(self, fluid_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        ob = fluid_config.geometries.oriented_boxes[0]  # "Inlet"
        label = oriented_box_label(ob, fluid_config)
        assert "Inlet" in label
        assert "in_outlet" in label

    def test_label_includes_bc_type(self, fluid_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        ob = fluid_config.geometries.oriented_boxes[0]  # linked to emitter BC
        label = oriented_box_label(ob, fluid_config)
        assert "emitter" in label
        assert "WaterBody" in label

    def test_label_includes_inflow_speed(self, fluid_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        ob = fluid_config.geometries.oriented_boxes[0]
        label = oriented_box_label(ob, fluid_config)
        assert "1.5" in label

    def test_oriented_box_no_bc(self, heat_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        # UpperWall region has no BC in heat_transfer
        ob = next(o for o in heat_config.geometries.oriented_boxes if o.name == "UpperWall")
        label = oriented_box_label(ob, heat_config)
        assert "UpperWall" in label

    def test_bi_directional_bc_shows_pressure(self, heat_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        ob = next(o for o in heat_config.geometries.oriented_boxes if o.name == "Inlet")
        label = oriented_box_label(ob, heat_config)
        assert "bi_directional" in label

    def test_label_includes_relaxation_constraint_for_oriented_box(self, fluid_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        data = copy.deepcopy(fluid_config.model_dump(exclude_none=True))
        data["particle_generation"]["settings"]["relaxation_constraints"] = [
            {
                "body_name": "WaterBody",
                "oriented_box": "Inlet",
                "type": "fixed"
            }
        ]
        cfg = SimulationConfig(**data)

        ob = cfg.geometries.oriented_boxes[0]
        label = oriented_box_label(ob, cfg)
        assert "Relaxation constraint" in label
        assert "WaterBody" in label
        assert "fixed" in label

    def test_label_does_not_use_body_constraints_for_oriented_box(self, fluid_config):
        from sphinxsim.visualization.annotations import oriented_box_label

        data = copy.deepcopy(fluid_config.model_dump(exclude_none=True))
        data["body_constraints"] = [
            {
                "body_name": "WallBoundary",
                "type": "fixed",
                "region": "Inlet",
            }
        ]
        cfg = SimulationConfig(**data)

        ob = cfg.geometries.oriented_boxes[0]
        label = oriented_box_label(ob, cfg)
        assert "Constraint →" not in label


class TestGravityLabel:
    def test_2d_gravity_label(self, fluid_config):
        from sphinxsim.visualization.annotations import gravity_label

        label = gravity_label(fluid_config)
        assert label is not None
        assert "9.81" in label
        assert "g =" in label

    def test_no_gravity_returns_none(self, heat_config):
        from sphinxsim.visualization.annotations import gravity_label

        # heat_transfer.json has no gravity
        label = gravity_label(heat_config)
        assert label is None


class TestObserverLabel:
    def test_observer_label_includes_name_body_and_variable(self, fluid_config):
        from sphinxsim.visualization.annotations import observer_label

        data = copy.deepcopy(fluid_config.model_dump(exclude_none=True))
        data["observers"] = [
            {
                "name": "ProbeA",
                "observed_body": "WaterBody",
                "variable": {"real_type": "Pressure"},
                "positions": [[0.1, 0.1]],
            }
        ]
        cfg = SimulationConfig(**data)

        label = observer_label(cfg.observers[0])
        assert "Observer: ProbeA" in label
        assert "body=WaterBody" in label
        assert "var=Pressure" in label


# ---------------------------------------------------------------------------
# ConfigVisualizer.preview — no-pyvista guard test
# ---------------------------------------------------------------------------

class TestConfigVisualizerNoPyvista:
    def test_raises_import_error_without_pyvista(self, fluid_config, tmp_path):
        from sphinxsim.visualization.preview import ConfigVisualizer

        with patch.dict(sys.modules, {"pyvista": None}):
            viz = ConfigVisualizer(fluid_config, tmp_path, off_screen=True)
            with pytest.raises(ImportError, match="PyVista"):
                viz.preview()


class TestSpatialDimensionInference:
    def test_planar_simbody_constraint_is_inferred_as_2d(self, tmp_path):
        from sphinxsim.visualization.preview import ConfigVisualizer

        data = _minimal_fluid_config()
        data["geometries"].pop("system_domain", None)
        data.pop("gravity", None)
        data["body_constraints"] = [
            {
                "body_name": "WallBoundary",
                "type": "simbody",
                "mobilized_body": "planar",
                "velocity": [0.0, -0.03],
                "angular_velocity": 2.0,
            }
        ]
        data["solver_parameters"]["restart"] = {
            "restore_step": 0,
            "save_interval": 1000,
            "summary_enabled": True,
        }

        config = SimulationConfig(**data)
        viz = ConfigVisualizer(config, tmp_path, off_screen=True)

        assert viz._spatial_dim() == 2


class TestPreviewViewMode:
    def test_2d_default_view_uses_orthographic_xy(self, fluid_config, tmp_path):
        from sphinxsim.visualization.preview import ConfigVisualizer

        viz = ConfigVisualizer(fluid_config, tmp_path, off_screen=True)
        calls: list[str] = []

        class FakePlotter:
            def enable_2d_style(self):
                calls.append("enable_2d_style")

            def enable_parallel_projection(self):
                calls.append("enable_parallel_projection")

            def view_xy(self, negative=False):
                calls.append(f"view_xy:{negative}")

        viz._configure_default_view(FakePlotter(), ndim=2)

        assert "enable_2d_style" in calls
        assert "enable_parallel_projection" in calls
        assert "view_xy:False" in calls

    def test_2d_widgets_only_offer_z_views(self, fluid_config, tmp_path):
        from sphinxsim.visualization.preview import ConfigVisualizer

        viz = ConfigVisualizer(fluid_config, tmp_path, off_screen=True)

        class FakePlotter:
            window_size = (1200, 800)

            def __init__(self):
                self.titles: list[str] = []

            def add_text(self, *args, **kwargs):
                return None

            def add_radio_button_widget(self, callback, group, value, title, **kwargs):
                self.titles.append(title)
                return None

        fake_plotter = FakePlotter()
        viz._add_view_direction_widgets(fake_plotter, ndim=2)

        assert fake_plotter.titles == ["+z", "-z"]


class TestPreviewObservers:
    def test_populate_plotter_renders_observer_points(self, fluid_config, tmp_path):
        from sphinxsim.visualization.preview import ConfigVisualizer

        data = copy.deepcopy(fluid_config.model_dump(exclude_none=True))
        data["geometries"].pop("system_domain", None)
        data["observers"] = [
            {
                "name": "ProbeA",
                "observed_body": "WaterBody",
                "variable": {"real_type": "Pressure"},
                "positions": [[0.1, 0.1], [0.2, 0.1]],
            }
        ]
        cfg = SimulationConfig(**data)
        viz = ConfigVisualizer(cfg, tmp_path, off_screen=True)

        class FakePlotter:
            def __init__(self):
                self.mesh_calls: list[dict[str, Any]] = []
                self.point_label_calls: list[dict[str, Any]] = []

            def add_mesh(self, mesh, **kwargs):
                self.mesh_calls.append({"mesh": mesh, **kwargs})

            def add_point_labels(self, points, labels, **kwargs):
                self.point_label_calls.append(
                    {"points": points, "labels": labels, **kwargs}
                )

            def add_text(self, *args, **kwargs):
                return None

            def add_legend(self, *args, **kwargs):
                return None

        class FakePyVista:
            @staticmethod
            def PolyData(points):
                return {"points": points}

        fake_plotter = FakePlotter()
        with patch.dict(sys.modules, {"pyvista": FakePyVista}):
            viz._populate_plotter(fake_plotter, vtp_dir=None)

        observer_mesh_calls = [
            call for call in fake_plotter.mesh_calls if call.get("label") == "Observer: ProbeA"
        ]
        assert len(observer_mesh_calls) == 1
        assert observer_mesh_calls[0]["color"] == (0.93, 0.13, 0.93)
        assert observer_mesh_calls[0]["point_size"] == 10

        observer_label_calls = [
            call
            for call in fake_plotter.point_label_calls
            if call["labels"] and "Observer: ProbeA" in call["labels"][0]
        ]
        assert len(observer_label_calls) == 1


# ---------------------------------------------------------------------------
# CLI preview command tests (no PyVista / no C++ required)
# ---------------------------------------------------------------------------

class TestCLIPreviewCommand:
    def _write_config(self, path: Path) -> Path:
        p = path / "config.json"
        p.write_text(json.dumps(_minimal_fluid_config()))
        return p

    def test_preview_missing_pyvista_returns_nonzero(self, build_temp_path, capsys):
        cfg = self._write_config(build_temp_path)
        with patch.dict(sys.modules, {"pyvista": None}):
            rc = main(["preview", str(cfg)])
        assert rc != 0
        err = capsys.readouterr().err
        assert "PyVista" in err or "pyvista" in err.lower()

    def test_preview_missing_config_returns_nonzero(self, build_temp_path, capsys):
        with patch.dict(sys.modules, {"pyvista": MagicMock()}):
            rc = main(["preview", str(build_temp_path / "nonexistent.json")])
        assert rc != 0

    def test_preview_calls_visualizer_preview(self, build_temp_path):
        cfg = self._write_config(build_temp_path)
        mock_pv = MagicMock()
        fake_visualizer = MagicMock()

        with patch.dict(sys.modules, {"pyvista": mock_pv}):
            with patch(
                "sphinxsim.visualization.preview.ConfigVisualizer",
                return_value=fake_visualizer,
            ) as MockViz:
                rc = main(["preview", str(cfg)])

        assert rc == 0
        MockViz.assert_called_once()
        fake_visualizer.preview.assert_called_once_with(use_cpp=True)

    def test_preview_no_cpp_flag(self, build_temp_path):
        cfg = self._write_config(build_temp_path)
        mock_pv = MagicMock()
        fake_visualizer = MagicMock()

        with patch.dict(sys.modules, {"pyvista": mock_pv}):
            with patch(
                "sphinxsim.visualization.preview.ConfigVisualizer",
                return_value=fake_visualizer,
            ):
                rc = main(["preview", str(cfg), "--no-cpp"])

        assert rc == 0
        fake_visualizer.preview.assert_called_once_with(use_cpp=False)

    def test_preview_invalid_config_returns_nonzero(self, build_temp_path, capsys):
        bad = _minimal_fluid_config()
        bad["fluid_bodies"] = []  # invalid — no fluid bodies
        p = build_temp_path / "bad.json"
        p.write_text(json.dumps(bad))
        mock_pv = MagicMock()
        with patch.dict(sys.modules, {"pyvista": mock_pv}):
            rc = main(["preview", str(p)])
        assert rc != 0

    def test_preview_visualizer_exception_returns_nonzero(self, build_temp_path, capsys):
        cfg = self._write_config(build_temp_path)
        mock_pv = MagicMock()
        fake_visualizer = MagicMock()
        fake_visualizer.preview.side_effect = RuntimeError("render failed")

        with patch.dict(sys.modules, {"pyvista": mock_pv}):
            with patch(
                "sphinxsim.visualization.preview.ConfigVisualizer",
                return_value=fake_visualizer,
            ):
                rc = main(["preview", str(cfg)])

        assert rc != 0
        assert "render failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Shell mode preview tests
# ---------------------------------------------------------------------------

class TestShellPreview:
    def _write_config(self, path: Path) -> tuple[Path, str]:
        """Write config and return (abs_path, shell-relative path)."""
        p = path / "config.json"
        p.write_text(json.dumps(_minimal_fluid_config()))
        rel = f"pytest-temp/{path.name}/config.json"
        return p, rel

    def test_shell_preview_no_pyvista_prints_error(self, build_temp_path, capsys):
        _, rel = self._write_config(build_temp_path)
        inputs = [f"load {rel}", "preview", "exit"]
        with patch.dict(sys.modules, {"pyvista": None}):
            with patch("builtins.input", side_effect=inputs):
                rc = main(["shell"])
        assert rc == 0  # shell itself exits cleanly
        err = capsys.readouterr().err
        assert "PyVista" in err or "pyvista" in err.lower()

    def test_shell_preview_before_load_errors(self, build_temp_path, capsys):
        inputs = ["preview", "exit"]
        with patch("builtins.input", side_effect=inputs):
            rc = main(["shell"])
        assert rc == 0
        assert "No config loaded" in capsys.readouterr().err

    def test_shell_preview_calls_visualizer(self, build_temp_path, capsys):
        _, rel = self._write_config(build_temp_path)
        fake_visualizer = MagicMock()

        inputs = [f"load {rel}", "preview", "exit"]
        with patch.dict(sys.modules, {"pyvista": MagicMock()}):
            with patch(
                "sphinxsim.visualization.preview.ConfigVisualizer",
                return_value=fake_visualizer,
            ) as MockViz:
                with patch("builtins.input", side_effect=inputs):
                    rc = main(["shell"])

        assert rc == 0
        MockViz.assert_called_once()
        fake_visualizer.preview.assert_called_once_with(use_cpp=True)

    def test_shell_preview_no_cpp_flag(self, build_temp_path):
        _, rel = self._write_config(build_temp_path)
        fake_visualizer = MagicMock()

        inputs = [f"load {rel}", "preview --no-cpp", "exit"]
        with patch.dict(sys.modules, {"pyvista": MagicMock()}):
            with patch(
                "sphinxsim.visualization.preview.ConfigVisualizer",
                return_value=fake_visualizer,
            ):
                with patch("builtins.input", side_effect=inputs):
                    rc = main(["shell"])

        assert rc == 0
        fake_visualizer.preview.assert_called_once_with(use_cpp=False)

    def test_shell_help_mentions_preview(self, build_temp_path, capsys):
        inputs = ["help", "exit"]
        with patch("builtins.input", side_effect=inputs):
            rc = main(["shell"])
        assert rc == 0
        assert "preview" in capsys.readouterr().out
