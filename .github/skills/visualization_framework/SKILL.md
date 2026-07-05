---
name: visualization-framework
description: "SPHinXsim visualization framework guidance for preview architecture, rendering modes, annotations, constraints, and testing patterns. Invoke by default for any task that edits or debugs files under sphinxsim/visualization."
---

# SPHinXsim Visualization Framework

## Purpose
Use this skill when working on preview and rendering behavior in SPHinXsim, especially under `sphinxsim/visualization`.

## Invocation Triggers
Invoke this skill by default when any of the following is true:
- The task modifies any file under `sphinxsim/visualization`.
- The task debugs preview behavior, plotting behavior, camera/view mode, labels, or legend content.
- The task touches visualization tests in `tests/test_visualization.py`.

Do not skip this skill for visualization-path changes, even if the user request is brief.

## Scope
Covers:
- Rendering pipeline and fallback behavior
- `ConfigVisualizer` rendering flow
- Annotation/label conventions
- Body constraints and observer visualization
- 2D vs 3D preview behavior
- Visualization testing patterns

Does not cover:
- General C++ solver runtime debugging unrelated to preview
- New project scaffolding
- Non-visualization CLI features

## Architecture

### Rendering pipeline (priority order)
1. VTP mode (preferred)
- C++ `buildGeometries()` generates `.vtp` polygon meshes.
- PyVista loads meshes for rendering.
- Preferred for geometry fidelity.

2. C++ bounds fallback
- If VTP meshes are unavailable, query bounds from C++ simulation object.
- Render bounding boxes as fallback.

Design rule:
- Prefer VTP/VTK objects for visualization.
- Avoid constructing ad-hoc meshes from config-only geometry when VTP/VTK path is expected.

## Core files
- `sphinxsim/visualization/preview.py`
- `sphinxsim/visualization/annotations.py`
- `tests/test_visualization.py`

## Key conventions

### `ConfigVisualizer` responsibilities
- Resolve spatial dimension / view mode.
- Populate plotter with shapes, oriented boxes, constraints, observers, and annotations.
- Keep rendering robust when PyVista or mesh assets are unavailable.

### Annotation functions
Keep annotation formatting centralized in `annotations.py`:
- `body_label(...)`
- `oriented_box_label(...)`
- `observer_label(...)`
- `body_constraint_label(...)`
- `gravity_label(...)`

Guidelines:
- Use compact, readable multiline labels.
- Keep display fields stable to avoid test churn.

### Color palette
Use fixed semantic color constants in `preview.py` for element classes (fluid, solid, continuum, region, observer, constraint, etc.).

## Body constraints rendering pattern
For each `config.body_constraints` item:
- Build label with `body_constraint_label(...)`.
- If constraint has a valid `region` referencing an oriented box:
  - render region overlay (wireframe style, constraint color).
  - place label at overlay center.
- Else:
  - resolve target body shape by name.
  - place label at body mesh center when mesh is available.

## 2D rendering notes
- 2D mode should use orthographic XY-style view behavior.
- Keep controls and camera defaults consistent with dimension inference.
- Ensure labels and overlays remain legible in planar mode.

## Testing playbook
Use `tests/test_visualization.py`.

1. Label unit tests
- Validate generated text content for each annotation function.
- Prefer strict substring assertions for critical fields.

2. Preview rendering tests
- Use mocked PyVista objects and fake plotter methods.
- Assert rendering flow does not raise.
- Assert expected plotting calls when behavior is deterministic.

3. Config validation-aware fixtures
- Build test config via `SimulationConfig(**data)`.
- Respect schema requirements:
  - region oriented box requires `half_size` and `transform`.
  - simbody constraints require `solver_parameters.restart`.

## Common failure patterns
- Missing import in local `annotations` import block inside `_populate_plotter`.
- Invalid oriented box schema in tests (`center/normal/radius` used for region type).
- Simbody test configs missing restart section.
- Mismatch between expected label text and annotation formatter.

## Implementation checklist
When adding a new visualization element:
1. Add or extend schema model/validation if needed.
2. Add annotation helper in `annotations.py`.
3. Add render block in `_populate_plotter` with semantic color constant.
4. Update legend entries.
5. Add label tests and preview tests.
6. Run visualization test file.

## Verification command
From repo root:

```bash
.venv/bin/python -m pytest tests/test_visualization.py -v
```
