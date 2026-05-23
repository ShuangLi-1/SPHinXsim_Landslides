# Installation Guide

Choose your platform-specific setup guide:

- [Linux Installation](installation-linux.md)
- [Windows Installation](installation-windows.md)
- [macOS Installation](installation-macos.md)

## Shared Notes

- Use CMake presets from the repository root.
- Keep vcpkg outside the repository folder (for example, `../vcpkg`).
- Install Python dev dependencies before running tests:

```bash
python -m pip install -e ".[dev]"
```

- Run full Python tests (including examples):

```bash
python -m pytest tests/ examples/ -v
```
