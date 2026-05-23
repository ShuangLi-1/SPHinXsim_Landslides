# macOS Installation (macOS 13)

## Prerequisites

Install system tools:

```bash
brew update
brew install ninja autoconf automake autoconf-archive pkg-config
```

## Clone Repository

```bash
git clone --recurse-submodules https://github.com/<your-org>/SPHinXsim.git
cd SPHinXsim
```

If already cloned without submodules:

```bash
git submodule update --init --recursive
```

## Install vcpkg

```bash
git clone https://github.com/microsoft/vcpkg.git ../vcpkg
../vcpkg/bootstrap-vcpkg.sh
```

## Install C/C++ Dependencies

```bash
../vcpkg/vcpkg install --clean-after-build openblas[dynamic-arch] --allow-unsupported
../vcpkg/vcpkg install --clean-after-build \
  eigen3 \
  tbb \
  boost-program-options \
  boost-geometry \
  simbody \
  spdlog \
  gtest \
  pybind11 \
  vtk \
  nlohmann-json
```

## Configure and Build

```bash
cmake --preset integrated-build-release \
  -D CMAKE_TOOLCHAIN_FILE="$(pwd)/../vcpkg/scripts/buildsystems/vcpkg.cmake" \
  -D Python3_EXECUTABLE="$(which python3)"
cmake --build --preset integrated-build-release --parallel "$(sysctl -n hw.logicalcpu)"
```

## Run Tests

Install Python package with dev dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run Python tests:

```bash
python -m pytest tests/ examples/ -v
```

Run C++ simulation tests:

```bash
ctest --test-dir build-integrated --output-on-failure -R "test_(2d|3d)_simulation$"
```
