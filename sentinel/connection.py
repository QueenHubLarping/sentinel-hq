"""
Local self-hosted Cognee + Ollama bootstrap. NO Cognee Cloud, NO external API —
the LLM and embeddings both run on a local Ollama instance, so nothing leaves
the laptop.

IMPORTANT: import this module *before* importing cognee. Importing it runs
``load_dotenv()`` and pins the env vars Cognee reads at import time
(e.g. ENABLE_BACKEND_ACCESS_CONTROL, which sets the single-user/local posture).

    from sentinel.connection import setup_cognee   # loads .env first
    import cognee
    ...
    await setup_cognee()
"""

import os
from dotenv import load_dotenv

# Load .env into the process environment as early as possible — Cognee reads
# several of these at import time, so this must run before `import cognee`.
load_dotenv()

# Safe local defaults so the project runs even without a .env file.
_DEFAULTS = {
    "ENABLE_BACKEND_ACCESS_CONTROL": "false",  # local single-user; no multi-tenant auth
    "TELEMETRY_DISABLED": "1",
    "CACHING": "false",  # disable session-memory cache so forget shows in recall immediately
    "LLM_PROVIDER": "ollama",
    "LLM_MODEL": "qwen2.5:3b",
    # Native structured-output mode: forces a valid JSON *instance*. Without this,
    # small local models echo the JSON *schema* and cognify fails validation.
    "LLM_INSTRUCTOR_MODE": "json_schema_mode",
    "LLM_ENDPOINT": "http://localhost:11434/v1",
    "LLM_API_KEY": "ollama",
    "EMBEDDING_PROVIDER": "ollama",
    "EMBEDDING_MODEL": "nomic-embed-text",
    "EMBEDDING_ENDPOINT": "http://localhost:11434/api/embed",
    "EMBEDDING_DIMENSIONS": "768",
    "HUGGINGFACE_TOKENIZER": "nomic-ai/nomic-embed-text-v1.5",
}
for _k, _v in _DEFAULTS.items():
    os.environ.setdefault(_k, _v)

# Base host (strip the OpenAI-compat "/v1" suffix) for the health check.
OLLAMA_HOST = os.environ["LLM_ENDPOINT"].split("/v1")[0]


async def setup_cognee() -> None:
    """Apply the local Ollama config to Cognee and fail fast if Ollama is down."""
    import cognee

    cognee.config.set_llm_provider(os.environ["LLM_PROVIDER"])
    cognee.config.set_llm_model(os.environ["LLM_MODEL"])
    cognee.config.set_llm_endpoint(os.environ["LLM_ENDPOINT"])
    cognee.config.set_llm_api_key(os.environ["LLM_API_KEY"])

    cognee.config.set_embedding_provider(os.environ["EMBEDDING_PROVIDER"])
    cognee.config.set_embedding_model(os.environ["EMBEDDING_MODEL"])
    cognee.config.set_embedding_endpoint(os.environ["EMBEDDING_ENDPOINT"])
    cognee.config.set_embedding_dimensions(int(os.environ["EMBEDDING_DIMENSIONS"]))

    _assert_ollama_running()


def _assert_ollama_running() -> None:
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"Ollama is not reachable at {OLLAMA_HOST}.\n"
            f"  Start it:   ollama serve\n"
            f"  Pull models: ollama pull {os.environ['LLM_MODEL']} && "
            f"ollama pull {os.environ['EMBEDDING_MODEL']}\n"
            f"Original error: {exc}"
        ) from exc
