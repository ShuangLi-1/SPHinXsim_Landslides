"""Helpers for locating and importing compiled SPHinXsim C++ extensions."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType


_DLL_HANDLES: list[object] = []


def _iter_existing_dirs(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    existing: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if path.is_dir() and resolved not in seen:
            existing.append(path)
            seen.add(resolved)
    return existing


def _candidate_search_dirs() -> list[Path]:
    bindings_dir = Path(__file__).resolve().parent
    package_root = bindings_dir.parent
    repo_root = package_root.parent

    build_roots = [
        repo_root / "build-integrated",
        repo_root / "build-integrated-debug",
    ]

    candidates: list[Path] = [bindings_dir / "native"]
    for build_root in build_roots:
        candidates.append(build_root)
        candidates.append(build_root / "Release")
        candidates.append(build_root / "RelWithDebInfo")
        candidates.append(build_root / "Debug")
    return _iter_existing_dirs(candidates)


def _configure_windows_loader() -> None:
    if os.name != "nt":
        return
    if not hasattr(os, "add_dll_directory"):
        return

    for path in _candidate_search_dirs():
        try:
            _DLL_HANDLES.append(os.add_dll_directory(str(path)))
        except (FileNotFoundError, OSError):
            continue


def _configure_module_search_path() -> None:
    for path in _candidate_search_dirs():
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def load_sphinxsys_core() -> ModuleType:
    """Load and return the SPHinXsim C++ extension module.

    Tries both 2-D and 3-D extension names, and both top-level and package
    qualified import paths.
    """
    _configure_windows_loader()
    _configure_module_search_path()

    module_names = [
        "_sphinxsys_core_2d",
        "_sphinxsys_core_3d",
        "sphinxsim.bindings.native._sphinxsys_core_2d",
        "sphinxsim.bindings.native._sphinxsys_core_3d",
    ]

    errors: list[str] = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")

    searched_dirs = ", ".join(str(p) for p in _candidate_search_dirs())
    details = "\n  - ".join(errors)
    raise ImportError(
        "C++ extension not found (_sphinxsys_core_2d / _sphinxsys_core_3d).\n"
        "Build and install the compiled sphinxsim package to use this command.\n"
        f"Searched directories: {searched_dirs}\n"
        f"Import errors:\n  - {details}"
    )
