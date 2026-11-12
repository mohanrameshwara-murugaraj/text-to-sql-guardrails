"""Optional local Ollama adapter. Candidate SQL is NEVER executed here.

No third-party client package is needed: Ollama exposes a local HTTP API.
Only run a trusted local Ollama instance. API responses are untrusted input.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelResponseError(ValueError):
    """The local model did not supply a valid structured candidate."""


@dataclass(frozen=True)
class SQLCandidate:
    sql: str | None
    explanation: str
    referenced_tables: tuple[str, ...]


def parse_candidate(text: str) -> SQLCandidate:
    """Strictly parse the LLM's JSON payload; do not trust its claims."""
    try:
        obj = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ModelResponseError("Model did not return valid JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"sql", "explanation", "referenced_tables"}:
        raise ModelResponseError("Expected exactly sql, explanation, referenced_tables")
    sql, explanation, tables = obj["sql"], obj["explanation"], obj["referenced_tables"]
    if sql is not None and (not isinstance(sql, str) or not sql.strip()):
        raise ModelResponseError("sql must be a nonempty string or null")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ModelResponseError("explanation must be a nonempty string")
    if not isinstance(tables, list) or not all(isinstance(t, str) and t for t in tables):
        raise ModelResponseError("referenced_tables must be a string list")
    if len(set(tables)) != len(tables):
        raise ModelResponseError("Duplicate referenced tables")
    return SQLCandidate(sql=sql, explanation=explanation, referenced_tables=tuple(tables))


def generate_candidate(
    prompt: str,
    *,
    model: str = "qwen2.5-coder:3b",
    endpoint: str = "http://127.0.0.1:11434/api/generate",
    timeout_s: int = 90,
    transport: Callable[[Request, int], bytes] | None = None,
) -> SQLCandidate:
    """Ask locally running Ollama for JSON. Timeout limits HTTP waiting, not SQL."""
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("Only loopback Ollama endpoints are supported")
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "format": {"type": "object", "properties": {
            "sql": {"type": ["string", "null"]},
            "explanation": {"type": "string"},
            "referenced_tables": {"type": "array", "items": {"type": "string"}},
        }, "required": ["sql", "explanation", "referenced_tables"], "additionalProperties": False},
        "options": {"temperature": 0},
    }).encode("utf-8")
    request = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    def _default_transport(req: Request, timeout: int) -> bytes:
        with urlopen(req, timeout=timeout) as response:
            return response.read(2_000_000)
    try:
        raw = (transport or _default_transport)(request, timeout_s)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ModelResponseError("Could not contact local Ollama; is it running and is the model installed?") from exc
    try:
        envelope: Any = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ModelResponseError("Ollama returned an invalid HTTP JSON body") from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("response"), str):
        raise ModelResponseError("Ollama response is missing the text field")
    return parse_candidate(envelope["response"])
