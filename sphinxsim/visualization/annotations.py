"""Annotation helpers for simulation preview visualization.

Builds human-readable label strings for shapes, bodies, boundary conditions,
and initial conditions from a SimulationConfig.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinxsim.config.schemas import (
        BodyConstraintConfig,
        FluidBoundaryConditionConfig,
        ObserverConfig,
        OrientedBoxConfig,
        SimulationConfig,
    )


def body_label(body_name: str, config: "SimulationConfig") -> str:
    """Return a short label string for a body shape."""
    for body in config.fluid_bodies:
        if body.name == body_name:
            mat = body.material
            parts = [f"Fluid: {body_name}", f"ρ={mat.density}"]
            if mat.sound_speed is not None:
                parts.append(f"c={mat.sound_speed}")
            if mat.viscosity is not None:
                visc = mat.viscosity
                if isinstance(visc, (int, float)):
                    parts.append(f"μ={visc}")
            if mat.thermal_properties is not None:
                tp = mat.thermal_properties
                if tp.thermal_boundary is not None:
                    parts.append(f"Thermal: {tp.thermal_boundary.value}")
            return "\n".join(parts)

    for body in config.solid_bodies:
        if body.name == body_name:
            return f"Solid: {body_name}\n(rigid)"

    for body in config.continuum_bodies:
        if body.name == body_name:
            mat = body.material
            parts = [f"Continuum: {body_name}", f"material={mat.type.value}"]
            if mat.density is not None:
                parts.append(f"ρ={mat.density}")
            return "\n".join(parts)

    return body_name


def oriented_box_label(ob: "OrientedBoxConfig", config: "SimulationConfig") -> str:
    """Return an annotation label for an oriented box, including its BCs."""
    parts = [f"{ob.name} [{ob.type.value}]"]

    # Fluid boundary conditions
    for bc in config.fluid_boundary_conditions:
        if bc.oriented_box == ob.name:
            bc_parts = [f"BC → {bc.body_name}: {bc.type.value}"]
            if bc.inflow_speed is not None:
                bc_parts.append(f"v={bc.inflow_speed}")
            if bc.pressure is not None:
                bc_parts.append(f"p={bc.pressure}")
            parts.append(" ".join(bc_parts))

    # Particle-relaxation constraints reference oriented boxes directly.
    pg_settings = config.particle_generation.settings
    if pg_settings is not None:
        for constraint in pg_settings.relaxation_constraints:
            if constraint.oriented_box == ob.name:
                parts.append(
                    f"Relaxation constraint → {constraint.body_name}: {constraint.type}"
                )

    return "\n".join(parts)


def gravity_label(config: "SimulationConfig") -> str | None:
    """Return a gravity annotation string, or None if gravity is not set."""
    if config.gravity is None:
        return None
    g = config.gravity
    if len(g) == 2:
        return f"g = ({g[0]}, {g[1]})"
    return f"g = ({g[0]}, {g[1]}, {g[2]})"


def observer_label(observer: "ObserverConfig") -> str:
    """Return an annotation label for an observer definition."""
    variable = observer.variable
    variable_name = variable.real_type if variable.real_type is not None else variable.vector_type
    return (
        f"Observer: {observer.name}\n"
        f"body={observer.observed_body}\n"
        f"var={variable_name}"
    )


def body_constraint_label(constraint: "BodyConstraintConfig") -> str:
    """Return an annotation label for a body constraint definition.

    Covers both ``fixed`` and ``simbody`` constraint types.  When a
    ``region`` (oriented box name) is specified the label notes it; otherwise
    the constraint applies to the entire body.
    """
    parts = [f"Constraint → {constraint.body_name}", f"type={constraint.type.value}"]

    if constraint.region is not None:
        parts.append(f"region={constraint.region}")

    if constraint.type.value == "simbody":
        if constraint.mobilized_body is not None:
            parts.append(f"mob={constraint.mobilized_body}")
        if constraint.velocity is not None:
            v = constraint.velocity
            if len(v) == 2:
                parts.append(f"v=({v[0]}, {v[1]})")
            else:
                parts.append(f"v=({v[0]}, {v[1]}, {v[2]})")
        if constraint.angular_velocity is not None:
            parts.append(f"ω={constraint.angular_velocity}")

    return "\n".join(parts)
