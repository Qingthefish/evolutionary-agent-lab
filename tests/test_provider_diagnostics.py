"""Sanitized failures and actual loopback HTTP faults; no real model calls."""
from contextlib import contextmanager
import http.client
import io
import json
from pathlib import Path
import socket
import socketserver
import ssl
import tempfile
import threading
import unittest
from unittest.mock import MagicMock,patch
import urllib.error
import urllib.request

from agent_lab import Workflow,WorkflowError
from agent_lab.deepseek import ProviderError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.hkgai import HKGAIClient,HKGAIHTTP
from agent_lab.runner import TaskRunner

SENTINEL='synthetic-private-sentinel'
REPLY=json.dumps({'id':'loopback-response','model':'synthetic-loopback','choices':[
    {'finish_reason':'stop','message':{'role':'assistant','content':'Synthetic local response'}}],
    'usage':{'prompt_tokens':4,'completion_tokens':1,'total_tokens':5}}).encode()


@contextmanager
def loopback(mode):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            stream=self.request.makefile('rb');size=0
            while True:
                line=stream.readline()
                if line in (b'\r\n',b'\n',b''):break
                if line.lower().startswith(b'content-length:'):size=int(line.split(b':',1)[1])
            stream.read(size);server.calls+=1
            try:
                if mode=='malformed':self.request.sendall(('not-http '+SENTINEL+'\r\n\r\n').encode());return
                if mode=='close':return
                if mode=='chunk':self.request.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n7\r\nxx');return
                if mode=='slow_headers':server.release.wait(1)
                status='401 Unauthorized' if mode=='rejected' else '200 OK'
                body=SENTINEL.encode() if mode=='rejected' else REPLY
                self.request.sendall(f'HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode())
                if mode=='slow_body':server.release.wait(1)
                self.request.sendall(body)
            except (BrokenPipeError,ConnectionResetError):pass
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads=True
    server=Server(('127.0.0.1',0),Handler);server.calls=0;server.release=threading.Event()
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);thread.start()
    original=urllib.request.build_opener
    def local_opener(*handlers):
        # Test-only direct localhost route; production endpoint/routing stays fixed.
        return original(urllib.request.ProxyHandler({}),*handlers)
    try:
        with patch.object(HKGAIHTTP,'endpoint',f'http://127.0.0.1:{server.server_address[1]}/completion'), \
             patch('urllib.request.build_opener',local_opener):yield server
    finally:
        server.release.set();server.shutdown();server.server_close();thread.join()


class ProviderDiagnosticTests(unittest.TestCase):
    def test_local_valid_response_preserves_usage_and_model(self):
        with loopback('valid') as server:
            client=HKGAIClient('synthetic-loopback',HKGAIHTTP('fake-local-key',allow_network=True,timeout=1))
            result=client.complete([{'role':'user','content':'Local check'}])
            self.assertEqual(result.model,'synthetic-loopback');self.assertEqual(result.usage['total_tokens'],5)
            self.assertEqual(server.calls,1)

    def test_actual_malformed_http_is_sanitized_not_an_escaping_exception(self):
        with loopback('malformed') as server,self.assertRaises(ProviderError) as caught:
            HKGAIHTTP('fake-local-key',allow_network=True,timeout=1)(b'{}')
        record=caught.exception.diagnostics()
        self.assertEqual((record['kind'],record['phase']),('http_protocol','opening'))
        self.assertEqual(server.calls,1);self.assertNotIn(SENTINEL,str(caught.exception)+json.dumps(record))
        self.assertTrue(record['request_may_have_been_processed']);self.assertFalse(record['automatic_retry'])

    def test_actual_connection_close_and_incomplete_chunk_are_distinct(self):
        for mode,kind,phase in [('close','connection_closed','opening'),('chunk','http_protocol','reading')]:
            with self.subTest(mode=mode),loopback(mode) as server,self.assertRaises(ProviderError) as caught:
                HKGAIHTTP('fake-local-key',allow_network=True,timeout=1)(b'{}')
            record=caught.exception.diagnostics()
            self.assertEqual((record['kind'],record['phase']),(kind,phase));self.assertEqual(server.calls,1)
            if mode=='chunk':self.assertEqual(record['http_status'],200);self.assertIsNotNone(record['response_bytes'])

    def test_actual_timeout_records_header_wait_versus_body_read_without_retry(self):
        for mode,phase in [('slow_headers','opening'),('slow_body','reading')]:
            with self.subTest(mode=mode),loopback(mode) as server,self.assertRaises(ProviderError) as caught:
                HKGAIHTTP('fake-local-key',allow_network=True,timeout=0.1)(b'{}')
            record=caught.exception.diagnostics()
            self.assertEqual((record['kind'],record['phase']),('timeout',phase));self.assertEqual(server.calls,1)
            self.assertGreaterEqual(record['duration_seconds'],0)
            self.assertEqual(record['request_bytes'],2);self.assertIsNone(record['response_bytes'])

    def test_actual_http_rejection_never_exposes_response_body(self):
        with loopback('rejected') as server,self.assertRaises(ProviderError) as caught:
            HKGAIHTTP('fake-local-key',allow_network=True,timeout=1)(b'{}')
        record=caught.exception.diagnostics()
        self.assertEqual((record['kind'],record['http_status']),('http_status',401));self.assertEqual(server.calls,1)
        self.assertNotIn(SENTINEL,str(caught.exception)+json.dumps(record));self.assertIsNone(record['response_bytes'])

    def test_oversized_response_has_bounded_byte_evidence(self):
        with loopback('valid') as server,patch.object(HKGAIHTTP,'max_bytes',128),self.assertRaises(ProviderError) as caught:
            HKGAIHTTP('fake-local-key',allow_network=True,timeout=1)(b'{}')
        record=caught.exception.diagnostics()
        self.assertEqual(record['kind'],'oversized_response');self.assertEqual(record['response_bytes'],129)
        self.assertEqual(server.calls,1)

    def test_dns_tls_and_wrapped_reasons_are_classified_without_logging_raw_details(self):
        cases=[(urllib.error.URLError(socket.gaierror(socket.EAI_NONAME,SENTINEL)),'dns'),
            (urllib.error.URLError(ssl.SSLError(SENTINEL)),'tls'),
            (urllib.error.URLError(TimeoutError(SENTINEL)),'timeout'),
            (ConnectionRefusedError(SENTINEL),'connection_refused'),
            (urllib.error.URLError(SENTINEL),'transport'),(http.client.BadStatusLine(SENTINEL),'http_protocol')]
        for error,expected in cases:
            with self.subTest(kind=expected),patch('urllib.request.build_opener') as build:
                build.return_value.open.side_effect=error
                with self.assertRaises(ProviderError) as caught:HKGAIHTTP('fake-local-key',allow_network=True)(b'{}')
                record=caught.exception.diagnostics();self.assertEqual(record['kind'],expected)
                self.assertNotIn(SENTINEL,str(caught.exception)+json.dumps(record))
                self.assertEqual(build.return_value.open.call_count,1)

    def test_network_disabled_and_malformed_completion_have_different_evidence(self):
        with patch('urllib.request.build_opener') as build,self.assertRaises(ProviderError) as caught:
            HKGAIHTTP('fake-local-key')(b'{}')
        record=caught.exception.diagnostics();build.assert_not_called()
        self.assertEqual(record['phase'],'preflight');self.assertFalse(record['request_may_have_been_processed'])
        with self.assertRaises(ProviderError) as malformed:
            HKGAIClient('synthetic',lambda _:b'not JSON').complete([{'role':'user','content':'test'}])
        self.assertEqual((malformed.exception.diagnostics()['kind'],malformed.exception.diagnostics()['phase']),('invalid_completion','parsing'))
        copy=record;copy['kind']='changed';self.assertEqual(caught.exception.diagnostics()['kind'],'network_disabled')

    def test_actual_protocol_error_stops_runner_and_persists_private_failure_evidence(self):
        with tempfile.TemporaryDirectory() as temp,loopback('malformed') as server:
            path=Path(temp)/'state.sqlite3';workflow=Workflow(path)
            workflow.register_actor('human','human');workflow.register_actor('writer','agent')
            chat=workflow.create_chat('private',['human','writer']);task=workflow.create_task(chat,'human','writer','Local fault')
            workflow.start_task(task,'writer');files=FileTools(workflow,Path(temp)/'files')
            gateway=ToolGateway(workflow,files,task,'writer',human='human',allowed=['create_text'])
            runner=TaskRunner(gateway,HKGAIClient('synthetic',HKGAIHTTP('fake-local-key',allow_network=True,timeout=1)),mode='live',constraints=[])
            runner.step()
            self.assertEqual(workflow.task(task,'human')['state'],'failed')
            self.assertEqual(workflow.db.execute('SELECT status FROM runner_sessions').fetchone()[0],'stopped')
            with patch.object(HKGAIHTTP,'__call__',side_effect=AssertionError('Do not retry terminal failure')):runner.run()
            self.assertEqual(server.calls,1);files.close();workflow.close()
            reopened=Workflow(path)
            try:
                rows=[e for e in reopened.events(task,'human') if e['kind']=='provider_request_failed']
                self.assertEqual(len(rows),1);detail=json.loads(rows[0]['detail'])
                self.assertEqual(detail['number'],1);self.assertEqual(detail['diagnostics']['kind'],'http_protocol')
                self.assertNotIn(SENTINEL,json.dumps(detail))
                reopened.register_actor('outsider','human')
                with self.assertRaises(WorkflowError):reopened.events(task,'outsider')
            finally:reopened.close()


if __name__=='__main__':unittest.main()
