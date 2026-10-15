"""Explicit DeepSeek HTTP boundary. No credentials, network, or retries by default."""

from dataclasses import dataclass
import json
import math
import urllib.error
import urllib.request

from .protocol import strict_json


class ProviderError(Exception):
    """Sanitized protocol or transport failure; never contains HTTP response bodies."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeepSeekHTTP:
    """A trusted application must explicitly authorize network use and supply a key.

    Only the official endpoint is supported. HKGAI needs its issued specification.
    Timeout is a socket-operation timeout, not an end-to-end task deadline.
    """

    endpoint = "https://api.deepseek.com/chat/completions"
    max_bytes = 2 * 1024 * 1024

    def __init__(self, api_key, *, allow_network=False, timeout=30):
        if not isinstance(api_key, str) or not api_key.strip() or any(c.isspace() for c in api_key):
            raise ProviderError("Supply a nonempty API key without whitespace")
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 120):
            raise ProviderError("Socket timeout must be between zero and 120 seconds")
        if type(allow_network) is not bool:
            raise ProviderError("Network authorization must be explicit")
        self._api_key = api_key
        self._allowed = allow_network
        self.timeout = timeout

    def __call__(self, payload):
        if not self._allowed:
            raise ProviderError("Network disabled; live calls require an authorized budget")
        if not isinstance(payload, bytes) or len(payload) > self.max_bytes:
            raise ProviderError("Invalid or oversized request")
        request = urllib.request.Request(
            self.endpoint, data=payload, method="POST",
            headers={"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"},
        )
        # No redirects or automatic retries: an interrupted POST may have been charged.
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                if response.status != 200 or response.geturl() != self.endpoint:
                    raise ProviderError("Unexpected provider HTTP response")
                data = response.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise ProviderError("Provider response exceeds byte limit")
            return data
        except urllib.error.HTTPError as error:
            error.close()
            raise ProviderError(f"Provider HTTP status {error.code}; no automatic retry") from None
        except (OSError, urllib.error.URLError, ValueError):
            raise ProviderError("Provider transport failed; reconcile before retrying") from None


@dataclass(frozen=True)
class Completion:
    message: dict
    finish_reason: str
    usage: dict
    response_id: str
    model: str


class DeepSeekClient:
    """Non-streaming tool protocol, with a caller-supplied transport and model ID.

    Injected transports are for explicit offline tests, never benchmark fallback.
    A final assistant message is a proposal, not trusted completion evidence.
    """

    def __init__(self, model, transport, *, max_tokens=2048):
        if not isinstance(model, str) or not model.strip() or len(model) > 128:
            raise ProviderError("An explicit course-approved model identifier is required")
        if not callable(transport) or type(max_tokens) is not int or not 1 <= max_tokens <= 16384:
            raise ProviderError("Supply a transport and a bounded output token limit")
        self.model = model
        self.transport = transport
        self.max_tokens = max_tokens

    def complete(self, messages, *, tools=()):
        if not isinstance(messages, list) or not messages:
            raise ProviderError("Supply a nonempty trusted conversation")
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "max_tokens": self.max_tokens, "thinking": {"type": "disabled"}}
        if tools:
            payload.update(tools=list(tools), tool_choice="auto")
        try:
            encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ProviderError("Request is not valid JSON") from None
        if len(encoded) > DeepSeekHTTP.max_bytes:
            raise ProviderError("Request exceeds byte limit")
        raw = self.transport(encoded)
        if not isinstance(raw, bytes) or len(raw) > DeepSeekHTTP.max_bytes:
            raise ProviderError("Invalid or oversized provider response")
        try:
            data = strict_json(raw)
            choices = data["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError()
            choice = choices[0]
            reason, source = choice["finish_reason"], choice["message"]
            if reason not in {"stop", "tool_calls"} or source["role"] != "assistant":
                raise ValueError()
            message = {"role": "assistant", "content": source.get("content")}
            if message["content"] is not None and not isinstance(message["content"], str):
                raise ValueError()
            if "reasoning_content" in source:
                if source["reasoning_content"] is not None and not isinstance(source["reasoning_content"], str):
                    raise ValueError()
                message["reasoning_content"] = source["reasoning_content"]
            calls = source.get("tool_calls")
            if calls is None:
                calls = []
            if not isinstance(calls, list) or len(calls) > 16:
                raise ValueError()
            identifiers = set()
            for call in calls:
                if (not isinstance(call, dict) or set(call) != {"id", "type", "function"}
                        or not isinstance(call["id"], str) or not 1 <= len(call["id"]) <= 128
                        or call["id"] in identifiers or call["type"] != "function"
                        or not isinstance(call["function"], dict)
                        or set(call["function"]) != {"name", "arguments"}
                        or not isinstance(call["function"]["name"], str)
                        or not isinstance(call["function"]["arguments"], str)):
                    raise ValueError()
                identifiers.add(call["id"])
            if bool(calls) != (reason == "tool_calls"):
                raise ValueError()
            if calls:
                message["tool_calls"] = calls
            elif not isinstance(message["content"], str) or not message["content"].strip():
                raise ValueError()
            usage = data["usage"]
            counts = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
            if any(type(value) is not int or value < 0 for value in counts.values()):
                raise ValueError()
            if any(not isinstance(data[key], str) or not data[key] for key in ("id", "model")):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            raise ProviderError("Invalid, incomplete, or unsupported provider completion; no tools released") from None
        return Completion(message, reason, counts, data["id"], data["model"])
