"""Pre-run simulation configuration visualizer.

Renders an interactive 3-D (or 2-D) preview of the simulation setup —
geometries, boundary conditions and body annotations — from a validated
:class:`~sphinxsim.config.schemas.SimulationConfig`.

Two rendering modes are supported:

VTP mode (preferred)
    The C++ ``buildGeometries()`` stage is invoked first so that the geometry
    builders write ``Shape<Name>.vtp`` files.  Those accurate polygon meshes
    are then loaded and displayed by PyVista.

Schema mode (fallback)
    When the C++ extension is not available (or building geometries fails),
    bounding boxes are reconstructed from the JSON schema and rendered as
    wireframe cubes / rectangles.
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sphinxsim.config.schemas import (
        GeometriesConfig,
        OrientedBoxConfig,
        ShapeConfig,
        SimulationConfig,
    )


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

# Colours assigned per body category so users instantly see what is what.
_FLUID_COLOUR = (0.20, 0.53, 0.85)       # blue
_SOLID_COLOUR = (0.70, 0.70, 0.70)       # grey
_CONTINUUM_COLOUR = (0.90, 0.60, 0.10)   # amber
_UNKNOWN_COLOUR = (0.60, 0.80, 0.40)     # green (shapes not in any body list)
_INLET_OUTLET_COLOUR = (0.85, 0.20, 0.20)  # red
_REGION_COLOUR = (0.85, 0.70, 0.10)        # yellow


def _body_colour(body_name: str, config: "SimulationConfig") -> tuple[float, float, float]:
    for b in config.fluid_bodies:
        if b.name == body_name:
            return _FLUID_COLOUR
    for b in config.solid_bodies:
        if b.name == body_name:
            return _SOLID_COLOUR
    for b in config.continuum_bodies:
        if b.name == body_name:
            return _CONTINUUM_COLOUR
    return _UNKNOWN_COLOUR


# ---------------------------------------------------------------------------
# Geometry helpers (schema-only fallback)
# ---------------------------------------------------------------------------

def _bounds_to_box(lower: list[float], upper: list[float]) -> Any:
    """Create a PyVista box mesh from lower/upper bounds."""
    import pyvista as pv  # type: ignore[import]

    if len(lower) == 2:
        # 2-D: extrude a thin slab so the box is still visible in 3-D view
        return pv.Box(
            bounds=(lower[0], upper[0], lower[1], upper[1], -0.01, 0.01)
        )
    return pv.Box(bounds=(lower[0], upper[0], lower[1], upper[1], lower[2], upper[2]))


def _schema_mesh_for_shape(shape: "ShapeConfig", config: "SimulationConfig") -> Any | None:
    """Build a fallback PyVista mesh from shape schema data."""
    import pyvista as pv  # type: ignore[import]

    stype = shape.type.value

    if stype in ("bounding_box", "multipolygon"):
        if shape.lower_bound is not None and shape.upper_bound is not None:
            return _bounds_to_box(shape.lower_bound, shape.upper_bound)

        # multipolygon: compute composite bounds from polygon entries
        if shape.polygons:
            lbs, ubs = [], []
            for poly in shape.polygons:
                if poly.lower_bound and poly.upper_bound:
                    lbs.append(poly.lower_bound)
                    ubs.append(poly.upper_bound)
                elif poly.inner_lower_bound and poly.inner_upper_bound:
                    lbs.append(poly.inner_lower_bound)
                    ubs.append(poly.inner_upper_bound)
            if lbs and ubs:
                lo = [min(b[i] for b in lbs) for i in range(len(lbs[0]))]
                hi = [max(b[i] for b in ubs) for i in range(len(ubs[0]))]
                return _bounds_to_box(lo, hi)

    if stype == "box":
        if shape.half_size is not None:
            h = shape.half_size
            if len(h) == 2:
                lo, hi = [-h[0], -h[1]], [h[0], h[1]]
            else:
                lo, hi = [-h[0], -h[1], -h[2]], [h[0], h[1], h[2]]
            mesh = _bounds_to_box(lo, hi)
            if shape.transform is not None:
                t = shape.transform.translation
                angle = shape.transform.rotation_angle
                if len(t) == 2:
                    mesh.translate([t[0], t[1], 0.0], inplace=True)
                else:
                    mesh.translate(t, inplace=True)
                if angle != 0.0:
                    axis = shape.transform.rotation_axis or [0.0, 0.0, 1.0]
                    mesh.rotate_vector(axis, math.degrees(angle), inplace=True)
            return mesh

    if stype == "expanded_box":
        # Find the original shape and expand its bounds
        orig_name = shape.original
        expansion = shape.expansion or 0.0
        for s in (config.geometries.shapes if config else []):
            if s.name == orig_name:
                orig_mesh = _schema_mesh_for_shape(s, config)
                if orig_mesh is not None:
                    orig_mesh.translate([0, 0, 0], inplace=True)  # ensure copy
                    b = orig_mesh.bounds  # (xmin,xmax,ymin,ymax,zmin,zmax)
                    return pv.Box(bounds=(
                        b[0] - expansion, b[1] + expansion,
                        b[2] - expansion, b[3] + expansion,
                        b[4] - expansion, b[5] + expansion,
                    ))

    if stype == "triangle_mesh":
        # Can't reconstruct without the file; return None (skip in fallback)
        return None

    if stype == "complex_shape":
        # Boolean compound — skip; sub-shapes are rendered separately
        return None

    return None


def _schema_mesh_for_oriented_box(ob: "OrientedBoxConfig") -> Any | None:
    """Build a PyVista mesh for an oriented box region or in/outlet."""
    import pyvista as pv  # type: ignore[import]

    if ob.type.value == "in_outlet":
        if ob.center is None or ob.radius is None:
            return None
        c = ob.center
        r = ob.radius
        if len(c) == 2:
            # Thin slab centred on the inlet face
            n = ob.normal or [1.0, 0.0]
            # Build a small box perpendicular to normal
            nx, ny = n[0], n[1]
            length = r * 2
            perp = r
            mesh = pv.Box(bounds=(-length / 2, length / 2, -perp, perp, -0.02, 0.02))
            angle = math.degrees(math.atan2(ny, nx))
            mesh.rotate_z(angle, inplace=True)
            mesh.translate([c[0], c[1], 0.0], inplace=True)
        else:
            mesh = pv.Sphere(radius=ob.radius, center=(c[0], c[1], c[2]))
        return mesh

    if ob.type.value == "region":
        if ob.half_size is None or ob.transform is None:
            return None
        h = ob.half_size
        t = ob.transform.translation
        angle = ob.transform.rotation_angle
        if len(h) == 2:
            mesh = _bounds_to_box([-h[0], -h[1]], [h[0], h[1]])
            mesh.translate([t[0], t[1], 0.0], inplace=True)
        else:
            mesh = pv.Box(bounds=(-h[0], h[0], -h[1], h[1], -h[2], h[2]))
            mesh.translate(t, inplace=True)
        if angle != 0.0:
            axis = ob.transform.rotation_axis or [0.0, 0.0, 1.0]
            mesh.rotate_vector(axis, math.degrees(angle), inplace=True)
        return mesh

    return None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ConfigVisualizer:
    """Visualize a simulation configuration before running the solver.

    Parameters
    ----------
    config:
        Validated :class:`~sphinxsim.config.schemas.SimulationConfig`.
    project_root:
        Root of the SPHinXsim project (used to locate temporary build files).
    off_screen:
        When *True*, render to an off-screen buffer instead of opening a
        window.  Useful for testing.
    """

    def __init__(
        self,
        config: "SimulationConfig",
        project_root: Path,
        *,
        off_screen: bool = False,
    ) -> None:
        self.config = config
        self.project_root = Path(project_root)
        self.off_screen = off_screen

        self._vtp_dir: Path | None = None
        self._cpp_shape_bounds: dict[str, tuple[list[float], list[float]]] | None = None

    @property
    def used_cpp_geometry(self) -> bool:
        """Whether the most recent preview used C++-generated VTP geometry."""
        return self._vtp_dir is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def preview(
        self,
        *,
        title: str = "SPHinXsim - Configuration Preview",
        use_cpp: bool = True,
    ) -> None:
        """Render the configuration preview.

        Parameters
        ----------
        title:
            Window title.
        use_cpp:
            When *True*, attempt to call ``buildGeometries()`` from the C++
            extension so that accurate VTP meshes are available.  Falls back
            to schema-based bounding-box reconstruction automatically.
        """
        try:
            import pyvista as pv  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "PyVista is required for visualization.\n"
                "Install it with:  pip install sphinxsim[visualization]"
            ) from None

        vtp_dir: Path | None = None
        if use_cpp:
            vtp_dir = self._try_build_geometries()
        else:
            self._cpp_shape_bounds = None
        self._vtp_dir = vtp_dir

        plotter = pv.Plotter(title=title, off_screen=self.off_screen)
        self._populate_plotter(plotter, vtp_dir)
        plotter.add_axes()
        plotter.show_grid()

        if vtp_dir:
            mode_label = "VTP geometry"
        elif self._cpp_shape_bounds:
            mode_label = "C++ bounds fallback"
        else:
            mode_label = "Schema bounding-box fallback"
        plotter.add_text(
            f"{title}\n[{mode_label}]",
            position="upper_left",
            font_size=10,
            color="white",
        )

        plotter.show()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_build_geometries(self) -> Path | None:
        """Run buildGeometries() and return the VTP output directory, or None."""
        try:
            import _sphinxsys_core_2d as sph  # type: ignore[import]
        except ImportError:
            try:
                import _sphinxsys_core_3d as sph  # type: ignore[import]
            except ImportError:
                return None

        vtp_output_dir = self.project_root / ".build-temp" / "preview_geometry"
        vtp_output_dir.mkdir(parents=True, exist_ok=True)

        tmp_cfg = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="sphinxsim_preview_"
        )
        try:
            tmp_cfg.write(self.config.model_dump_json(indent=2, exclude_none=True))
            tmp_cfg.close()

            original_dir = os.getcwd()
            try:
                sim = sph.SPHSimulation(tmp_cfg.name)
                sim.resetOutputRoot(str(vtp_output_dir))
                sim.buildGeometries()
                try:
                    self._cpp_shape_bounds = dict(sim.getShapeBounds())
                except Exception:
                    self._cpp_shape_bounds = None
            finally:
                os.chdir(original_dir)

        except Exception:
            return None
        finally:
            try:
                os.unlink(tmp_cfg.name)
            except OSError:
                pass

        # VTPs land in <vtp_output_dir>/output/
        output_subdir = vtp_output_dir / "output"
        if output_subdir.is_dir() and any(output_subdir.glob("Shape*.vtp")):
            return output_subdir
        # Fallback: check the root itself
        if any(vtp_output_dir.glob("Shape*.vtp")):
            return vtp_output_dir

        return None

    def _populate_plotter(self, plotter: Any, vtp_dir: Path | None) -> None:
        """Add all shapes and annotations to *plotter*."""
        import pyvista as pv  # type: ignore[import]

        from sphinxsim.visualization.annotations import (
            body_label,
            gravity_label,
            oriented_box_label,
        )

        config = self.config

        # Build a name → colour map for body shapes
        body_names: set[str] = set()
        body_names.update(b.name for b in config.fluid_bodies)
        body_names.update(b.name for b in config.solid_bodies)
        body_names.update(b.name for b in config.continuum_bodies)

        rendered_shapes: set[str] = set()

        # --- Render each shape ---
        for shape in config.geometries.shapes:
            if shape.type.value == "complex_shape":
                # Skip — rendered via sub-shapes
                continue

            mesh = self._load_shape_mesh(shape, vtp_dir, config)
            if mesh is None:
                continue

            is_body = shape.name in body_names
            colour = _body_colour(shape.name, config)
            opacity = 0.6 if is_body else 0.35
            style = "surface" if is_body else "wireframe"

            plotter.add_mesh(
                mesh,
                color=colour,
                opacity=opacity,
                style=style,
                label=shape.name,
            )

            # Label at mesh centroid
            centre = mesh.center
            label_text = body_label(shape.name, config) if is_body else shape.name
            plotter.add_point_labels(
                [centre],
                [label_text],
                point_size=0,
                font_size=8,
                text_color="white",
                always_visible=True,
            )
            rendered_shapes.add(shape.name)

        # --- Render oriented boxes (in/outlets and constraint regions) ---
        for ob in config.geometries.oriented_boxes:
            mesh = self._load_oriented_box_mesh(ob, vtp_dir)
            if mesh is None:
                mesh = _schema_mesh_for_oriented_box(ob)
            if mesh is None:
                continue

            colour = _INLET_OUTLET_COLOUR if ob.type.value == "in_outlet" else _REGION_COLOUR
            plotter.add_mesh(
                mesh,
                color=colour,
                opacity=0.50,
                style="wireframe",
                line_width=2,
                label=ob.name,
            )
            label_text = oriented_box_label(ob, config)
            plotter.add_point_labels(
                [mesh.center],
                [label_text],
                point_size=0,
                font_size=7,
                text_color="yellow",
                always_visible=True,
            )

        # --- Domain bounding box ---
        if config.geometries.system_domain is not None:
            domain = config.geometries.system_domain
            domain_mesh = _bounds_to_box(domain.lower_bound, domain.upper_bound)
            plotter.add_mesh(
                domain_mesh,
                color="white",
                opacity=0.10,
                style="wireframe",
                line_width=1,
            )

        # --- Gravity annotation ---
        g_label = gravity_label(config)
        if g_label:
            plotter.add_text(g_label, position="lower_left", font_size=9, color="cyan")

        # --- Legend ---
        legend_entries = [
            ["Fluid body", _FLUID_COLOUR],
            ["Solid body", _SOLID_COLOUR],
            ["Continuum body", _CONTINUUM_COLOUR],
            ["Other shape", _UNKNOWN_COLOUR],
            ["Inlet/Outlet", _INLET_OUTLET_COLOUR],
            ["Region", _REGION_COLOUR],
        ]
        plotter.add_legend(
            [
                (entry[0], [int(c * 255) for c in entry[1]])
                for entry in legend_entries
            ],
            bcolor="black",
            border=True,
        )

    def _load_shape_mesh(
        self,
        shape: "ShapeConfig",
        vtp_dir: Path | None,
        config: "SimulationConfig",
    ) -> Any | None:
        """Load the mesh for *shape* — VTP first, C++ bounds second, schema fallback last."""
        if vtp_dir is not None:
            vtp_path = vtp_dir / f"Shape{shape.name}.vtp"
            if vtp_path.exists():
                try:
                    import pyvista as pv  # type: ignore[import]
                    return pv.read(str(vtp_path))
                except Exception:
                    pass

        if self._cpp_shape_bounds is not None and shape.name in self._cpp_shape_bounds:
            lower, upper = self._cpp_shape_bounds[shape.name]
            return _bounds_to_box(list(lower), list(upper))

        return _schema_mesh_for_shape(shape, config)

    def _load_oriented_box_mesh(
        self, ob: "OrientedBoxConfig", vtp_dir: Path | None
    ) -> Any | None:
        """Load the oriented-box VTP written by addOrientedBox()."""
        if vtp_dir is None:
            return None
        vtp_path = vtp_dir / f"Shape{ob.name}.vtp"
        if not vtp_path.exists():
            return None
        try:
            import pyvista as pv  # type: ignore[import]
            return pv.read(str(vtp_path))
        except Exception:
            return None
