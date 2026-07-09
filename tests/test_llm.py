"""Tests for the MockLLM natural-language → config conversion."""

import pytest
from pydantic import ValidationError

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.llm.common import (
    apply_stl_geometry_overrides,
    example_config,
    infer_requested_material_type,
    infer_requested_simulation_type,
    sanitize_config_dict,
)
from sphinxsim.llm.mock_llm import MockLLM, PhysicsType, _detect_physics


# ---------------------------------------------------------------------------
# _detect_physics helper
# ---------------------------------------------------------------------------


class TestDetectPhysics:
    def test_fluid_keywords(self):
        assert _detect_physics("water flowing through a pipe") == PhysicsType.FLUID
        assert _detect_physics("channel flow simulation") == PhysicsType.FLUID
        assert _detect_physics("Navier-Stokes solver") == PhysicsType.FLUID

    def test_solid_keywords(self):
        assert _detect_physics("elastic beam under load") == PhysicsType.SOLID
        assert _detect_physics("deformation of a steel plate") == PhysicsType.SOLID

    def test_plastic_continuum_keywords(self):
        assert _detect_physics("granular soil column collapse") == PhysicsType.PLASTIC_CONTINUUM
        assert _detect_physics("landslide with plastic continuum material") == PhysicsType.PLASTIC_CONTINUUM

    def test_fsi_keywords(self):
        assert _detect_physics("fsi simulation of a flexible flap") == PhysicsType.FSI
        assert _detect_physics("fluid-structure interaction") == PhysicsType.FSI

    def test_both_fluid_and_solid_yields_fsi(self):
        assert _detect_physics("water flow over an elastic structure") == PhysicsType.FSI

    def test_unknown_defaults_to_fluid(self):
        assert _detect_physics("some random text") == PhysicsType.FLUID


# ---------------------------------------------------------------------------
# MockLLM.generate
# ---------------------------------------------------------------------------


class TestMockLLM:
    def setup_method(self):
        self.llm = MockLLM()

    def test_returns_simulation_config(self):
        cfg = self.llm.generate("simulate water flowing through a pipe")
        assert isinstance(cfg, SimulationConfig)

    def test_physics_fluid(self):
        cfg = self.llm.generate("water dam break simulation")
        assert cfg.fluid_bodies[0].name

    def test_physics_solid(self):
        cfg = self.llm.generate("elastic beam bending under load")
        assert cfg.simulation_type.value == "continuum_dynamics"

    def test_physics_plastic_continuum(self):
        cfg = self.llm.generate("2D column collapse of granular soil using plastic continuum")
        assert cfg.simulation_type.value == "continuum_dynamics"
        assert cfg.continuum_bodies[0].material.type.value == "plastic_continuum"
        assert cfg.continuum_bodies[0].material.friction_angle is not None

    def test_physics_fsi(self):
        cfg = self.llm.generate("hydroelastic fluid-structure interaction")
        assert cfg.solver_parameters.end_time is not None

    def test_name_extracted(self):
        cfg = self.llm.generate("water flowing through a pipe at 2 m/s")
        assert len(cfg.fluid_bodies[0].name) > 0

    def test_velocity_override(self):
        cfg = self.llm.generate("water flowing at 3 m/s through a channel")
        assert cfg.solver_parameters.fluid_dynamics is not None
        assert cfg.solver_parameters.fluid_dynamics.max_velocity_factor == pytest.approx(3.0)

    def test_end_time_override(self):
        cfg = self.llm.generate("simulate for 5 s")
        assert cfg.solver_parameters.end_time == pytest.approx(5.0)

    def test_domain_override(self):
        cfg = self.llm.generate("simulate water in a 2 m domain")
        assert cfg.geometries.system_domain is not None
        assert cfg.geometries.system_domain.upper_bound == [2.0, 2.0]

    def test_resolution_override(self):
        cfg = self.llm.generate("water flow with 5 mm resolution")
        assert cfg.geometries.global_resolution is not None
        assert cfg.geometries.global_resolution.particle_spacing == pytest.approx(0.005)

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="description must not be empty"):
            self.llm.generate("")

    def test_whitespace_description_raises(self):
        with pytest.raises(ValueError):
            self.llm.generate("   ")

    def test_result_is_valid_schema(self):
        """Generated config must always pass Pydantic validation."""
        descriptions = [
            "water through a pipe",
            "elastic plate vibration",
            "fsi simulation of a flag in the wind",
            "dam break",
            "tensile test of rubber in a 2 m domain",
            "water at 10 m/s for 2 s",
        ]
        for desc in descriptions:
            cfg = self.llm.generate(desc)
            # round-trip through JSON to confirm schema is fully satisfied
            restored = SimulationConfig.model_validate_json(cfg.model_dump_json())
            assert restored == cfg

    def test_update_changes_existing_end_time(self):
        base = self.llm.generate("water flow")
        updated = self.llm.update(base, "simulate for 3 s")
        assert updated.solver_parameters.end_time == pytest.approx(3.0)

    def test_update_changes_end_time_with_second_wording(self):
        base = self.llm.generate("water flow")
        updated = self.llm.update(base, "the end time is 3 second.")
        assert updated.solver_parameters.end_time == pytest.approx(3.0)

    def test_update_adds_observer(self):
        base = self.llm.generate("water flow")
        updated = self.llm.update(base, "add observer named outlet at (1.0, 0.5)")
        assert len(updated.observers) == len(base.observers) + 1
        assert updated.observers[-1].name == "outlet"


class TestExampleConfig:
    def test_3d_dam_break_uses_3d_fixture(self):
        example = example_config("3d dam break")

        assert len(example["geometries"]["system_domain"]["lower_bound"]) == 3
        assert all(shape["type"] != "multipolygon" for shape in example["geometries"]["shapes"])

    def test_3d_plastic_column_uses_repose_angle_fixture(self):
        example = example_config("3d column collapse using plastic material")

        assert example["simulation_type"] == "continuum_dynamics"
        assert len(example["geometries"]["system_domain"]["lower_bound"]) == 3
        assert example["continuum_bodies"][0]["material"]["type"] == "plastic_continuum"
        assert all(shape["type"] != "multipolygon" for shape in example["geometries"]["shapes"])


class TestSTLGeometryOverrides:
    def test_landslide_stl_files_replace_body_and_boundary_shapes(self):
        cfg = example_config("3d landslide case")
        updated = apply_stl_geometry_overrides(
            cfg,
            "Create a runnable 3D landslide simulation from two STL files: "
            "./input/SlideBody.stl is the moving landslide soil body, and "
            "./input/Channel.stl is the fixed terrain boundary.",
        )

        shapes = {shape["name"]: shape for shape in updated["geometries"]["shapes"]}
        assert shapes["GranularBody"]["type"] == "triangle_mesh"
        assert shapes["GranularBody"]["file_name"] == "./input/SlideBody.stl"
        assert shapes["GranularBody"]["translation"] == [0.0, 0.0, 0.0]
        assert shapes["GranularBody"]["scale"] == pytest.approx(1.0)
        assert shapes["WallBoundary"]["type"] == "triangle_mesh"
        assert shapes["WallBoundary"]["file_name"] == "./input/Channel.stl"
        assert "WallInnerBox" not in shapes
        assert "WallOuterBox" not in shapes

        restored = SimulationConfig.model_validate(updated)
        assert restored.continuum_bodies[0].name == "GranularBody"
        assert restored.solid_bodies[0].name == "WallBoundary"

    def test_sanitize_removes_shape_fields_that_do_not_match_type(self):
        cfg = example_config("3d landslide case")
        cfg["geometries"]["shapes"][0]["file_name"] = "./input/SlideBody.stl"
        cfg["geometries"]["shapes"][0]["scale"] = 1.0

        sanitized = sanitize_config_dict(cfg)

        granular = sanitized["geometries"]["shapes"][0]
        assert granular["type"] == "bounding_box"
        assert "file_name" not in granular
        assert "scale" not in granular

    def test_stl_file_name_does_not_drive_material_intent(self):
        description = "Create a 3D case from ./input/Landslide.stl and ./input/Channel.stl."

        assert infer_requested_simulation_type(description) is None
        assert infer_requested_material_type(description) is None

    def test_textual_landslide_typo_drives_material_intent(self):
        description = "Create a 3D landsldie case using ./input/SlideBody.stl as the moving body."

        assert infer_requested_simulation_type(description) == "continuum_dynamics"
        assert infer_requested_material_type(description) == "plastic_continuum"
