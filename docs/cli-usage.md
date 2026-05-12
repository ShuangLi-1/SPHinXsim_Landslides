# CLI Usage Guide

SPHinXsim provides a command-line interface for building, validating, updating, and running SPH simulations. This guide covers all available commands and workflows.

## Quick start

### Interactive shell mode (recommended)

The easiest way to get started is the interactive shell:

```bash
sphinxsim shell
```

This opens an interactive prompt where you can enter commands sequentially:

```
> generate "water dam break simulation"
✓ Config generated and saved to config.json
✓ Schema validation passed

> validate
Configuration: WaterBody (fluid) + WallBoundary (solid)
  Domain: [0, 0] to [5.37, 5.37]
  Resolution: 0.025 m
  End time: 0.5 s
  Gravity: [0, -1] m/s²

> update "simulate for 2 s"
✓ Config updated and saved to config.json
✓ Schema validation passed

> validate
Configuration: WaterBody (fluid) + WallBoundary (solid)
  Domain: [0, 0] to [5.37, 5.37]
  Resolution: 0.025 m
  End time: 2.0 s
  Gravity: [0, -1] m/s²

> run
Building simulation...
Running SPH simulation...
Output saved to: build-integrated/output

> exit
Goodbye!
```

### Shell with custom config file

```bash
sphinxsim shell --config my_simulation.json
```

### Shell commands

Inside the shell, you can use the following commands:

| Command | Description |
| --- | --- |
| `generate "description"` | Generate a new config from natural language description |
| `update "instruction"` | Modify the current config with an instruction (e.g., "change end time to 5 s") |
| `validate` | Display the current config structure and validate it |
| `run` | Build and execute the validated simulation |
| `help` | Show available commands |
| `exit` | Quit the shell |

## Direct commands (non-interactive)

You can also run individual commands directly:

### Generate

Create a new simulation config from a natural language description:

```bash
sphinxsim generate --description "2D water dam break with 0.5 m/s initial velocity" --output config.json
```

This:
1. Sends your description to the LLM provider (mock by default, or Ollama if configured)
2. Receives a JSON config in response
3. Validates the config against strict schemas
4. Saves the result to `config.json`
5. Prints a summary

### Validate

Check an existing config without modifying it:

```bash
sphinxsim validate --config config.json
```

This displays:
- Simulation type (fluid_dynamics, continuum_dynamics, or coupled)
- List of bodies and their material types
- Domain bounds and resolution
- Solver parameters (end time, output interval, etc.)
- Any validation errors

### Update

Modify an existing config with natural language instructions:

```bash
sphinxsim update --config config.json --description "increase end time to 10 s" --output config_updated.json
```

This:
1. Loads the existing config
2. Sends it to the LLM provider along with your instruction
3. Receives a modified JSON config
4. Validates the updated config
5. Saves the result to `config_updated.json`

### Run

Execute a validated simulation:

```bash
sphinxsim run --config config.json
```

This:
1. Validates the config
2. Builds SPHinXsys simulation components in C++
3. Runs the simulation
4. Saves output to `build-integrated/output`

## Workflow examples

### Example 1: Quick iteration with the shell

```bash
sphinxsim shell
> generate "2D water dam break, domain 5m x 5m, resolution 2.5cm"
> validate
> run
> exit
```

### Example 2: Compare two configurations

```bash
sphinxsim generate --description "water dam break" --output config_v1.json
sphinxsim validate --config config_v1.json

sphinxsim generate --description "water dam break with faster gravity" --output config_v2.json
sphinxsim validate --config config_v2.json

# Then run the version you prefer:
sphinxsim run --config config_v1.json
```

### Example 3: Fine-tune a config without regenerating

```bash
sphinxsim shell --config config.json
> validate
> update "change particle spacing to 1 cm"
> validate
> run
```

### Example 4: Batch process with direct commands

```bash
for desc in "water dam break" "sloshing tank" "wave propagation"; do
  sphinxsim generate --description "$desc" --output "config_$desc.json"
  sphinxsim validate --config "config_$desc.json"
done
```

## LLM provider selection

By default, `sphinxsim` uses a local mock LLM that works offline. To use a different provider:

### Use Ollama (local LLM inference)

```bash
export SPHINXSIM_LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:3b
sphinxsim generate --description "water dam break"
```

First, ensure Ollama is running:
```bash
ollama serve
# In another terminal:
ollama pull qwen2.5:3b
```

### Use OpenAI

```bash
export SPHINXSIM_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4
sphinxsim generate --description "water dam break"
```

### Use mock (default)

```bash
export SPHINXSIM_LLM_PROVIDER=mock
sphinxsim generate --description "water dam break"
```

## Output locations

- **Generated configs**: Saved to the path specified by `--output` (default: `config.json`)
- **Simulation output**: Saved to `build-integrated/output/`
- **Temporary files**: Stored in `.build-temp/`

## Error handling

If config generation or validation fails:

1. **Generation fails**: The LLM response did not match the expected JSON schema. Check the error message for details, or try rephrasing your description.
2. **Validation fails**: The config violates a schema constraint (e.g., body type mismatch). Use `sphinxsim validate` to see which field is invalid.
3. **Execution fails**: The config is valid but the simulation failed. Check simulation output in `build-integrated/output/`.

## See also

- [LLM Testing](llm-testing.md) for local testing with mock and Ollama
- [Schema reference](index.md#current-capabilities) for supported simulation types and materials
