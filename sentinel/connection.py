"""
Cognee bootstrap using Groq for reasoning and local Ollama for embeddings.

IMPORTANT: import this module *before* importing cognee. Importing it runs
``load_dotenv()`` and pins the env vars Cognee reads at import time
(e.g. ENABLE_BACKEND_ACCESS_CONTROL, which sets the single-user/local posture).

    from sentinel.connection import setup_cognee   # loads .env first
    import cognee
    ...
    await setup_cognee()
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env into the process environment as early as possible — Cognee reads
# several of these at import time, so this must run before `import cognee`.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Non-secret defaults; a Groq key must still come from the environment or .env.
_DEFAULTS = {
    "ENABLE_BACKEND_ACCESS_CONTROL": "false",  # local single-user; no multi-tenant auth
    "TELEMETRY_DISABLED": "1",
    "CACHING": "false",  # disable session-memory cache so forget shows in recall immediately
    # Cognee routes this LiteLLM-prefixed model to Groq. Groq needs no endpoint.
    "LLM_PROVIDER": "custom",
    "LLM_MODEL": "groq/llama-3.3-70b-versatile",
    "EMBEDDING_PROVIDER": "ollama",
    "EMBEDDING_MODEL": "nomic-embed-text",
    "EMBEDDING_ENDPOINT": "http://localhost:11434/api/embed",
    "EMBEDDING_DIMENSIONS": "768",
    "HUGGINGFACE_TOKENIZER": "nomic-ai/nomic-embed-text-v1.5",
}
for _k, _v in _DEFAULTS.items():
    os.environ.setdefault(_k, _v)

# Cognee validates the LLM env at IMPORT time (cognee.shared.rate_limiting builds
# LLMConfig on import, before setup_cognee() runs) and requires LLM_API_KEY to be
# present and non-empty whenever LLM_MODEL/LLM_ENDPOINT are set — even for Ollama. The
# GitHub Action passes an empty LLM_API_KEY in local mode, so inject a placeholder here
# (this module is imported before `import cognee`). Real keys (Groq) are left untouched.
if os.environ.get("LLM_PROVIDER") == "ollama" and not os.environ.get("LLM_API_KEY"):
    os.environ["LLM_API_KEY"] = "ollama"


async def setup_cognee() -> None:
    """Apply the LLM + Ollama-embeddings config and fail fast on missing dependencies.

    Two LLM postures, selected by LLM_PROVIDER:
      - ``ollama``  — fully local reasoning (no API key needed); the on-prem/self-hosted
        posture. A dummy LLM_API_KEY ("ollama") satisfies the client.
      - anything else (e.g. ``custom`` for Groq) — needs a real key in LLM_API_KEY/GROQ_API_KEY.
    """
    import cognee

    provider = os.environ["LLM_PROVIDER"]
    if provider == "ollama":
        api_key = (os.environ.get("LLM_API_KEY") or "ollama").strip()
    else:
        api_key = (os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError(
                f"LLM API key is missing for provider '{provider}'. "
                "Set GROQ_API_KEY (or LLM_API_KEY), or use LLM_PROVIDER=ollama for local reasoning."
            )

    cognee.config.set_llm_provider(provider)
    cognee.config.set_llm_model(os.environ["LLM_MODEL"])
    if os.environ.get("LLM_ENDPOINT"):
        cognee.config.set_llm_endpoint(os.environ["LLM_ENDPOINT"])
    cognee.config.set_llm_api_key(api_key)

    cognee.config.set_embedding_provider(os.environ["EMBEDDING_PROVIDER"])
    cognee.config.set_embedding_model(os.environ["EMBEDDING_MODEL"])
    cognee.config.set_embedding_endpoint(os.environ["EMBEDDING_ENDPOINT"])
    cognee.config.set_embedding_dimensions(int(os.environ["EMBEDDING_DIMENSIONS"]))

    _assert_embedding_service_running()


def _assert_embedding_service_running() -> None:
    """Check local Ollama when it is the configured embedding provider."""
    if os.environ["EMBEDDING_PROVIDER"] != "ollama":
        return

    import urllib.error
    import urllib.parse
    import urllib.request

    endpoint = urllib.parse.urlsplit(os.environ["EMBEDDING_ENDPOINT"])
    ollama_host = f"{endpoint.scheme}://{endpoint.netloc}"
    try:
        urllib.request.urlopen(f"{ollama_host}/api/tags", timeout=3)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"Ollama embeddings are not reachable at {ollama_host}.\n"
            f"  Start it:   ollama serve\n"
            f"  Pull model: ollama pull {os.environ['EMBEDDING_MODEL']}\n"
            f"Original error: {exc}"
        ) from exc
