# Windows Installation (VS 2022)

## Prerequisites

Install:

- Visual Studio 2022 (Desktop development with C++)
- CMake
- Ninja
- Git
- Python 3.11

Use x64 Native Tools Command Prompt for VS 2022 or Developer PowerShell.

## Clone Repository

```powershell
git clone --recurse-submodules https://github.com/<your-org>/SPHinXsim.git
cd SPHinXsim
```

If already cloned without submodules:

```powershell
git submodule update --init --recursive
```

## Install vcpkg

```powershell
git clone https://github.com/microsoft/vcpkg.git ..\vcpkg
..\vcpkg\bootstrap-vcpkg.bat
```

## Install C/C++ Dependencies

```powershell
..\vcpkg\vcpkg.exe install --clean-after-build openblas[dynamic-arch] --allow-unsupported
..\vcpkg\vcpkg.exe install --clean-after-build `
  eigen3 `
  tbb `
  boost-program-options `
  boost-geometry `
  simbody `
  spdlog `
  gtest `
  pybind11 `
  vtk `
  nlohmann-json
```

## Configure and Build

```powershell
cmake --preset integrated-build-release-windows `
  -D CMAKE_TOOLCHAIN_FILE="$pwd\..\vcpkg\scripts\buildsystems\vcpkg.cmake" `
  -D Python3_EXECUTABLE="$(python -c "import sys; print(sys.executable)")"
cmake --build --preset integrated-build-release-windows --parallel
```

## Run Tests

Install Python package with dev dependencies:

```powershell
python -m pip install -e ".[dev]"
```

To enable geometry preview (`sphinxsim preview`), also install:

```powershell
python -m pip install -e ".[visualization]"
```

Run Python tests:

```powershell
python -m pytest tests/ examples/ -v
```

Run C++ simulation tests:

```powershell
ctest --test-dir build-integrated --output-on-failure -R "test_(2d|3d)_simulation$"
```

## Notes

- If `cl` is not found, reopen a Visual Studio developer shell and rerun configure.
- If CMake cache gets inconsistent, remove `build-integrated` and reconfigure.
