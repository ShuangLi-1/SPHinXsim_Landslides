# Installation Guide

Choose your platform-specific setup guide:

- [Linux Installation](installation-linux.md)
- [Windows Installation](installation-windows.md)
- [macOS Installation](installation-macos.md)

## Shared Notes

- Use CMake presets from the repository root.
- Keep vcpkg outside the repository folder (for example, `../vcpkg`).
- Preferred workflow: use `pip install` from source so Python packaging and C++ extension build happen in one step.

```bash
# Linux/macOS
CMAKE_ARGS="-D CMAKE_TOOLCHAIN_FILE=$(pwd)/../vcpkg/scripts/buildsystems/vcpkg.cmake" \
python3 -m pip install -e ".[dev,visualization]"

# Windows (PowerShell)
$env:CMAKE_ARGS='-D CMAKE_TOOLCHAIN_FILE="' + "$pwd\..\vcpkg\scripts\buildsystems\vcpkg.cmake" + '" -D CMAKE_C_COMPILER=cl -D CMAKE_CXX_COMPILER=cl'
python -m pip install -e ".[dev,visualization]"
```

- Install Python dev dependencies before running tests:

```bash
python -m pip install -e ".[dev]"
```

- To enable the `sphinxsim preview` visualizer, install the optional PyVista dependency:

```bash
python -m pip install -e ".[visualization]"
```

  See [Visualization](visualization.md) for details.

- Run full Python tests (including examples):

```bash
python -m pytest tests/ examples/ -v
```
