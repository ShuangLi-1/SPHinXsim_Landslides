# LLM Testing

This project uses two distinct LLM test paths so local development can exercise both a mock backend and a live Ollama backend, while CI stays fully deterministic.

## Test matrix

| Test area | Local | CI |
| --- | --- | --- |
| `tests/test_ollama_llm.py` | Mocked only | Mocked only |
| `tests/test_ollama_llm_integration.py` | Live Ollama when available, otherwise skipped | Skipped |
| `examples/test_nlp_to_simulation.py` | Mocked case plus live Ollama case when available | Mocked case only, live Ollama skipped |

## Environment variables

Local development typically uses [setup-local-env.sh](../setup-local-env.sh) to set:

- `SPHINXSIM_LLM_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://localhost:11434`
- `OLLAMA_MODEL=qwen2.5:3b`

CI sets `SPHINXSIM_LLM_PROVIDER=mock` so the workflow never depends on an external API or a running Ollama server.

## How to run locally

To exercise the mock and Ollama paths locally:

```bash
# Test with mock LLM (no Ollama needed)
pytest tests/test_ollama_llm.py -v

# Test with live Ollama (requires Ollama running locally)
pytest tests/test_ollama_llm_integration.py -v

# Run end-to-end example with both mock and Ollama
pytest examples/test_nlp_to_simulation.py -v

# Or use the interactive shell with Ollama
source setup-local-env.sh
sphinxsim shell
# Then issue commands like: generate "...", update "...", validate, run
```

## How CI behaves

CI runs the mocked tests everywhere and skips the live Ollama cases automatically. This keeps the pipeline stable while still validating the example workflow and the Ollama adapter logic that does not require a live server.

## Interactive shell with Ollama

For interactive development, use the shell mode with Ollama:

```bash
source setup-local-env.sh  # Sets SPHINXSIM_LLM_PROVIDER=ollama and other vars
sphinxsim shell
```

Inside the shell, you can generate and update configs using the live Ollama backend:

```
> generate "2D water dam break simulation"
✓ Config generated and saved to config.json
✓ Schema validation passed

> validate
Configuration: WaterBody (fluid) + WallBoundary (solid)
  Domain: [0, 0] to [5.37, 5.37]
  Resolution: 0.025 m
  End time: 0.5 s

> update "increase end time to 2 seconds"
✓ Config updated and saved to config.json
✓ Schema validation passed

> run
Building simulation...
Running SPH simulation...
```

See [CLI Usage](cli-usage.md) for full shell command reference.
