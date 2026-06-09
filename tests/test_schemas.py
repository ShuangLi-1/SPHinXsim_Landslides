"""Tests for sphinxsim.config.schemas (Pydantic validation)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sphinxsim.config.schemas import DomainConfig, SimulationConfig


def _make_minimal_fluid_config(**overrides) -> SimulationConfig:
    data = {
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
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [1.0, 1.0],
                },
            ],
            "oriented_boxes": [
                {
                    "name": "Inlet",
                    "type": "region",
                    "half_size": [0.1, 0.05],
                    "transform": {"translation": [0.05, 0.2], "rotation_angle": 0.0},
                }
            ],
        },
        "particle_generation": {
            "build_and_run": False,
            "settings": {
                "bodies": [
                    {"name": "WaterBody"},
                    {"name": "WallBoundary", "solid_body": {}},
                ],
                "relaxation_parameters": {"total_iterations": 1000},
            },
        },
        "fluid_bodies": [
            {
                "name": "WaterBody",
                "material": {
                    "type": "weakly_compressible_fluid",
                    "density": 1000.0,
                },
                "particle_reserve_factor": 10.0,
            }
        ],
        "solid_bodies": [{"name": "WallBoundary", "material": {"type": "rigid_body"}}],
        "gravity": [0.0, -1.0],
        "observers": [
            {
                "name": "Obs",
                "observed_body": "WaterBody",
                "variable": {"real_type": "Pressure"},
                "positions": [[0.5, 0.2]],
            }
        ],
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
            "output_interval": 0.01,
            "screen_interval": 100,
            "fluid_dynamics": {
                "acoustic_cfl": 0.6,
                "advection_cfl": 0.25,
                "surface_type": "free_surface",
                "particle_sort_frequency": 100,
            },
        },
    }
    data.update(overrides)
    return SimulationConfig(**data)


def _make_minimal_continuum_config(**overrides) -> SimulationConfig:
    data = {
        "simulation_type": "continuum_dynamics",
        "geometries": {
            "system_domain": {"lower_bound": [0.0, 0.0], "upper_bound": [1.0, 1.0]},
            "global_resolution": {"particle_spacing": 0.05},
            "shapes": [
                {
                    "name": "ContinuumBody",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [0.4, 0.2],
                },
                {
                    "name": "WallBoundary",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [1.0, 1.0],
                },
            ],
        },
        "particle_generation": {
            "build_and_run": False,
            "settings": {
                "bodies": [
                    {"name": "ContinuumBody"},
                    {"name": "WallBoundary", "solid_body": {}},
                ],
                "relaxation_parameters": {"total_iterations": 1000},
            },
        },
        "continuum_bodies": [
            {
                "name": "ContinuumBody",
                "material": {
                    "type": "general_continuum",
                    "density": 1000.0,
                    "sound_speed": 20.0,
                    "youngs_modulus": 1.0e6,
                    "poisson_ratio": 0.3,
                },
            }
        ],
        "solid_bodies": [{"name": "WallBoundary", "material": {"type": "rigid_body"}}],
        "solver_parameters": {
            "end_time": 1.0,
            "output_interval": 0.01,
            "continuum_dynamics": {
                "acoustic_cfl": 0.4,
                "advection_cfl": 0.2,
            },
        },
    }
    data.update(overrides)
    return SimulationConfig(**data)


class TestDomainConfig:
    def test_valid(self):
        d = DomainConfig(lower_bound=[0.0, 0.0], upper_bound=[1.0, 2.0])
        assert d.upper_bound[1] == 2.0

    def test_non_increasing_bounds_rejected(self):
        with pytest.raises(ValidationError):
            DomainConfig(lower_bound=[0.0, 0.0], upper_bound=[1.0, 0.0])


class TestSimulationConfig:

    def test_minimal_fluid_config(self):
        cfg = _make_minimal_fluid_config()
        assert cfg.simulation_type.value == "fluid_dynamics"
        assert len(cfg.fluid_bodies) == 1
        assert cfg.solver_parameters.fluid_dynamics is not None
        assert cfg.solver_parameters.fluid_dynamics.surface_type == "free_surface"

    def test_fluid_solver_accepts_surface_type(self):
        cfg = _make_minimal_fluid_config(
            solver_parameters={
                "end_time": 1.0,
                "output_interval": 0.01,
                "screen_interval": 100,
                "fluid_dynamics": {
                    "acoustic_cfl": 0.6,
                    "advection_cfl": 0.25,
                    "surface_type": "open_boundary",
                    "particle_sort_frequency": 100,
                },
            }
        )
        assert cfg.solver_parameters.fluid_dynamics is not None
        assert cfg.solver_parameters.fluid_dynamics.surface_type == "open_boundary"

    def test_fluid_solver_rejects_unknown_key(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _make_minimal_fluid_config(
                solver_parameters={
                    "end_time": 1.0,
                    "output_interval": 0.01,
                    "screen_interval": 100,
                    "fluid_dynamics": {
                        "acoustic_cfl": 0.6,
                        "advection_cfl": 0.25,
                        "surface_type": "free_surface",
                        "unsupported_key": "x",
                    },
                }
            )

    def test_missing_fluid_solver_section_rejected(self):
        with pytest.raises(ValidationError, match="solver_parameters.fluid_dynamics"):
            _make_minimal_fluid_config(solver_parameters={"end_time": 1.0})

    def test_missing_fluid_bodies_rejected(self):
        with pytest.raises(ValidationError, match="requires fluid_bodies"):
            _make_minimal_fluid_config(fluid_bodies=[])

    def test_body_must_reference_shape_name(self):
        bad = {
            "fluid_bodies": [
                {
                    "name": "UnknownBody",
                    "material": {
                        "type": "weakly_compressible_fluid",
                        "density": 1000.0,
                    },
                }
            ]
        }
        with pytest.raises(ValidationError, match="must match a shape name"):
            _make_minimal_fluid_config(**bad)

    def test_shape_reference_to_previous_shape_is_allowed(self):
        geometries = {
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
                    "name": "ExpandedWaterBody",
                    "type": "expanded_box",
                    "original": "WaterBody",
                    "expansion": 0.01,
                },
                {
                    "name": "WallBoundary",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [1.0, 1.0],
                },
            ],
            "oriented_boxes": [
                {
                    "name": "Inlet",
                    "type": "region",
                    "half_size": [0.1, 0.05],
                    "transform": {"translation": [0.05, 0.2], "rotation_angle": 0.0},
                }
            ],
        }
        cfg = _make_minimal_fluid_config(geometries=geometries)
        assert any(shape.name == "ExpandedWaterBody" for shape in cfg.geometries.shapes)

    def test_shape_duplicate_name_rejected(self):
        geometries = {
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
                    "name": "WaterBody",
                    "type": "expanded_box",
                    "original": "WaterBody",
                    "expansion": 0.01,
                },
                {
                    "name": "WallBoundary",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [1.0, 1.0],
                },
            ],
            "oriented_boxes": [
                {
                    "name": "Inlet",
                    "type": "region",
                    "half_size": [0.1, 0.05],
                    "transform": {"translation": [0.05, 0.2], "rotation_angle": 0.0},
                }
            ],
        }
        with pytest.raises(ValidationError, match="duplicate shape name"):
            _make_minimal_fluid_config(geometries=geometries)

    def test_shape_reference_must_be_previously_defined(self):
        geometries = {
            "system_domain": {"lower_bound": [0.0, 0.0], "upper_bound": [1.0, 1.0]},
            "global_resolution": {"particle_spacing": 0.05},
            "shapes": [
                {
                    "name": "ExpandedWaterBody",
                    "type": "expanded_box",
                    "original": "WaterBody",
                    "expansion": 0.01,
                },
                {
                    "name": "WaterBody",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [0.4, 0.2],
                },
                {
                    "name": "WallBoundary",
                    "type": "bounding_box",
                    "lower_bound": [0.0, 0.0],
                    "upper_bound": [1.0, 1.0],
                },
            ],
            "oriented_boxes": [
                {
                    "name": "Inlet",
                    "type": "region",
                    "half_size": [0.1, 0.05],
                    "transform": {"translation": [0.05, 0.2], "rotation_angle": 0.0},
                }
            ],
        }
        with pytest.raises(ValidationError, match="previously defined"):
            _make_minimal_fluid_config(geometries=geometries)

    def test_observer_observed_body_must_exist(self):
        with pytest.raises(ValidationError, match="observer observed_body"):
            _make_minimal_fluid_config(
                observers=[
                    {
                        "name": "Obs",
                        "observed_body": "MissingBody",
                        "variable": {"real_type": "Pressure"},
                        "positions": [[0.1, 0.2]],
                    }
                ]
            )

    def test_boundary_condition_requires_existing_oriented_box(self):
        with pytest.raises(ValidationError, match="oriented_box"):
            _make_minimal_fluid_config(
                fluid_boundary_conditions=[
                    {
                        "body_name": "WaterBody",
                        "oriented_box": "MissingBox",
                        "type": "emitter",
                        "inflow_speed": 1.0,
                    }
                ]
            )

    def test_global_resolution_is_required(self):
        data = _make_minimal_fluid_config().model_dump(mode="json")
        del data["geometries"]["global_resolution"]

        with pytest.raises(ValidationError, match="global_resolution"):
            SimulationConfig.model_validate(data)

    def test_body_constraint_region_requires_existing_oriented_box(self):
        cfg = _make_minimal_fluid_config(
            body_constraints=[
                {
                    "body_name": "WallBoundary",
                    "type": "fixed",
                    "region": "Inlet",
                }
            ]
        )
        assert cfg.body_constraints[0].region == "Inlet"

        with pytest.raises(ValidationError, match="existing oriented box"):
            _make_minimal_fluid_config(
                body_constraints=[
                    {
                        "body_name": "WallBoundary",
                        "type": "fixed",
                        "region": "WallBoundary",
                    }
                ]
            )

    def test_extra_state_recording_accepts_int_type(self):
        cfg = _make_minimal_fluid_config(
            extra_state_recording=[
                {
                    "name": "WaterBody",
                    "variables": [{"int_type": ["BufferIndicator", "Indicator"]}],
                }
            ]
        )
        assert cfg.extra_state_recording[0].variables[0].int_type == ["BufferIndicator", "Indicator"]

    def test_extra_state_recording_rejects_unknown_variable_type_key(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _make_minimal_fluid_config(
                extra_state_recording=[
                    {
                        "name": "WaterBody",
                        "variables": [{"bool_type": ["Flag"]}],
                    }
                ]
            )

    def test_dimensionality_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="dimensionality"):
            _make_minimal_fluid_config(
                observers=[
                    {
                        "name": "Obs",
                        "observed_body": "WaterBody",
                        "variable": {"real_type": "Pressure"},
                        "positions": [[0.1, 0.2, 0.3]],
                    }
                ]
            )

    def test_roundtrip_json(self):
        cfg = _make_minimal_fluid_config()
        restored = SimulationConfig.model_validate_json(cfg.model_dump_json())
        assert restored == cfg

    def test_full_updated_fixture_validates(self):
        fixture_path = Path(__file__).parent / "examples" / "full_updated_simulation_config.json"
        payload = json.loads(fixture_path.read_text())
        cfg = SimulationConfig.model_validate(payload)

        assert cfg.simulation_type.value == "fluid_dynamics"
        assert cfg.solver_parameters.fluid_dynamics is not None
        assert cfg.fluid_bodies[0].particle_reserve_factor == pytest.approx(350.0)
        assert cfg.fluid_boundary_conditions[0].type.value == "emitter"

    def test_heat_transfer_fixture_accepts_thermal_properties(self):
        fixture_path = (
            Path(__file__).parent
            / "test_simulation"
            / "test_2d_simulation"
            / "data"
            / "heat_transfer.json"
        )
        payload = json.loads(fixture_path.read_text())
        cfg = SimulationConfig.model_validate(payload)

        thermal = cfg.fluid_bodies[0].material.thermal_properties
        assert thermal is not None
        expected_conductivity = payload["fluid_bodies"][0]["material"]["thermal_properties"][
            "thermal_conductivity"
        ]
        expected_heat_capacity = payload["fluid_bodies"][0]["material"]["thermal_properties"][
            "volumetric_heat_capacity"
        ]
        assert thermal.thermal_conductivity == pytest.approx(expected_conductivity)
        assert thermal.thermal_conductivity > 0.0
        assert thermal.volumetric_heat_capacity == pytest.approx(expected_heat_capacity)
        assert thermal.volumetric_heat_capacity > 0.0
        assert cfg.solid_bodies[0].material.thermal_properties is not None
        assert cfg.solid_bodies[0].material.thermal_properties.thermal_boundary.value == "Dirichlet"
        assert len(cfg.initial_conditions) == 2
        assert cfg.initial_conditions[0].body_name == "WallBoundary"
        assert cfg.initial_conditions[0].assignments[0].variable.real_type == "Temperature"

    def test_t_junction_fixture_accepts_mixture_and_mass_fractions(self):
        fixture_path = (
            Path(__file__).parent
            / "test_simulation"
            / "test_2d_simulation"
            / "data"
            / "t_junction.json"
        )
        payload = json.loads(fixture_path.read_text())
        cfg = SimulationConfig.model_validate(payload)

        material = cfg.fluid_bodies[0].material
        assert material.type.value == "weakly_compressible_mixture"
        assert len(material.species) == 3

        first_bc = cfg.fluid_boundary_conditions[0]
        assert first_bc.mass_fractions == pytest.approx([0.5, 0.3, 0.2])

    def test_t_junction_fixture_rejects_mass_fractions_not_normalized(self):
        fixture_path = (
            Path(__file__).parent
            / "test_simulation"
            / "test_2d_simulation"
            / "data"
            / "t_junction.json"
        )
        payload = json.loads(fixture_path.read_text())
        payload["fluid_boundary_conditions"][0]["mass_fractions"] = [0.6, 0.3, 0.2]

        with pytest.raises(ValidationError, match="mass_fractions must sum to 1.0"):
            SimulationConfig.model_validate(payload)

    def test_t_junction_fixture_rejects_mass_fractions_out_of_range(self):
        fixture_path = (
            Path(__file__).parent
            / "test_simulation"
            / "test_2d_simulation"
            / "data"
            / "t_junction.json"
        )
        payload = json.loads(fixture_path.read_text())
        payload["fluid_boundary_conditions"][0]["mass_fractions"] = [1.2, -0.1, -0.1]

        with pytest.raises(ValidationError, match="mass_fractions values must be in \\[0, 1\\]"):
            SimulationConfig.model_validate(payload)

    def test_fluid_solver_accepts_max_velocity_factor(self):
        cfg = _make_minimal_fluid_config(
            solver_parameters={
                "end_time": 1.0,
                "output_interval": 0.01,
                "screen_interval": 100,
                "fluid_dynamics": {
                    "acoustic_cfl": 0.6,
                    "advection_cfl": 0.25,
                    "max_velocity_factor": 2.0,
                    "surface_type": "free_surface",
                    "particle_sort_frequency": 100,
                },
            }
        )
        assert cfg.solver_parameters.fluid_dynamics is not None
        assert cfg.solver_parameters.fluid_dynamics.max_velocity_factor == pytest.approx(2.0)

    def test_fluid_material_accepts_viscosity_reynolds_number_object(self):
        cfg = _make_minimal_fluid_config(
            fluid_bodies=[
                {
                    "name": "WaterBody",
                    "material": {
                        "type": "weakly_compressible_fluid",
                        "density": 1000.0,
                        "viscosity": {"Reynolds_number": 50.0},
                    },
                }
            ]
        )
        assert cfg.fluid_bodies[0].material.viscosity is not None

    def test_fluid_solver_max_velocity_factor_default(self):
        cfg = _make_minimal_fluid_config()
        assert cfg.solver_parameters.fluid_dynamics is not None
        assert cfg.solver_parameters.fluid_dynamics.max_velocity_factor == pytest.approx(1.0)

    def test_fluid_material_accepts_thermal_properties(self):
        cfg = _make_minimal_fluid_config(
            fluid_bodies=[
                {
                    "name": "WaterBody",
                    "material": {
                        "type": "weakly_compressible_fluid",
                        "density": 1000.0,
                        "thermal_properties": {
                            "thermal_conductivity": 0.6,
                            "volumetric_heat_capacity": 4181.3,
                        },
                    },
                }
            ]
        )
        thermal = cfg.fluid_bodies[0].material.thermal_properties
        assert thermal is not None
        assert thermal.thermal_conductivity == pytest.approx(0.6)
        assert thermal.volumetric_heat_capacity == pytest.approx(4181.3)

    def test_fluid_material_rejects_incomplete_thermal_properties(self):
        with pytest.raises(ValidationError, match="thermal_properties requires"):
            _make_minimal_fluid_config(
                fluid_bodies=[
                    {
                        "name": "WaterBody",
                        "material": {
                            "type": "weakly_compressible_fluid",
                            "density": 1000.0,
                            "thermal_properties": {
                                "thermal_conductivity": 0.6,
                            },
                        },
                    }
                ]
            )

    def test_solid_material_accepts_thermal_boundary_mode(self):
        cfg = _make_minimal_fluid_config(
            solid_bodies=[
                {
                    "name": "WallBoundary",
                    "material": {
                        "type": "rigid_body",
                        "thermal_properties": {
                            "thermal_boundary": "Dirichlet",
                        },
                    },
                }
            ]
        )
        thermal = cfg.solid_bodies[0].material.thermal_properties
        assert thermal is not None
        assert thermal.thermal_boundary is not None
        assert thermal.thermal_boundary.value == "Dirichlet"

    def test_characteristic_dimensions_support_new_base_units(self):
        cfg = _make_minimal_fluid_config(
            characteristic_dimensions=[
                {
                    "value": 1.0,
                    "name": "Length",
                    "hint": "geometries.system_domain.upper_bound",
                },
                {
                    "value": 1.0,
                    "name": "Temperature",
                    "hint": "geometries.system_domain.upper_bound",
                },
                {
                    "value": 1.0,
                    "name": "ElectricCurrent",
                    "hint": "geometries.system_domain.upper_bound",
                },
                {
                    "value": 1.0,
                    "name": "AmountOfSubstance",
                    "hint": "geometries.system_domain.upper_bound",
                },
                {
                    "value": 1.0,
                    "name": "LuminousIntensity",
                    "hint": "geometries.system_domain.upper_bound",
                },
                {
                    "value": 1.0,
                    "name": "AngularVelocity",
                    "hint": "geometries.system_domain.upper_bound",
                },
            ]
        )
        names = {d.name.value for d in cfg.characteristic_dimensions or []}
        assert "Temperature" in names
        assert "ElectricCurrent" in names
        assert "AmountOfSubstance" in names
        assert "LuminousIntensity" in names
        assert "AngularVelocity" in names

    def test_continuum_config_can_omit_restart(self):
        cfg = _make_minimal_continuum_config()
        assert cfg.solver_parameters.restart is None

    def test_complex_shape_disallows_intersection(self):
        with pytest.raises(ValidationError, match="only support union and subtraction"):
            _make_minimal_fluid_config(
                geometries={
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
                            "lower_bound": [0.0, 0.0],
                            "upper_bound": [1.0, 1.0],
                        },
                        {
                            "name": "BadComplex",
                            "type": "complex_shape",
                            "sub_shapes": ["WaterBody", "WallBoundary"],
                            "operations": ["union", "intersection"],
                        },
                    ],
                }
            )
