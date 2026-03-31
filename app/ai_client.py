"""
ai_client.py — Provider-agnostic AI abstraction layer.

Default provider: Ollama (runs locally — NO API key needed).
Switch providers by changing "provider" in config.json only.

Supported providers:
  - ollama    → Local Ollama (default, free, no key)
  - openai    → OpenAI GPT-4o etc. (needs OPENAI_API_KEY)
  - anthropic → Anthropic Claude (needs ANTHROPIC_API_KEY)
  - stub      → Offline testing/development (no key, canned responses)
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class AIClientBase(ABC):
    """All AI provider implementations extend this."""

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        """Send a prompt, return text response."""
        ...

    def complete_json(self, prompt: str, system: Optional[str] = None) -> dict:
        """Like complete(), but parses and returns JSON. Strips markdown fences."""
        raw     = self.complete(prompt, system=system)
        cleaned = _strip_code_fences(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse AI response as JSON:\n%s", raw)
            raise ValueError(
                f"AI response was not valid JSON: {e}\n\nRaw response:\n{raw}"
            ) from e


# ---------------------------------------------------------------------------
# Ollama — LOCAL, no API key required (DEFAULT)
# ---------------------------------------------------------------------------

class OllamaClient(AIClientBase):
    """
    Calls a locally running Ollama instance.
    Install Ollama: https://ollama.com
    Pull a model:   ollama pull llama3
    Then run:       ollama serve
    """

    def __init__(self):
        try:
            import requests
            self._requests = requests
        except ImportError:
            raise ImportError("requests not installed. Run: pip install requests")

        provider_cfg   = settings.providers.get("ollama", {})
        self._base_url = provider_cfg.get("base_url", "http://localhost:11434/api")
        self._model    = settings.ai.model
        self._timeout  = settings.ai.timeout_seconds

        logger.info(
            "OllamaClient ready → %s  model=%s", self._base_url, self._model
        )

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        payload = {
            "model":  self._model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": settings.ai.temperature,
                "num_predict": settings.ai.max_tokens,
            },
        }

        if settings.logging.show_ai_prompts:
            logger.debug("→ Ollama prompt (first 200 chars):\n%s", full_prompt[:200])

        try:
            resp = self._requests.post(
                f"{self._base_url}/generate",
                json    = payload,
                timeout = self._timeout,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
            if settings.logging.show_ai_prompts:
                logger.debug("← Ollama response (first 200):\n%s", text[:200])
            return text
        except self._requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Cannot connect to Ollama at %s.\n"
                "Make sure Ollama is running: ollama serve\n"
                "And you have pulled the model: ollama pull %s"
                % (self._base_url, self._model)
            )
        except self._requests.exceptions.Timeout:
            raise RuntimeError(
                f"Ollama request timed out after {self._timeout}s. "
                "Try increasing timeout_seconds in config.json."
            )
        except self._requests.RequestException as e:
            raise RuntimeError(f"Ollama API error: {e}") from e


# ---------------------------------------------------------------------------
# OpenAI (optional — only if you have an API key)
# ---------------------------------------------------------------------------

class OpenAIClient(AIClientBase):
    """OpenAI Chat Completions. Requires OPENAI_API_KEY env variable."""

    def __init__(self):
        try:
            import openai
            self._openai = openai
        except ImportError:
            raise ImportError("Run: pip install openai")

        api_key = settings.ai.api_key
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable is not set.\n"
                "Either set it, or switch provider to 'ollama' in config.json."
            )
        self._client = openai.OpenAI(api_key=api_key, timeout=settings.ai.timeout_seconds)

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model       = settings.ai.model,
                messages    = messages,
                temperature = settings.ai.temperature,
                max_tokens  = settings.ai.max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except self._openai.OpenAIError as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e


# ---------------------------------------------------------------------------
# Anthropic (optional — only if you have an API key)
# ---------------------------------------------------------------------------

class AnthropicClient(AIClientBase):
    """Anthropic Claude models. Requires ANTHROPIC_API_KEY env variable."""

    def __init__(self):
        try:
            import anthropic
            self._anthropic = anthropic
        except ImportError:
            raise ImportError("Run: pip install anthropic")

        api_key = settings.ai.api_key
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY environment variable is not set.\n"
                "Either set it, or switch provider to 'ollama' in config.json."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        kwargs: dict = {
            "model":      settings.ai.model,
            "max_tokens": settings.ai.max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(**kwargs)
            return (response.content[0].text if response.content else "").strip()
        except self._anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e


# ---------------------------------------------------------------------------
# Stub — offline testing, no AI required
# ---------------------------------------------------------------------------

class StubAIClient(AIClientBase):
    """
    Deterministic canned responses for offline development and testing.
    Set provider to 'stub' in config.json to activate.
    """

    _STUBS = [
        (
            ["problem_statement", "analyse the following product idea"],
            '{"problem_statement":"stub problem","features":["feature A","feature B","feature C"],'
            '"target_users":["developer"],"constraints":[],"tech_stack":["Python","FastAPI"]}',
        ),
        (
            ["task list", "break the following product", "development task list", "json array of up to"],
            '[{"title":"Setup project","description":"Initialize repo and install dependencies",'
            '"priority":"high","dependencies":[]},{"title":"Build core feature",'
            '"description":"Implement the main business logic","priority":"high",'
            '"dependencies":["Setup project"]}]',
        ),
        (
            ["json array of relative file paths", "list the files that need"],
            '["main.py", "utils/helpers.py"]',
        ),
        (
            ["root_cause", "debug the following error"],
            '{"root_cause":"NameError: variable not defined","fix_description":'
            '"Add variable declaration before use","patched_code":"x = 0\\nprint(x)",'
            '"confidence":"high"}',
        ),
        (
            ["refactored_code", "refactor the following"],
            '{"refactored_code":"# Refactored\\ndef main():\\n    x = 0\\n    print(x)\\n\\nmain()",'
            '"changes_made":["Added docstring","Wrapped in function"]}',
        ),
    ]

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        prompt_lower = prompt.lower()
        for keywords, stub in self._STUBS:
            if any(kw in prompt_lower for kw in keywords):
                return stub
        if "write the complete contents" in prompt_lower or "file content" in prompt_lower:
            return 'print("Hello from Claude CTO!")\n'
        return '{"result": "stub response"}'


# ---------------------------------------------------------------------------
# Factory — single public entry point
# ---------------------------------------------------------------------------

_client_cache: Optional[AIClientBase] = None


def get_ai_client() -> AIClientBase:
    """Return a singleton AI client based on config.json provider setting."""
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    provider = settings.ai.provider.lower()
    logger.info(
        "Initializing AI client: provider=%s  model=%s", provider, settings.ai.model
    )

    if provider == "ollama":
        _client_cache = OllamaClient()
    elif provider == "openai":
        _client_cache = OpenAIClient()
    elif provider == "anthropic":
        _client_cache = AnthropicClient()
    elif provider == "stub":
        _client_cache = StubAIClient()
    else:
        raise ValueError(
            f"Unknown AI provider: '{provider}'. "
            "Valid options: ollama, openai, anthropic, stub"
        )

    return _client_cache


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    """Remove ```json...``` or ```...``` wrappers from model output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text  = "\n".join(lines).strip()
    return text
