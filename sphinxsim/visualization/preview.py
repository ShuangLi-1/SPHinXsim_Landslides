"""Pre-run simulation configuration visualizer.

Renders an interactive 3-D (or 2-D) preview of the simulation setup —
geometries, boundary conditions and body annotations — from a validated
:class:`~sphinxsim.config.schemas.SimulationConfig`.

Two rendering modes are supported, tried in order:

VTP mode (preferred)
    The C++ ``buildGeometries()`` stage is invoked and the resulting
    ``Shape<Name>.vtp`` polygon meshes are loaded and displayed by PyVista.
    The live :class:`SPHSimulation` object is kept in ``_sim`` for further
    queries.

C++ bounds fallback
    When VTP files are not produced, accurate bounding boxes are queried
    directly from the live C++ simulation object via ``getShapeBounds()``.

The C++ extension (``_sphinxsys_core_2d`` or ``_sphinxsys_core_3d``) must
be installed.  If it is not found an :class:`ImportError` is raised with
a clear install hint.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sphinxsim.config.schemas import (
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
# Geometry helpers
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
    config_path:
        Path to the original JSON config file.  Passed directly to
        :class:`SPHSimulation` — the file is the single source of truth.
        Required for C++ geometry building; if omitted no shapes are rendered.
    off_screen:
        When *True*, render to an off-screen buffer instead of opening a
        window.  Useful for testing.
    """

    def __init__(
        self,
        config: "SimulationConfig",
        project_root: Path,
        *,
        config_path: Path | None = None,
        off_screen: bool = False,
    ) -> None:
        self.config = config
        self.project_root = Path(project_root)
        self.config_path = Path(config_path) if config_path is not None else None
        self.off_screen = off_screen

        self._vtp_dir: Path | None = None
        self._sim: Any | None = None
        self._shape_bounds_cache: dict[str, Any] | None = None

    @property
    def used_cpp_geometry(self) -> bool:
        """Whether the most recent preview used C++-generated VTP geometry."""
        return self._vtp_dir is not None

    @property
    def used_cpp_bounds(self) -> bool:
        """Whether the most recent preview used live C++ shape bounds."""
        return self._sim is not None

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
            When *True*, call ``buildGeometries()`` from the C++ extension.
            Raises :class:`ImportError` if the extension is not installed.
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
            self._sim = None
            self._shape_bounds_cache = None
        self._vtp_dir = vtp_dir

        plotter = pv.Plotter(title=title, off_screen=self.off_screen)
        self._populate_plotter(plotter, vtp_dir)
        plotter.add_axes()
        plotter.show_grid()

        if vtp_dir:
            mode_label = "VTP geometry"
        elif self._sim is not None:
            mode_label = "C++ bounds fallback"
        else:
            mode_label = "No C++ geometry"
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
        """Run buildGeometries() and return the VTP output directory, or None.

        Uses ``self.config_path`` directly as the C++ config input so the
        original JSON file is the single source of truth.  The live
        :class:`SPHSimulation` object is kept as ``self._sim`` for further
        queries (e.g. ``getShapeBounds()``).
        """
        if self.config_path is None:
            self._sim = None
            return None

        try:
            import _sphinxsys_core_2d as sph  # type: ignore[import]
        except ImportError:
            try:
                import _sphinxsys_core_3d as sph  # type: ignore[import]
            except ImportError:
                raise ImportError(
                    "C++ extension not found (_sphinxsys_core_2d / _sphinxsys_core_3d).\n"
                    "Build and install the compiled sphinxsim package to use preview."
                ) from None

        vtp_output_dir = self.project_root / ".build-temp" / "preview_geometry"
        vtp_output_dir.mkdir(parents=True, exist_ok=True)
        output_subdir = vtp_output_dir / "output"
        for stale_dir in (vtp_output_dir, output_subdir):
            if not stale_dir.is_dir():
                continue
            for stale_vtp in stale_dir.glob("Shape*.vtp"):
                try:
                    stale_vtp.unlink()
                except OSError:
                    pass

        original_dir = os.getcwd()
        try:
            sim = sph.SPHSimulation(str(self.config_path))
            sim.resetOutputRoot(str(vtp_output_dir))
            sim.buildGeometries()
            self._sim = sim
            self._shape_bounds_cache = None
        except Exception:
            self._sim = None
            self._shape_bounds_cache = None
            return None
        finally:
            os.chdir(original_dir)

        # VTPs land in <vtp_output_dir>/output/
        if output_subdir.is_dir() and any(output_subdir.glob("Shape*.vtp")):
            return output_subdir
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
        """Load the mesh for *shape* — VTP first, C++ bounds second."""
        if vtp_dir is not None:
            vtp_path = vtp_dir / f"Shape{shape.name}.vtp"
            if vtp_path.exists():
                try:
                    import pyvista as pv  # type: ignore[import]
                    return pv.read(str(vtp_path))
                except Exception:
                    pass

        if self._sim is not None:
            try:
                if self._shape_bounds_cache is None:
                    self._shape_bounds_cache = self._sim.getShapeBounds()
                if shape.name in self._shape_bounds_cache:
                    lower, upper = self._shape_bounds_cache[shape.name]
                    return _bounds_to_box(list(lower), list(upper))
            except Exception:
                self._shape_bounds_cache = {}
                pass

        return None

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
