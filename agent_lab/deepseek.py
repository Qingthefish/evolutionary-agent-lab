"""Explicit DeepSeek HTTP boundary. No credentials, network, or retries by default."""

from dataclasses import dataclass
import http.client
import json
import math
import socket
import ssl
import time
import urllib.error
import urllib.request

from .protocol import strict_json


# Fixed labels for a rejected completion: which structural rule refused it and
# three bounded observations. Never a response value, tool argument or message text.
PARSE_RULES = ("not_json", "missing_field", "choice_count", "finish_reason", "role", "content_type",
               "reasoning_type", "tool_call_shape", "tool_call_limit", "duplicate_tool_call_id",
               "finish_reason_mismatch", "required_tool_missing", "empty_text", "usage", "identity", "other")
FINISH_REASON_LABELS = ("stop", "tool_calls", "length", "content_filter", "function_call")


def _finish_label(value):
    if not isinstance(value, str):
        return "invalid"
    return value if value in FINISH_REASON_LABELS else "other"


def _valid_completion_check(check):
    return (isinstance(check, dict) and set(check) == {"parse_rule", "finish_reason", "tool_calls", "content_present"}
            and isinstance(check["parse_rule"], str) and check["parse_rule"] in PARSE_RULES
            and (check["finish_reason"] is None or (isinstance(check["finish_reason"], str)
                 and check["finish_reason"] in (*FINISH_REASON_LABELS, "other", "invalid")))
            and (check["tool_calls"] is None or (type(check["tool_calls"]) is int
                 and 0 <= check["tool_calls"] <= DeepSeekHTTP.max_bytes))
            and (check["content_present"] is None or type(check["content_present"]) is bool))


class ProviderError(Exception):
    """Sanitized protocol or transport failure; never contains HTTP response bodies."""

    def __init__(self, message, *, kind="provider_error", phase="unknown", request_bytes=None,
                 response_bytes=None, duration_seconds=None, http_status=None,
                 request_may_have_been_processed=True, completion_check=None):
        kinds = {"provider_error", "network_disabled", "invalid_request", "http_status", "unexpected_response",
                 "oversized_response", "timeout", "dns", "tls", "connection_closed", "connection_refused",
                 "http_protocol", "transport", "invalid_completion"}
        phases = {"unknown", "preflight", "opening", "reading", "parsing"}
        if (not isinstance(kind, str) or kind not in kinds or not isinstance(phase, str) or phase not in phases
                or any(v is not None and (type(v) is not int or v < 0) for v in (request_bytes, response_bytes))
                or (duration_seconds is not None and (type(duration_seconds) not in (int, float)
                    or not math.isfinite(duration_seconds) or duration_seconds < 0))
                or (http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599))
                or type(request_may_have_been_processed) is not bool
                or (completion_check is not None and (kind != "invalid_completion"
                    or not _valid_completion_check(completion_check)))):
            raise ValueError("Invalid bounded provider diagnostic")
        super().__init__(message)
        self._diagnostic = {"kind": kind, "phase": phase, "request_bytes": request_bytes,
            "response_bytes": response_bytes, "duration_seconds": duration_seconds, "http_status": http_status,
            "request_may_have_been_processed": request_may_have_been_processed, "automatic_retry": False}
        if completion_check is not None:
            self._diagnostic["completion_check"] = dict(completion_check)

    def diagnostics(self):
        """A data-only copy; no raw reason, URL, header, body or credential."""
        return {key: dict(value) if isinstance(value, dict) else value for key, value in self._diagnostic.items()}


def _transport_kind(error):
    # URLError.reason may be an exception OR an arbitrary string. Never log it.
    for _ in range(3):
        if isinstance(error, urllib.error.URLError) and isinstance(error.reason, BaseException):
            error = error.reason
        else:
            break
    if isinstance(error, TimeoutError): return "timeout"
    if isinstance(error, socket.gaierror): return "dns"
    if isinstance(error, ssl.SSLError): return "tls"
    if isinstance(error, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
                          http.client.RemoteDisconnected)): return "connection_closed"
    if isinstance(error, ConnectionRefusedError): return "connection_refused"
    if isinstance(error, http.client.HTTPException): return "http_protocol"
    return "transport"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeepSeekHTTP:
    """A trusted application must explicitly authorize network use and supply a key.

    Only the official endpoint is supported; HKGAI uses a separate fixed-host subclass.
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
            raise ProviderError("Network disabled; live calls require an authorized budget", kind="network_disabled",
                                phase="preflight", request_may_have_been_processed=False)
        if not isinstance(payload, bytes) or len(payload) > self.max_bytes:
            raise ProviderError("Invalid or oversized request", kind="invalid_request", phase="preflight",
                                request_may_have_been_processed=False)
        request = urllib.request.Request(
            self.endpoint, data=payload, method="POST",
            headers={"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"},
        )
        # No redirects or automatic retries: an interrupted POST may have been charged.
        started = time.monotonic()
        phase, response_bytes, status = "opening", None, None

        def failure(message, kind):
            return ProviderError(message, kind=kind, phase=phase, request_bytes=len(payload),
                response_bytes=response_bytes, duration_seconds=max(0, time.monotonic()-started), http_status=status)

        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                status = response.status if type(response.status) is int and 100 <= response.status <= 599 else None
                if response.status != 200 or response.geturl() != self.endpoint:
                    raise failure("Unexpected provider HTTP response", "unexpected_response")
                phase = "reading"
                data = response.read(self.max_bytes + 1)
                response_bytes = len(data)
            if len(data) > self.max_bytes:
                raise failure("Provider response exceeds byte limit", "oversized_response")
            return data
        except urllib.error.HTTPError as error:
            status = error.code if type(error.code) is int and 100 <= error.code <= 599 else None
            error.close()
            raise failure(f"Provider HTTP status {status}; no automatic retry", "http_status") from None
        except (OSError, urllib.error.URLError, ValueError, http.client.HTTPException) as error:
            if isinstance(error, http.client.IncompleteRead): response_bytes = len(error.partial)
            raise failure("Provider transport failed; reconcile before retrying", _transport_kind(error)) from None


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

    request_options = {"thinking": {"type": "disabled"}}

    def __init__(self, model, transport, *, max_tokens=2048, tool_choice="auto"):
        if not isinstance(model, str) or not model.strip() or len(model) > 128:
            raise ProviderError("An explicit course-approved model identifier is required")
        if not callable(transport) or type(max_tokens) is not int or not 1 <= max_tokens <= 16384:
            raise ProviderError("Supply a transport and a bounded output token limit")
        if not isinstance(tool_choice, str) or tool_choice not in {"auto", "required"}:
            raise ProviderError("Use explicit auto or required tool selection")
        self.model = model
        self.transport = transport
        self.max_tokens = max_tokens
        self.tool_choice = tool_choice

    def complete(self, messages, *, tools=()):
        if not isinstance(messages, list) or not messages:
            raise ProviderError("Supply a nonempty trusted conversation")
        if self.tool_choice == "required" and not tools:
            raise ProviderError("Required tool selection needs actual tools", kind="invalid_request",
                                phase="preflight", request_may_have_been_processed=False)
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "max_tokens": self.max_tokens, **self.request_options}
        if tools:
            payload.update(tools=list(tools), tool_choice=self.tool_choice)
        try:
            encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ProviderError("Request is not valid JSON") from None
        if len(encoded) > DeepSeekHTTP.max_bytes:
            raise ProviderError("Request exceeds byte limit")
        raw = self.transport(encoded)
        if not isinstance(raw, bytes) or len(raw) > DeepSeekHTTP.max_bytes:
            raise ProviderError("Invalid or oversized provider response")
        # Each rejection path sets its fixed label first, so an unexpected
        # shape is classified by the rule being checked. Accepted completions
        # and the single sanitized error are unchanged.
        check = {"parse_rule": "other", "finish_reason": None, "tool_calls": None, "content_present": None}
        try:
            check["parse_rule"] = "not_json"
            data = strict_json(raw)
            check["parse_rule"] = "missing_field"
            choices = data["choices"]
            check["parse_rule"] = "choice_count"
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError()
            check["parse_rule"] = "missing_field"
            choice = choices[0]
            reason, source = choice["finish_reason"], choice["message"]
            check["finish_reason"] = _finish_label(reason)
            role, content = source["role"], source.get("content")
            check["parse_rule"] = "finish_reason"
            if not isinstance(reason, str) or reason not in {"stop", "tool_calls"}:
                raise ValueError()
            check["parse_rule"] = "role"
            if role != "assistant":
                raise ValueError()
            check["parse_rule"] = "content_type"
            message = {"role": "assistant", "content": content}
            if content is not None and not isinstance(content, str):
                raise ValueError()
            check["content_present"] = bool(content and content.strip())
            check["parse_rule"] = "reasoning_type"
            if "reasoning_content" in source:
                if source["reasoning_content"] is not None and not isinstance(source["reasoning_content"], str):
                    raise ValueError()
                message["reasoning_content"] = source["reasoning_content"]
            check["parse_rule"] = "tool_call_shape"
            calls = source.get("tool_calls")
            if calls is None:
                calls = []
            if not isinstance(calls, list):
                raise ValueError()
            check["tool_calls"] = len(calls)
            check["parse_rule"] = "tool_call_limit"
            if len(calls) > 16:
                raise ValueError()
            identifiers = set()
            for call in calls:
                check["parse_rule"] = "tool_call_shape"
                if (not isinstance(call, dict) or set(call) != {"id", "type", "function"}
                        or not isinstance(call["id"], str) or not 1 <= len(call["id"]) <= 128
                        or call["type"] != "function"
                        or not isinstance(call["function"], dict)
                        or set(call["function"]) != {"name", "arguments"}
                        or not isinstance(call["function"]["name"], str)
                        or not isinstance(call["function"]["arguments"], str)):
                    raise ValueError()
                check["parse_rule"] = "duplicate_tool_call_id"
                if call["id"] in identifiers:
                    raise ValueError()
                identifiers.add(call["id"])
            check["parse_rule"] = "finish_reason_mismatch"
            if bool(calls) != (reason == "tool_calls"):
                raise ValueError()
            check["parse_rule"] = "required_tool_missing"
            if self.tool_choice == "required" and not calls:
                raise ValueError()
            check["parse_rule"] = "empty_text"
            if calls:
                message["tool_calls"] = calls
            elif not isinstance(message["content"], str) or not message["content"].strip():
                raise ValueError()
            check["parse_rule"] = "usage"
            usage = data["usage"]
            counts = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
            if any(type(value) is not int or value < 0 for value in counts.values()):
                raise ValueError()
            if counts["total_tokens"] != counts["prompt_tokens"] + counts["completion_tokens"]:
                raise ValueError()
            check["parse_rule"] = "identity"
            if any(not isinstance(data[key], str) or not data[key] for key in ("id", "model")):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            raise ProviderError("Invalid, incomplete, or unsupported provider completion; no tools released",
                kind="invalid_completion", phase="parsing", request_bytes=len(encoded), response_bytes=len(raw),
                completion_check=check) from None
        return Completion(message, reason, counts, data["id"], data["model"])
