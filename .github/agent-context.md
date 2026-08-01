# Agent Context Preferences

This file is repository-tracked context for Copilot/agent behavior and can be updated over time.

## Python Environment Preference

- Prefer system Python (`python3`).
- Avoid virtual environments unless explicitly requested.

## Testing Preferences

- Default schema test command: `python3 -m pytest tests/test_schemas.py -q`.
- Prefer targeted tests first, then broader test runs on request.

## Documentation Preferences

- Keep docs aligned with CLI behavior whenever command flags or workflows change.
- Prefer concise, practical examples that can be copied directly.

## Workflow Preferences

- Use repository-tracked preference updates in this file for long-term changes.
- Keep persistent memory entries short and consistent with this file.

## Notes

- Persistent cross-session memory is managed separately under `/memories/`.
- Keep this file in sync with user preferences you want versioned in the repository.
