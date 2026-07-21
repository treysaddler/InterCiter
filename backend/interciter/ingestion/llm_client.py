"""Chat clients for LLM extraction — one code path, many backends.

The extractor is model- and endpoint-agnostic. Anything that speaks the OpenAI
``/chat/completions`` shape works: the NIEHS **LiteLLM proxy** (frontier + lesser
models) and a **Biowulf**-hosted server (e.g. vLLM) are both reached by
:class:`OpenAICompatibleClient`. Biowulf can also run *offline*: export the prompts,
run them on the cluster, and replay the responses through :class:`BatchResponseClient`
so extraction is identical whether the model ran live or in a batch job.

A request is content-addressed (:func:`request_id`) so batch responses map back to the
right prompt regardless of ingestion order.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from ..config import Settings
from ..net import RETRY_STATUSES, retry_delay, ssl_context


class LLMError(RuntimeError):
    """Raised on a transport/endpoint failure (distinct from malformed model output)."""


def request_id(model: str, template_version: str, passage_index: int, text: str) -> str:
    """Stable id for a prompt, addressed by model + template + passage content."""
    digest = hashlib.sha256(
        f"{template_version}\x00{model}\x00{text}".encode("utf-8")
    ).hexdigest()[:16]
    return f"p{passage_index}_{digest}"


@dataclass
class ExtractionRequest:
    request_id: str
    passage_index: int
    model: str
    system: str
    user: str
    temperature: float
    max_tokens: int

    def to_json_line(self) -> str:
        """Serialize as one JSONL row for an offline batch runner (e.g. vLLM)."""
        return json.dumps(
            {
                "request_id": self.request_id,
                "model": self.model,
                "passage_index": self.passage_index,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": self.system},
                    {"role": "user", "content": self.user},
                ],
            }
        )


class ChatClient(Protocol):
    """Returns a raw completion string for a request, or ``None`` to abstain."""

    def complete(self, request: ExtractionRequest) -> str | None: ...


class OpenAICompatibleClient:
    """Live client for any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: int = 120,
        request_json_object: bool = True,
    ) -> None:
        if not base_url:
            raise LLMError("llm_base_url is not configured")
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._json_object = request_json_object

    def complete(self, request: ExtractionRequest) -> str | None:
        payload: dict = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if self._json_object:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "interciter (+https://github.com/treysaddler/InterCiter)",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            f"{self._base}/chat/completions", data=data, headers=headers, method="POST"
        )
        attempts = 5
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(
                    req, timeout=self._timeout, context=ssl_context()
                ) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt < attempts - 1:
                    time.sleep(retry_delay(attempt, exc.headers.get("Retry-After")))
                    continue
                raise LLMError(f"HTTP {exc.code} from LLM endpoint: {exc.reason}") from exc
            except Exception as exc:  # noqa: BLE001
                raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            body = json.loads(raw.decode("utf-8", errors="replace"))
            return body["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise LLMError(f"unexpected LLM response shape: {exc}") from exc


class BatchResponseClient:
    """Replays completions from an offline batch run, keyed by ``request_id``."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses

    def complete(self, request: ExtractionRequest) -> str | None:
        return self._responses.get(request.request_id)


def client_from_settings(settings: Settings) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        settings.llm_base_url, settings.llm_api_key, timeout=settings.llm_timeout
    )


def load_batch_responses(path: str) -> dict[str, str]:
    """Load an offline batch response file into ``{request_id: completion}``.

    Accepts our own ``{"request_id","completion"}`` rows as well as OpenAI-style rows
    carrying ``choices[0].message.content`` (directly or under a ``response`` object).
    """
    responses: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rid = obj.get("request_id") or obj.get("custom_id")
            if not rid:
                continue
            completion = _extract_completion(obj)
            if completion is not None:
                responses[rid] = completion
    return responses


def _extract_completion(obj: dict) -> str | None:
    if isinstance(obj.get("completion"), str):
        return obj["completion"]
    body = obj.get("response", obj)
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
