"""Pre-run simulation configuration visualizer.

Renders an interactive 3-D (or 2-D) preview of the simulation setup —
geometries, boundary conditions and body annotations — from a validated
:class:`~sphinxsim.config.schemas.SimulationConfig`.

Two rendering modes are supported, tried in order:

VTP mode (preferred)
    The C++ ``buildGeometries()`` stage is invoked and the resulting
    ``Shape<Name>.vtp`` polygon meshes are loaded and displayed by PyVista.
    The lightweight C++ ``GeometryBuilder`` is used for this stage.

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

from sphinxsim.bindings.loader import load_sphinxsys_core, load_sphinxsys_core_nd

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


def _label_anchor_point(mesh: Any) -> tuple[float, float, float]:
    """Choose a label position inside *mesh* when possible.

    For concave shapes the geometric center can lie outside. We sample a few
    points inside the axis-aligned bounds and keep the first point confirmed as
    enclosed by the surface. If enclosure checks are unavailable, we fall back
    to the mesh center.
    """
    try:
        import pyvista as pv  # type: ignore[import]
    except Exception:
        return tuple(float(v) for v in mesh.center)

    bounds = mesh.bounds
    x0, x1, y0, y1, z0, z1 = (float(v) for v in bounds)
    center = tuple(float(v) for v in mesh.center)

    # Probe from center outward; using interior fractions avoids boundary points.
    fractions = (0.5, 0.35, 0.65, 0.2, 0.8)
    candidates = []
    for fx in fractions:
        x = x0 + (x1 - x0) * fx
        for fy in fractions:
            y = y0 + (y1 - y0) * fy
            for fz in fractions:
                z = z0 + (z1 - z0) * fz
                candidates.append((x, y, z))

    # Ensure the geometric center is always tested first.
    candidates.insert(0, center)

    try:
        points = pv.PolyData(candidates)
        selected = points.select_enclosed_points(
            mesh,
            tolerance=1e-6,
            check_surface=False,
        )
        mask = selected["SelectedPoints"]
        for idx, value in enumerate(mask):
            if int(value) == 1:
                point = candidates[idx]
                return (float(point[0]), float(point[1]), float(point[2]))
    except Exception:
        pass

    return center


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
        self._bounds_sim: Any | None = None
        self._shape_bounds_cache: dict[str, Any] | None = None

    def _spatial_dim(self) -> int:
        """Return the spatial dimension (2 or 3) inferred from the config.

        Checks multiple vector fields in order of reliability so the correct
        binding module is selected even when ``system_domain`` is absent.
        """
        geo = self.config.geometries

        # Most reliable: system_domain explicitly declares the bounding box.
        if geo.system_domain is not None:
            return len(geo.system_domain.lower_bound)

        # Top-level gravity vector.
        if self.config.gravity is not None:
            return len(self.config.gravity)

        # Walk shapes: bounding_box / box / expanded_box carry explicit vectors.
        for shape in geo.shapes:
            for vec in (shape.lower_bound, shape.upper_bound, shape.half_size):
                if vec is not None:
                    return len(vec)
            if shape.transform is not None:
                return len(shape.transform.translation)
            # triangle_mesh: translation field is 3-D only (min_length=3).
            if shape.translation is not None:
                return len(shape.translation)

        # Walk oriented boxes: center / normal / half_size.
        for ob in geo.oriented_boxes:
            for vec in (ob.center, ob.normal, ob.half_size):
                if vec is not None:
                    return len(vec)
            if ob.transform is not None:
                return len(ob.transform.translation)

        return 3  # safe default — 3-D module handles most cases

    @property
    def used_cpp_geometry(self) -> bool:
        """Whether the most recent preview used C++-generated VTP geometry."""
        return self._vtp_dir is not None

    @property
    def used_cpp_bounds(self) -> bool:
        """Whether the most recent preview used live C++ shape bounds."""
        return self._bounds_sim is not None

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
            self._bounds_sim = None
            self._shape_bounds_cache = None
        self._vtp_dir = vtp_dir

        plotter = pv.Plotter(title=title, off_screen=self.off_screen)
        self._populate_plotter(plotter, vtp_dir)
        plotter.add_axes()
        plotter.show_grid(font_size=10)
        self._add_view_direction_widgets(plotter)

        if vtp_dir:
            mode_label = "VTP geometry"
        elif self._bounds_sim is not None:
            mode_label = "C++ bounds fallback"
        else:
            mode_label = "No C++ geometry"
        plotter.add_text(
            f"{title}\n[{mode_label}]",
            position="upper_right",
            font_size=8,
            color="white",
        )

        plotter.show()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_view_direction_widgets(self, plotter: Any) -> None:
        """Add on-screen camera view-direction buttons."""

        def set_plus_x() -> None:
            plotter.view_yz(negative=False)

        def set_minus_x() -> None:
            plotter.view_yz(negative=True)

        def set_plus_y() -> None:
            plotter.view_xz(negative=False)

        def set_minus_y() -> None:
            plotter.view_xz(negative=True)

        def set_plus_z() -> None:
            plotter.view_xy(negative=False)

        def set_minus_z() -> None:
            plotter.view_xy(negative=True)

        def set_isometric() -> None:
            plotter.view_isometric()

        # Radio buttons are mutually exclusive, so they behave like view presets.
        buttons = [
            ("+x", set_plus_x, False),
            ("-x", set_minus_x, False),
            ("-y", set_minus_y, False),
            ("+y", set_plus_y, False),
            ("+z", set_plus_z, False),
            ("-z", set_minus_z, False),
            ("isometric", set_isometric, True),
        ]

        group = "camera_view_direction"
        _, height = plotter.window_size
        size = 9
        margin_x = 14.0
        margin_top = 32.0
        y0 = max(10.0, float(height) - margin_top)

        plotter.add_text(
            "Views:",
            position=(margin_x, y0 + 2.0),
            font_size=7,
            color="white",
        )

        x0 = margin_x + 52.0
        dx = 62.0
        for idx, (title, callback, is_default) in enumerate(buttons):
            plotter.add_radio_button_widget(
                callback,
                group,
                value=is_default,
                title=title,
                position=(x0 + dx * idx, y0),
                size=size,
                border_size=1,
                color_on="dodgerblue",
                color_off="gray",
            )

    def _try_build_geometries(self) -> Path | None:
        """Run buildGeometries() and return the VTP output directory, or None.

        Uses ``self.config_path`` directly as the C++ config input so the
        original JSON file is the single source of truth. Geometry generation
        uses the lightweight ``GeometryBuilder`` class. If VTPs are not
        produced, a live :class:`SPHSimulation` is created as a fallback for
        ``getShapeBounds()`` queries.
        """
        if self.config_path is None:
            self._bounds_sim = None
            return None

        ndim = self._spatial_dim()
        try:
            sph = load_sphinxsys_core_nd(ndim)
        except ImportError as exc:
            raise ImportError(str(exc)) from None

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
        # Change to the config file's directory so that relative paths in the
        # JSON (e.g. STL file_path for 3-D triangle_mesh shapes) resolve correctly.
        os.chdir(self.config_path.parent)
        try:
            builder = sph.GeometryBuilder(str(self.config_path))
            builder.resetOutputRoot(str(vtp_output_dir))
            builder.buildGeometries()
            self._bounds_sim = None
            self._shape_bounds_cache = None
        except Exception:
            self._bounds_sim = None
            self._shape_bounds_cache = None
            return None
        finally:
            os.chdir(original_dir)

        # VTPs land in <vtp_output_dir>/output/
        if output_subdir.is_dir() and any(output_subdir.glob("Shape*.vtp")):
            return output_subdir
        if any(vtp_output_dir.glob("Shape*.vtp")):
            return vtp_output_dir

        # Fallback: build via SPHSimulation so we can query shape bounds.
        try:
            sim = sph.SPHSimulation(str(self.config_path))
            sim.resetOutputRoot(str(vtp_output_dir))
            sim.buildGeometries()
            self._bounds_sim = sim
            self._shape_bounds_cache = None
        except Exception:
            self._bounds_sim = None
            self._shape_bounds_cache = None

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

            label_anchor = _label_anchor_point(mesh)
            label_text = body_label(shape.name, config) if is_body else shape.name
            plotter.add_point_labels(
                [label_anchor],
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
            size=(0.16, 0.16),
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

        if self._bounds_sim is not None:
            try:
                if self._shape_bounds_cache is None:
                    self._shape_bounds_cache = self._bounds_sim.getShapeBounds()
                if shape.name in self._shape_bounds_cache:
                    lower, upper = self._shape_bounds_cache[shape.name]
                    return _bounds_to_box(list(lower), list(upper))
            except Exception:
                self._shape_bounds_cache = {}

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
