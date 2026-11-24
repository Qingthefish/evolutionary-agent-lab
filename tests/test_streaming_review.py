"""Independent negative controls for the teammate streaming/partial-edit review."""
import json
from unittest.mock import patch
import unittest

from agent_lab.deepseek import ProviderError, StreamAssemblyError, assemble_stream
from agent_lab.hkgai import HKGAIHTTP
from test_streaming_transport import TOOL_STREAM, delta, event, sse_server
import test_classroom_robustness as robustness
from agent_lab.files import FileToolError


class StreamReviewTests(unittest.TestCase):
    def test_conflicting_response_identity_cannot_be_combined(self):
        for key in ('id','model'):
            with self.subTest(key=key),self.assertRaises(StreamAssemblyError):
                changed=json.loads(TOOL_STREAM[1][5:]);changed[key]='different-response'
                assemble_stream([TOOL_STREAM[0],'data: '+json.dumps(changed),*TOOL_STREAM[2:]],max_bytes=1<<20)

    def test_complete_body_without_done_is_still_an_interrupted_stream(self):
        with self.assertRaises(StreamAssemblyError):
            assemble_stream(TOOL_STREAM[:-1],max_bytes=1<<20)

    def test_malformed_tool_fields_are_sanitized_and_operator_decidable(self):
        for bad in ([1], 'private-upstream-text', True):
            lines=[delta(tool_calls=[{'index':0,'function':bad}])]
            with self.subTest(bad=bad),sse_server(lines):
                with self.assertRaises(ProviderError) as caught:
                    HKGAIHTTP('synthetic-key',allow_network=True,stream=True)(b'{"model":"synthetic"}')
                self.assertEqual(caught.exception.diagnostics()['kind'],'invalid_stream')
                self.assertNotIn('private-upstream-text',str(caught.exception))

    def test_malformed_tool_array_is_a_stream_error_not_type_error(self):
        with sse_server([delta(tool_calls=True)]):
            with self.assertRaises(ProviderError) as caught:
                HKGAIHTTP('synthetic-key',allow_network=True,stream=True)(b'{}')
            self.assertEqual(caught.exception.diagnostics()['kind'],'invalid_stream')

    def test_multibyte_text_obeys_actual_encoded_byte_cap(self):
        with self.assertRaises(StreamAssemblyError):
            assemble_stream([delta(content='界'*100),delta(finish='stop'),
                event(choices=[],usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}),
                'data: [DONE]'],max_bytes=200)

    def test_tool_arguments_after_finish_and_changed_call_identity_are_refused(self):
        for inserted in [delta(tool_calls=[{'index':0,'function':{'arguments':'extra'}}]),
                         delta(tool_calls=[{'index':0,'id':'different-call'}])]:
            with self.subTest(inserted=inserted),self.assertRaises(StreamAssemblyError):
                assemble_stream([*TOOL_STREAM[:7],inserted,*TOOL_STREAM[7:]],max_bytes=1<<20)

    def test_missing_first_call_fragment_is_not_silently_reindexed(self):
        lines=[TOOL_STREAM[0],TOOL_STREAM[5],*TOOL_STREAM[6:]]
        with self.assertRaises(StreamAssemblyError):assemble_stream(lines,max_bytes=1<<20)

    def test_raw_line_read_is_bounded_before_allocating_the_whole_line(self):
        with sse_server(['data: '+('x'*2048)]),patch.object(HKGAIHTTP,'max_stream_bytes',128):
            with self.assertRaises(ProviderError) as caught:
                HKGAIHTTP('synthetic-key',allow_network=True,stream=True)(b'{}')
            self.assertEqual(caught.exception.diagnostics()['kind'],'invalid_stream')
            self.assertLessEqual(caught.exception.diagnostics()['response_bytes'],129)


class PassageReviewTests(unittest.TestCase):
    setUp=robustness.ReplaceTextTests.setUp
    read=robustness.ReplaceTextTests.read
    def test_overlapping_matches_are_ambiguous_and_leave_file_unchanged(self):
        self.files.update_text(self.task,'writer','GUIDE.md','banana',expected_sha256=robustness.sha(self.read()))
        with self.assertRaisesRegex(FileToolError,'occurs|ambiguous'):
            self.files.replace_text(self.task,'writer','GUIDE.md','ana','X',expected_sha256=robustness.sha('banana'))
        self.assertEqual(self.read(),'banana')
