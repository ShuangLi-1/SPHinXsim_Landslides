# Visualization

SPHinXsim includes a pre-run configuration visualizer that renders your simulation
setup — geometries, bodies, boundary conditions, and physics annotations — before
the expensive C++ solver starts.  This lets you catch setup mistakes early and build
an intuitive picture of what the simulation will run.

## What it shows

| Element | Visual style | Colour |
|---|---|---|
| Fluid body shapes | Solid surface | Blue |
| Solid body shapes | Solid surface | Grey |
| Continuum body shapes | Solid surface | Amber |
| Other defined shapes | Wireframe | Green |
| Inlet/Outlet oriented boxes | Wireframe | Red |
| Constraint region oriented boxes | Wireframe | Yellow |
| System domain bounding box | Wireframe | White (10 % opacity) |

Each shape and oriented box is labelled with an annotation that includes:

- **Body shapes**: material type, density, sound speed, thermal boundary type (when applicable).
- **Oriented boxes**: BC type (emitter, bi-directional), inflow speed or pressure, constraint target.
- **Gravity**: shown in the lower-left corner when a gravity vector is defined.

## Installation

PyVista is an optional dependency.  Install it alongside SPHinXsim with:

```bash
pip install sphinxsim[visualization]
```

## CLI usage

### Interactive shell

`preview` is available as a first-class shell command:

```
sphinxsim> generate "2D heat transfer in a channel" config.json
✅ Config generated and written to ...

sphinxsim> preview
🖼  Building configuration preview for: .../config.json
   Attempting C++ geometry build for accurate VTP meshes...

sphinxsim> preview --no-cpp
🖼  Building configuration preview for: .../config.json
   Using schema-only bounding-box fallback (--no-cpp).
```

`preview` requires a config to be loaded first (via `load` or `generate`).

### Basic preview (direct command)

```bash
sphinxsim preview path/to/config.json
```

This opens an interactive PyVista window showing the geometry.  The visualizer
first attempts to invoke `buildGeometries()` from the C++ extension to produce
accurate polygon-mesh VTP files.  If the extension is not available or the build
fails, it falls back to bounding-box reconstruction from the JSON schema.

### Schema-only fallback (no C++ required)

```bash
sphinxsim preview path/to/config.json --no-cpp
```

Skips the C++ geometry build entirely and reconstructs bounding boxes directly
from the config.  Useful when the C++ extension is not built yet, or for rapid
config iteration where visual accuracy is less important.

### Off-screen rendering

```bash
sphinxsim preview path/to/config.json --off-screen
```

Renders to an off-screen buffer instead of opening a window.  Intended for
automated testing or headless environments.

## Python API

You can also invoke the visualizer directly from Python:

```python
import json
from pathlib import Path
from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.visualization.preview import ConfigVisualizer

config = SimulationConfig(**json.loads(Path("my_config.json").read_text()))

viz = ConfigVisualizer(config, project_root=Path("."))
viz.preview()                     # opens interactive window, tries C++ first
viz.preview(use_cpp=False)        # schema bounding-box fallback only
viz.preview(title="My setup")     # custom window title
```

### `ConfigVisualizer` parameters

| Parameter | Type | Description |
|---|---|---|
| `config` | `SimulationConfig` | Validated Pydantic config object |
| `project_root` | `Path` | Root of the SPHinXsim project (locates `.build-temp/`) |
| `off_screen` | `bool` | Render off-screen when `True` (default `False`) |

### `preview()` parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | `"SPHinXsim — Configuration Preview"` | Window title |
| `use_cpp` | `bool` | `True` | Attempt C++ geometry build before falling back to schema |

## Two-stage rendering strategy

### Stage 1 — VTP geometry (preferred)

When `use_cpp=True` (the default), the visualizer:

1. Writes a validated config to a temporary JSON file.
2. Calls `SPHSimulation.buildGeometries()` from the C++ extension.
3. The C++ builders write `Shape<Name>.vtp` files to `.build-temp/preview_geometry/output/`.
4. PyVista reads and renders those polygon meshes.

This gives **accurate geometry** — including rotations, boolean-composition results,
and imported triangle meshes.

### Stage 2 — Schema bounding-box fallback

When the C++ extension is unavailable (or `--no-cpp` is passed), the visualizer
reconstructs approximate meshes from the JSON schema:

| Shape type | Fallback mesh |
|---|---|
| `bounding_box` | Axis-aligned box from `lower_bound` / `upper_bound` |
| `box` | Box from `half_size` + `transform` (translation and rotation applied) |
| `expanded_box` | Original shape's bounding box expanded by `expansion` |
| `multipolygon` | Bounding box over all polygon entries' bounds |
| `triangle_mesh` | **Not rendered** (file not available at this stage) |
| `complex_shape` | **Not rendered** (rendered via its sub-shapes) |
| `in_outlet` | Thin rectangular slab perpendicular to the normal direction |
| `region` | Box from `half_size` + `transform` |

!!! note
    The bounding-box fallback is always available without a C++ build and is
    useful for a quick sanity check of domain extents and body placement.

## Shape types and VTP availability

Not all shape types produce VTP files in the C++ builders.  Here is the
complete mapping:

| Shape type | VTP written by C++? |
|---|---|
| `bounding_box` | ✅ Yes |
| `box` (with transform/rotation) | ✅ Yes |
| `expanded_box` | ✅ Yes |
| `multipolygon` (2D) | ✅ Yes |
| `triangle_mesh` (3D) | ✅ Yes |
| `complex_shape` | ❌ No (boolean composition of named sub-shapes) |

`complex_shape` geometries are skipped in both VTP mode and schema fallback;
their constituent sub-shapes are rendered individually.

## Annotations module

The `sphinxsim.visualization.annotations` module provides standalone label
generators that can be used outside of PyVista:

```python
from sphinxsim.visualization.annotations import body_label, oriented_box_label, gravity_label

# Human-readable body summary
label = body_label("WaterBody", config)
# → "Fluid: WaterBody\nρ=1000.0\nc=10.0"

# Oriented box with BC annotation
ob = config.geometries.oriented_boxes[0]
label = oriented_box_label(ob, config)
# → "Inlet [in_outlet]\nBC → WaterBody: emitter v=1.5"

# Gravity vector
g = gravity_label(config)
# → "g = (0.0, -9.81)"  or None if not set
```

## Future work

The visualization module is intentionally minimal for this phase.  Planned extensions include:

- **SDF / level-set geometry**: rendering signed-distance-function shapes once those are added to the geometry builder.
- **Particle cloud preview**: optional overlay of generated particle positions after `generateParticles()`.
- **Initial condition colouring**: colour-mapping particle regions by their initial temperature, velocity, or density.
- **BC arrow glyphs**: directional arrows for inflow/outflow boundaries.
- **Embedded notebook support**: inline rendering for Jupyter environments.

## See also

- [CLI Usage](cli-usage.md) for the full command reference
- [Installation](installation.md) for build requirements including VTK/PyVista
