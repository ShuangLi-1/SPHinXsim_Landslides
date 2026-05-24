"""Annotation helpers for simulation preview visualization.

Builds human-readable label strings for shapes, bodies, boundary conditions,
and initial conditions from a SimulationConfig.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinxsim.config.schemas import (
        FluidBoundaryConditionConfig,
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

    # Body constraints that reference this oriented box as a region
    for constraint in config.body_constraints:
        if constraint.region == ob.name:
            parts.append(f"Constraint → {constraint.body_name}: {constraint.type.value}")

    return "\n".join(parts)


def gravity_label(config: "SimulationConfig") -> str | None:
    """Return a gravity annotation string, or None if gravity is not set."""
    if config.gravity is None:
        return None
    g = config.gravity
    if len(g) == 2:
        return f"g = ({g[0]}, {g[1]})"
    return f"g = ({g[0]}, {g[1]}, {g[2]})"
