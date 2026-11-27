"""Opt-in streamed replies rebuilt into the same strict completion (proposed 2026-11-23).

Live rehearsal, 2026-11-23: two non-streaming HKGAI requests ended with HTTP 504 at
about 124 s while the model was still generating (27-44 tokens/s). A streamed
8,192-token request completed in 139 s with its first chunk after 3.3 s. The
streamed body is assembled and passed through the unchanged strict parser.
Loopback HTTP and scripted events only; no real model calls.
"""
from contextlib import contextmanager
import json
import socketserver
import threading
import unittest
from unittest.mock import patch
import urllib.request

from agent_lab.deepseek import (DeepSeekClient, ProviderError, StreamAssemblyError, TruncatedCompletion,
                                assemble_stream)
from agent_lab.hkgai import HKGAIClient, HKGAIHTTP
from agent_lab.runtime import LiveConfig, RuntimeSetupError, live_clients

SECRET = "synthetic-private-stream"


def event(**fields):
    return "data: " + json.dumps({"id": "s1", "model": "synthetic", **fields})


def delta(finish=None, **values):
    return event(choices=[{"index": 0, "delta": values, "finish_reason": finish}])


TOOL_STREAM = [
    delta(role="assistant", reasoning="think "), delta(reasoning="more"),
    delta(tool_calls=[{"index": 0, "id": "c0", "type": "function", "function": {"name": "create_text", "arguments": ""}}]),
    delta(tool_calls=[{"index": 0, "function": {"arguments": '{"path": "a.py", '}}]),
    delta(tool_calls=[{"index": 0, "function": {"arguments": '"content": "x"}'}}]),
    delta(tool_calls=[{"index": 1, "id": "c1", "type": "function", "function": {"name": "read_text",
                                                                                  "arguments": '{"path": "b"}'}}]),
    delta(finish="tool_calls"),
    event(choices=[], usage={"prompt_tokens": 7, "completion_tokens": 30, "total_tokens": 37,
                             "completion_tokens_details": {"reasoning_tokens": 12}}),
    "data: [DONE]",
]


def client_for(lines):
    return HKGAIClient("synthetic", lambda payload: assemble_stream(iter(lines), max_bytes=1 << 20))


class AssemblyTests(unittest.TestCase):
    def test_tool_call_fragments_reasoning_and_usage_become_one_strict_completion(self):
        result = client_for(TOOL_STREAM).complete([{"role": "user", "content": "hi"}],
                                                  tools=[{"type": "function", "function": {"name": "x"}}])
        self.assertEqual(result.finish_reason, "tool_calls")
        self.assertEqual([c["function"]["name"] for c in result.message["tool_calls"]], ["create_text", "read_text"])
        self.assertEqual(json.loads(result.message["tool_calls"][0]["function"]["arguments"]),
                         {"path": "a.py", "content": "x"})
        self.assertEqual(result.usage, {"prompt_tokens": 7, "completion_tokens": 30, "total_tokens": 37})
        self.assertEqual(result.reasoning_tokens, 12)
        self.assertNotIn("reasoning", result.message)  # Hidden text is not echoed back.

    def test_streamed_length_cutoff_keeps_the_existing_truncation_path(self):
        lines = [delta(role="assistant", reasoning="r" * 500), delta(finish="length"),
                 event(choices=[], usage={"prompt_tokens": 7, "completion_tokens": 8192, "total_tokens": 8199,
                                          "completion_tokens_details": {"reasoning_tokens": 8192}}), "data: [DONE]"]
        with self.assertRaises(TruncatedCompletion) as caught:
            client_for(lines).complete([{"role": "user", "content": "hi"}])
        self.assertEqual((caught.exception.shape["reasoning_chars"], caught.exception.shape["reasoning_tokens"]),
                         (500, 8192))
        self.assertEqual(caught.exception.usage["completion_tokens"], 8192)

    def test_incomplete_or_invalid_streams_release_no_tools(self):
        # An interrupted envelope is refused before parsing; a completed stream
        # missing usage is still refused by the unchanged strict completion parser.
        with self.assertRaises(StreamAssemblyError):
            client_for([delta(role="assistant", content="partial")]).complete([{"role":"user","content":"hi"}])
        with self.assertRaises(ProviderError) as caught:
            client_for([delta(role="assistant", content="ok"), delta(finish="stop"), "data: [DONE]"]).complete(
                [{"role":"user","content":"hi"}])
        self.assertEqual(caught.exception.diagnostics()["kind"], "invalid_completion")
        for lines in (["data: {not json"], ['data: {"error": {"message": "%s"}}' % SECRET],
                      [delta(tool_calls=[{"function": {"name": "x"}}])],
                      [event(choices=[{"delta": {}}, {"delta": {}}])]):
            with self.assertRaises(ValueError):
                assemble_stream(iter(lines), max_bytes=1 << 20)
        with self.assertRaises(StreamAssemblyError):
            assemble_stream(iter([delta(content="x" * 50)]), max_bytes=10)


@contextmanager
def sse_server(lines, *, pause=0.0):
    seen = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            stream = self.request.makefile("rb"); size = 0
            while True:
                line = stream.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                if line.lower().startswith(b"content-length:"):
                    size = int(line.split(b":", 1)[1])
            seen.append(json.loads(stream.read(size)))
            self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n")
            for line in lines:
                self.request.sendall((line + "\n\n").encode())
                if pause:
                    threading.Event().wait(pause)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    original = urllib.request.build_opener

    def local_opener(*handlers):  # Test-only direct localhost route; production routing stays fixed.
        return original(urllib.request.ProxyHandler({}), *handlers)
    try:
        with patch.object(HKGAIHTTP, "endpoint", f"http://127.0.0.1:{server.server_address[1]}/completion"), \
             patch("urllib.request.build_opener", local_opener):
            yield seen
    finally:
        server.shutdown(); server.server_close(); thread.join()


class LoopbackTransportTests(unittest.TestCase):
    def test_actual_http_stream_is_requested_assembled_and_parsed(self):
        with sse_server(TOOL_STREAM, pause=0.02) as seen:
            transport = HKGAIHTTP("synthetic-key", allow_network=True, timeout=2, stream=True)
            result = HKGAIClient("synthetic", transport).complete(
                [{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "x"}}])
        self.assertTrue(seen[0]["stream"])
        self.assertEqual(seen[0]["stream_options"], {"include_usage": True})
        self.assertNotIn("thinking", seen[0])  # Thinking stays on; only delivery changes.
        self.assertEqual(len(result.message["tool_calls"]), 2)

    def test_total_duration_may_exceed_the_socket_timeout_while_chunks_keep_arriving(self):
        lines = [delta(role="assistant")] + [delta(content="x") for _ in range(12)] + [
            delta(finish="stop"), event(choices=[], usage={"prompt_tokens": 1, "completion_tokens": 12,
                                                           "total_tokens": 13}), "data: [DONE]"]
        with sse_server(lines, pause=0.1):
            transport = HKGAIHTTP("synthetic-key", allow_network=True, timeout=0.5, stream=True)
            result = HKGAIClient("synthetic", transport).complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result.message["content"], "x" * 12)  # About 1.5 s total with a 0.5 s socket timeout.

    def test_a_stream_error_event_is_a_sanitized_provider_failure(self):
        with sse_server(['data: {"error": {"message": "%s"}}' % SECRET]):
            transport = HKGAIHTTP("synthetic-key", allow_network=True, timeout=2, stream=True)
            with self.assertRaises(ProviderError) as caught:
                HKGAIClient("synthetic", transport).complete([{"role": "user", "content": "hi"}])
        diagnostics = caught.exception.diagnostics()
        self.assertEqual((diagnostics["kind"], diagnostics["phase"]), ("invalid_stream", "reading"))
        self.assertTrue(diagnostics["request_may_have_been_processed"])
        self.assertNotIn(SECRET, json.dumps(diagnostics))
        from agent_lab.runner import operator_decision_failure
        self.assertTrue(operator_decision_failure(diagnostics))  # Only the operator may resend; never automatic.


class ConfigurationTests(unittest.TestCase):
    def test_streaming_is_off_by_default_and_must_be_explicit(self):
        base = dict(model="m", api_key="k", provider="hkgai")
        self.assertFalse(LiveConfig(**base).stream_responses)
        self.assertFalse(next(iter(live_clients(LiveConfig(**base), ["a"]).values())).transport.stream)
        self.assertTrue(next(iter(live_clients(LiveConfig(**base, stream_responses=True), ["a"]).values()))
                        .transport.stream)
        with self.assertRaises(RuntimeSetupError):
            LiveConfig(**base, stream_responses="yes")
        with self.assertRaises(ProviderError):
            HKGAIHTTP("k", stream=1)
        self.assertFalse(DeepSeekClient("m", HKGAIHTTP("k")).transport.stream)


if __name__ == "__main__":
    unittest.main()
