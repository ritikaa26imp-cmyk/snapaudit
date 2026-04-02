"""
Talk to the local Ollama HTTP API.

This module is the **only** place that should open HTTP connections to Ollama.
The ``/api/chat`` endpoint accepts a ``model`` id (e.g. ``qwen2.5vl:7b``),
OpenAI-style ``messages``, and optional per-message ``images`` as raw base64
strings—matching what the official Ollama CLI and REST docs describe.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, TypedDict

import httpx
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class OllamaRuntimeConfig(TypedDict):
    """Subset of ``config.yaml`` needed to reach the running Ollama daemon."""

    active_model: str
    ollama_base_url: str


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.yaml"


def load_config() -> OllamaRuntimeConfig:
    """
    Read ``config.yaml`` and return the active vision tag plus API base URL.

    ``active_model`` must match an Ollama model name (``ollama list``), e.g.
    ``qwen2.5vl:7b``, ``gemma3:4b``, or ``llava:7b``.
    """
    path = _config_path()
    with path.open("rb") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config at {path} must parse to a mapping")

    model = str(data.get("active_model", "")).strip()
    base = str(data.get("ollama_base_url", "http://localhost:11434")).strip()
    if not model:
        raise ValueError("config.yaml must set active_model")

    return OllamaRuntimeConfig(active_model=model, ollama_base_url=base.rstrip("/"))


def get_active_model() -> str:
    """Return ``active_model`` from ``config.yaml`` (same source as :func:`load_config`)."""
    return load_config()["active_model"]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OllamaError(Exception):
    """Non-success interaction with Ollama (HTTP layer or transport)."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class JSONParseError(Exception):
    """Model output could not be parsed as JSON after fence stripping."""

    def __init__(self, raw_response: str) -> None:
        self.raw_response = raw_response
        super().__init__("failed to parse JSON from model response")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\r?\n?(.*?)\r?\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def parse_json_response(response: str) -> dict[str, Any]:
    """
    Parse JSON from a model reply.

    Vision models often wrap JSON in Markdown fences; we strip `` ```json ``
    blocks when present, then :func:`json.loads`. Raises :class:`JSONParseError`
    with the original string attached if parsing still fails.
    """
    raw = response
    text = response.strip()
    segments: list[str] = [text]
    fence = _FENCE_RE.match(text)
    if fence:
        segments.append(fence.group(1).strip())

    last_error: Exception | None = None
    for segment in segments:
        try:
            parsed = json.loads(segment)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        last_error = ValueError("top-level JSON value is not an object")
    raise JSONParseError(raw) from last_error


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------


class OllamaClient:
    """
    Thin async wrapper around ``POST {base}/api/chat``.

    Ollama expects:

    - ``model``: string tag pulled from config (works for any vision-capable tag).
    - ``messages``: ``system`` + ``user`` turns; images ride on the **user**
      message as parallel base64 blobs (no ``data:`` prefix).
    - ``stream``: ``false`` to receive a single JSON object (no NDJSON stream).
    """

    def __init__(self) -> None:
        cfg = load_config()
        self.model: str = cfg["active_model"]
        self.base_url: str = cfg["ollama_base_url"]

    async def chat(self, prompt: str, images: list[str]) -> str:
        """
        Run one non-streaming chat completion with a system prompt and images.

        ``images`` must already be base64-encoded strings (as produced by the
        preprocessor). They are sent in the ``images`` array on the **user**
        message, which is how Ollama wires multimodal inputs for vision models.
        """
        url = f"{self.base_url}/api/chat"
        # System holds the instructions; user turn carries pixels for vision models.
        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]
        if images:
            messages.append(
                {
                    "role": "user",
                    "content": "Follow the system instructions and respond in JSON only.",
                    "images": images,
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": "Follow the system instructions and respond in JSON only.",
                }
            )

        payload = {"model": self.model, "messages": messages, "stream": False}

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
                response = await client.post(url, json=payload)
        except httpx.RequestError as exc:
            raise OllamaError(f"connection to Ollama failed: {exc}", status_code=0) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("ollama chat model=%s latency_ms=%s", self.model, elapsed_ms)

        if response.status_code != 200:
            body = response.text[:2000]
            raise OllamaError(
                f"Ollama returned HTTP {response.status_code}: {body}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise OllamaError(
                f"Ollama returned non-JSON body: {response.text[:500]}",
                status_code=response.status_code,
            ) from exc

        message = data.get("message") if isinstance(data, dict) else None
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content

        raise OllamaError(
            f"unexpected Ollama response shape: {json.dumps(data)[:500]}",
            status_code=response.status_code,
        )
