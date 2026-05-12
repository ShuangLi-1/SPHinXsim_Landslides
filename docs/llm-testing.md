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
source setup-local-env.sh
pytest tests/test_ollama_llm.py -v
pytest tests/test_ollama_llm_integration.py -v
pytest examples/test_nlp_to_simulation.py -v
```

## How CI behaves

CI runs the mocked tests everywhere and skips the live Ollama cases automatically. This keeps the pipeline stable while still validating the example workflow and the Ollama adapter logic that does not require a live server.
