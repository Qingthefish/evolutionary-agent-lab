"""Public-network boundaries and actual broker handoff, without external calls."""

import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.retrieval import PublicHTTPS, RetrievalError, RetrievalLimits, WebRetrieval, plain_text, public_url
from test_runner import tool

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]


class Reply:
    def __init__(self, body=b'<p>Evidence</p>', status=200, **headers):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = {'Content-Type': 'text/html', **headers}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        return self.body.read(size)


class Connection:
    def __init__(self, reply):
        self.reply, self.sock, self.calls, self.closed = reply, None, [], False

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def getresponse(self):
        return self.reply

    def close(self):
        self.closed = True


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.workflow = Workflow(self.path/'state.sqlite3')
        for actor, kind in (('user','human'),('researcher','agent'),('writer','agent')):
            self.workflow.register_actor(actor,kind)
        self.chat = self.workflow.create_chat('group',['user','researcher','writer'])
        self.task = self.workflow.create_task(self.chat,'user','researcher','Retrieve cited documentation')
        self.target = self.workflow.create_task(self.chat,'user','writer','Use cited documentation')
        for task, actor in ((self.task,'researcher'),(self.target,'writer')):
            self.workflow.start_task(task,actor)
        self.files = FileTools(self.workflow,self.path/'files')
        self.web = WebRetrieval(self.workflow,self.files)

    def tearDown(self):
        self.files.close(); self.workflow.close(); self.directory.cleanup()

    def page(self, body=b'<h1>Docs</h1><p>Check conditions.</p><script>EXECUTE ME</script>'):
        return {'url':'https://docs.example.org/guide','content_type':'text/html','body':body,
                'sha256':hashlib.sha256(body).hexdigest(),'redirects':[]}

    def test_disabled_network_never_resolves_or_connects(self):
        with patch('socket.getaddrinfo') as dns:
            with self.assertRaises(RetrievalError):
                PublicHTTPS().fetch('https://example.org')
            dns.assert_not_called()

    def test_pinned_public_ip_keeps_original_tls_host_and_no_credentials(self):
        connection = Connection(Reply())
        with patch('socket.getaddrinfo',return_value=PUBLIC), patch('agent_lab.retrieval._PinnedHTTPS',return_value=connection) as pinned:
            page = PublicHTTPS(allow_network=True).fetch('https://docs.example.org/a?q=hello')
        self.assertEqual(pinned.call_args.args[:2],('docs.example.org','93.184.216.34'))
        self.assertTrue(connection.closed)
        self.assertEqual(page['body'],b'<p>Evidence</p>')
        headers = connection.calls[0][1]['headers']
        self.assertFalse(set(headers)&{'Authorization','Cookie','Proxy-Authorization'})

    def test_local_urls_mixed_dns_and_private_redirects_are_rejected(self):
        for url in ('file:///etc/passwd','http://example.org','https://127.0.0.1','https://[::1]/',
                    'https://169.254.169.254/','https://u:p@example.org','https://example.org:8443/',
                    'https://example.org/\r\nHeader:bad','https://example.org\\@127.0.0.1/'):
            with self.subTest(url=url), self.assertRaises(RetrievalError): public_url(url)
        mixed = PUBLIC + [(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]
        with patch('socket.getaddrinfo',return_value=mixed), patch('agent_lab.retrieval._PinnedHTTPS') as pinned:
            with self.assertRaises(RetrievalError): PublicHTTPS(allow_network=True).fetch('https://example.org')
            pinned.assert_not_called()
        connection = Connection(Reply(status=302,Location='https://127.0.0.1/secret'))
        with patch('socket.getaddrinfo',return_value=PUBLIC), patch('agent_lab.retrieval._PinnedHTTPS',return_value=connection):
            with self.assertRaises(RetrievalError): PublicHTTPS(allow_network=True).fetch('https://example.org')
        self.assertTrue(connection.closed)

    def test_response_limits_unsupported_types_challenges_and_timeouts_fail_explicitly(self):
        replies=[Reply(b'x'*1025),Reply(**{'Content-Length':'99999'}),Reply(**{'Content-Type':'application/pdf'}),
                 Reply(status=202),Reply(**{'Content-Encoding':'gzip'})]
        for reply in replies:
            with patch('socket.getaddrinfo',return_value=PUBLIC), patch('agent_lab.retrieval._PinnedHTTPS',return_value=Connection(reply)):
                with self.assertRaises(RetrievalError):
                    PublicHTTPS(allow_network=True,limits=RetrievalLimits(response_bytes=1024)).fetch('https://example.org')
        with patch('socket.getaddrinfo',side_effect=TimeoutError):
            with self.assertRaisesRegex(RetrievalError,'failed or timed out'):
                PublicHTTPS(allow_network=True).fetch('https://example.org')

    def test_cited_text_uses_owned_files_and_explicit_snapshot_handoff(self):
        with patch.object(self.web.http,'fetch',return_value=self.page()):
            result=self.web.retrieve_text(self.task,'researcher',url='https://docs.example.org/guide',path='sources/guide.md')
        text=self.files.read_text(self.task,'researcher','sources/guide.md')['content']
        self.assertIn('Source: https://docs.example.org/guide',text)
        self.assertNotIn('EXECUTE ME',text)
        with self.assertRaises(WorkflowError): self.files.read_text(self.task,'writer','sources/guide.md')
        offer=self.files.offer_artifact(self.task,'researcher',path='sources/guide.md',target_task=self.target,
                                       expected_sha256=result['artifact']['sha256'])
        self.files.accept_artifact(self.target,'writer',artifact_id=offer['artifact_id'],path='sources/guide.md')
        self.assertEqual(self.files.read_text(self.target,'writer','sources/guide.md')['content'],text)
        self.assertEqual(self.workflow.db.execute('SELECT status FROM retrieval_records').fetchone()[0],'succeeded')

    def test_failed_requests_retained_and_bad_output_formats_do_not_fetch(self):
        with patch.object(self.web.http,'fetch',side_effect=RetrievalError('HTTP failure')):
            with self.assertRaises(RetrievalError):
                self.web.retrieve_text(self.task,'researcher',url='https://example.org',path='source.txt')
        self.assertEqual(self.workflow.db.execute('SELECT status FROM retrieval_records').fetchone()[0],'failed')
        with patch.object(self.web.http,'fetch') as fetch:
            for path in ('../escape.md','source.pdf','/source.md'):
                with self.assertRaises(WorkflowError): self.web.retrieve_text(self.task,'researcher',url='https://example.org',path=path)
            fetch.assert_not_called()
        self.workflow.ask_human(self.task,'researcher','user','Which source?')
        with self.assertRaises(WorkflowError): self.web.search_web(self.task,'researcher',query='docs',limit=1)

    def test_search_echo_site_filter_duplicate_and_challenge_handling(self):
        body=b'''<rss><channel><link>https://www.bing.com/search?q=site%3Adocs.example.org+guide</link>
            <item><title>Wrong domain</title><link>https://other.org/guide</link></item>
            <item><title>Guide</title><link>https://docs.example.org/guide</link></item>
            <item><title>Duplicate</title><link>https://docs.example.org/guide</link></item></channel></rss>'''
        with patch.object(self.web.http,'fetch',return_value=self.page(body)):
            result=self.web.search_web(self.task,'researcher',query='site:docs.example.org guide',limit=3)
        self.assertEqual(len(result['results']),1)
        self.assertEqual(result['results'][0]['title'],'Guide')
        for body in (b'<html>challenge</html>',b'<!DOCTYPE rss><rss/>',b'<rss><channel><link>https://x/?q=another</link></channel></rss>'):
            with patch.object(self.web.http,'fetch',return_value=self.page(body)), self.assertRaises(RetrievalError):
                self.web.search_web(self.task,'researcher',query='docs',limit=1)

    def test_gateway_requires_backend_and_caps_new_search_calls(self):
        with self.assertRaises(WorkflowError):
            ToolGateway(self.workflow,self.files,self.task,'researcher',human='user',allowed=['search_web'])
        gateway=ToolGateway(self.workflow,self.files,self.task,'researcher',human='user',allowed=['retrieve_text'],retrieval=self.web,max_calls=1)
        with patch.object(self.web.http,'fetch',return_value=self.page()):
            result=gateway.dispatch(tool('retrieve_text',{'url':'https://docs.example.org/guide','path':'source.md'},'retrieve'))
        self.assertTrue(json.loads(result['content'])['ok'])
        with self.assertRaises(WorkflowError): gateway.dispatch(tool('retrieve_text',{'url':'https://docs.example.org/guide','path':'again.md'},'again'))

    def test_text_extraction_truncation_and_utf8_boundary(self):
        text,truncated=plain_text(b'<p>'+b'a'*300+b'</p>','text/html',256)
        self.assertTrue(truncated); self.assertEqual(len(text),256)
        with self.assertRaises(RetrievalError): plain_text(b'\xff','text/plain',256)


if __name__=='__main__': unittest.main()
