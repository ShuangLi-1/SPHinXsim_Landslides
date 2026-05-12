"""sphinxsim.llm – LLM helpers (mock and production)."""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinxsim.llm.mock_llm import MockLLM
    from sphinxsim.llm.ollama_llm import OllamaLLM
    from sphinxsim.llm.openai_llm import OpenAILLM

def get_llm():
    provider = os.getenv("SPHINXSIM_LLM_PROVIDER", "mock")

    if provider == "openai":
        from sphinxsim.llm.openai_llm import OpenAILLM

        return OpenAILLM(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    
    if provider == "ollama":
        from sphinxsim.llm.ollama_llm import OllamaLLM
        return OllamaLLM(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        )
        
    from sphinxsim.llm.mock_llm import MockLLM

    return MockLLM()

__all__ = ["MockLLM", "OpenAILLM", "OllamaLLM", "get_llm"]


def __getattr__(name):
    if name == "MockLLM":
        from sphinxsim.llm.mock_llm import MockLLM

        return MockLLM
    
    if name == "OpenAILLM":
        from sphinxsim.llm.openai_llm import OpenAILLM

        return OpenAILLM
    
    if name == "OllamaLLM":
        from sphinxsim.llm.ollama_llm import OllamaLLM

        return OllamaLLM


    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
