# Linux Installation (Ubuntu 22.04)

## Prerequisites

Install system packages:

```bash
sudo apt-get update
sudo apt-get install -y \
  apt-utils \
  build-essential \
  curl zip unzip tar \
  pkg-config git \
  ninja-build \
  autoconf automake autoconf-archive \
  libxmu-dev libxi-dev libgl-dev libxt-dev \
  libvtk9-dev
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
  nlohmann-json
```

## Configure and Build

```bash
cmake --preset integrated-build-release \
  -D CMAKE_TOOLCHAIN_FILE="$(pwd)/../vcpkg/scripts/buildsystems/vcpkg.cmake" \
  -D Python3_EXECUTABLE="$(which python3)"
cmake --build --preset integrated-build-release --parallel "$(nproc)"
```

## Run Tests

Install Python package with dev dependencies:

```bash
python -m pip install -e ".[dev]"
```

To enable geometry preview (`sphinxsim preview`), also install:

```bash
python -m pip install -e ".[visualization]"
```

Run Python tests:

```bash
python -m pytest tests/ examples/ -v
```

Run C++ simulation tests:

```bash
ctest --test-dir build-integrated --output-on-failure -R "test_(2d|3d)_simulation$"
```
