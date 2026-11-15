"""Official mid-test import is bounded, lossless, and has no runtime effects."""

import copy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from agent_lab.evaluation.official_dataset import OfficialDatasetError, load_mid_test


ARCHIVE = Path(__file__).resolve().parents[1] / 'evaluation/official/mid-test/Mid_Test.zip'
SCENARIOS = (
    ('scenario_1_software_engineering 2', 'software-engineering',
     [('lead', 'Technical Lead'), ('dev', 'Software Developer'),
      ('qa', 'Test Engineer'), ('release', 'Release Manager')]),
    ('scenario_2_newsroom 2', 'newsroom',
     [('chief_editor', 'Editor-in-Chief'), ('reporter', 'Reporter'),
      ('fact_checker', 'Fact-Checker'), ('editor', 'Editor')]),
    ('scenario_3_securities_fund 2', 'securities-fund',
     [('fund_manager', 'Fund Manager'), ('research', 'Investment Research Analyst'),
      ('risk', 'Risk Manager'), ('marketing', 'Marketing Specialist')]),
)


class OfficialDatasetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)

    def rewritten_archive(self, *, changes=None, omitted=(), additions=()):
        """Alter the real package without extracting any member to disk."""
        changes = changes or {}
        target = self.path / 'Mid_Test.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)  # intentional duplicate ZIP names
            with ZipFile(ARCHIVE) as source, ZipFile(target, 'w', compression=ZIP_DEFLATED) as result:
                for member in source.infolist():
                    if member.filename not in omitted:
                        result.writestr(copy.copy(member),
                                        changes.get(member.filename, source.read(member)))
                for member, content in additions:
                    result.writestr(member, content)
        return target

    def test_real_package_retains_every_original_document_and_hash(self):
        result = load_mid_test(ARCHIVE)
        self.assertEqual(result['dataset_id'], 'nlp-mid-test-2026')
        self.assertEqual(result['split'], 'official_mid')
        raw = ARCHIVE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'e104fedbb6db46399936c69251ca2843dfa1e5845441f0a17af6e1af88cf25f2')
        self.assertEqual(result['source']['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['source']['bytes'], len(raw))
        self.assertEqual(result['source']['archive_name'], 'Mid_Test.zip')
        with ZipFile(ARCHIVE) as source:
            meaningful = sorted(name for name in source.namelist()
                                if name.endswith('.md') and not name.startswith('__MACOSX/'))
            expected = [{'path': name, 'sha256': hashlib.sha256(source.read(name)).hexdigest(),
                         'bytes': len(source.read(name))} for name in meaningful]
            self.assertEqual(len(expected), 10)
            self.assertEqual(result['source']['members'], expected)
            self.assertEqual(result['source']['ignored_members'],
                             sorted(name for name in source.namelist() if name.startswith('__MACOSX/')))
            self.assertEqual(result['readme'],
                             {'source': 'README.md', 'text': source.read('README.md').decode('utf-8')})

    def test_all_roles_and_six_tasks_preserve_the_exact_fenced_prompts(self):
        result = load_mid_test(ARCHIVE)
        self.assertEqual(len(result['scenarios']), 3)
        all_task_ids = []
        with ZipFile(ARCHIVE) as source:
            for number, ((folder, scenario_id, roles), scenario) in enumerate(
                    zip(SCENARIOS, result['scenarios']), start=1):
                with self.subTest(scenario=scenario_id):
                    self.assertEqual(scenario['id'], scenario_id)
                    role_source = f'{folder}/01_role_initialization.md'
                    self.assertEqual(scenario['role_source'], role_source)
                    self.assertEqual([(role['id'], role['name']) for role in scenario['roles']], roles)
                    role_document = source.read(role_source).decode('utf-8')
                    role_prompts = [part.split('\n```', 1)[0]
                                    for part in role_document.split('```text\n')[1:]]
                    self.assertEqual([role['prompt'] for role in scenario['roles']], role_prompts)
                    self.assertEqual(len(scenario['tasks']), 2)
                    for sequence, task in enumerate(scenario['tasks'], start=1):
                        task_id = f'scenario-{number}-task-{sequence}'
                        task_source = f'{folder}/0{sequence + 1}_task_{sequence}.md'
                        document = source.read(task_source).decode('utf-8')
                        prompt = document.split('```text\n', 1)[1].split('\n```', 1)[0]
                        self.assertEqual(task['id'], task_id)
                        self.assertEqual(task['sequence'], sequence)
                        self.assertEqual(task['source'], task_source)
                        self.assertEqual(task['prompt'], prompt)
                        self.assertEqual(task['depends_on'],
                                         None if sequence == 1 else f'scenario-{number}-task-1')
                        self.assertIn(task['title'], document.splitlines()[0])
                        self.assertEqual(hashlib.sha256(task['prompt'].encode('utf-8')).hexdigest(),
                                         hashlib.sha256(prompt.encode('utf-8')).hexdigest())
                        all_task_ids.append(task_id)
        self.assertEqual(len(all_task_ids), 6)
        self.assertEqual(len(set(all_task_ids)), 6)

    def test_html_slide_requirement_remains_visible_without_silent_conversion(self):
        result = load_mid_test(ARCHIVE)
        tasks = [task for scenario in result['scenarios'] for task in scenario['tasks']]
        self.assertEqual([task['requested_format'] for task in tasks],
                         ['unspecified'] * 5 + ['html_slides'])
        self.assertIn('Deliver it as HTML slides', tasks[-1]['prompt'])
        self.assertIn('end-of-2026 perspective', tasks[-1]['prompt'])

    def test_same_group_continuity_and_unresolved_protocol_are_explicit(self):
        result = load_mid_test(ARCHIVE)
        self.assertEqual(result['protocol'], {
            'within_scenario': 'same_group_same_context',
            'between_scenarios': 'separate_group',
            'human': 'real_unscripted',
            'acceptance': 'negotiated_with_human',
            'memory_reset_rules': 'unspecified',
            'repeat_rules': 'unspecified',
            'scoring_rubric': 'unspecified',
            'timing_rule': 'unspecified',
            'format_conflict_task_ids': ['scenario-3-task-2'],
        })

    def test_repeat_import_is_deterministic_json_without_extraction_or_model_calls(self):
        from agent_lab.deepseek import DeepSeekHTTP

        with patch.object(ZipFile, 'extract', side_effect=AssertionError('No extraction')) as extract, \
             patch.object(ZipFile, 'extractall', side_effect=AssertionError('No extraction')) as extractall, \
             patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('No model request')) as model:
            first = load_mid_test(ARCHIVE)
            second = load_mid_test(ARCHIVE)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        extract.assert_not_called()
        extractall.assert_not_called()
        model.assert_not_called()
        self.assertEqual(list(self.path.iterdir()), [])

    def test_macos_metadata_is_optional_but_never_a_role_or_task(self):
        with ZipFile(ARCHIVE) as source:
            metadata = [name for name in source.namelist() if name.startswith('__MACOSX/')]
        original = load_mid_test(ARCHIVE)
        stripped = load_mid_test(self.rewritten_archive(omitted=metadata))
        self.assertEqual(stripped['scenarios'], original['scenarios'])
        self.assertEqual(stripped['source']['ignored_members'], [])
        self.assertNotEqual(stripped['source']['sha256'], original['source']['sha256'])

    def test_missing_extra_or_duplicate_document_is_an_import_error(self):
        task = 'scenario_2_newsroom 2/03_task_2.md'
        for kwargs in ({'omitted': [task]},
                       {'additions': [('unlisted-task.md', b'```text\nExtra task\n```\n')]},
                       {'additions': [('README.md', b'duplicate')]}):
            with self.subTest(change=kwargs), self.assertRaises(OfficialDatasetError):
                load_mid_test(self.rewritten_archive(**kwargs))

    def test_unsafe_member_paths_are_rejected_without_writing_files(self):
        for name in ('../outside.txt', '/absolute.txt', 'scenario_1_software_engineering 2/../escape.txt',
                     'scenario_2_newsroom 2\\extra.md', '__MACOSX/../../escape.txt'):
            with self.subTest(name=name), self.assertRaises(OfficialDatasetError):
                load_mid_test(self.rewritten_archive(additions=[(name, b'untrusted data')]))
        self.assertFalse((self.path / 'outside.txt').exists())
        self.assertFalse((self.path / 'escape.txt').exists())

    def test_symlink_and_invalid_utf8_cannot_be_imported_as_documents(self):
        link = ZipInfo('README.md')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(self.rewritten_archive(omitted=['README.md'], additions=[(link, b'outside.md')]))
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(self.rewritten_archive(changes={'README.md': b'\xff\xfeinvalid UTF-8'}))

    def test_missing_or_ambiguous_prompt_fences_are_not_silently_guessed(self):
        path = 'scenario_1_software_engineering 2/02_task_1.md'
        with ZipFile(ARCHIVE) as source:
            original = source.read(path)
        for content in (b'# Task without a fenced prompt\n',
                        original + b'\n```text\nSecond competing prompt\n```\n'):
            with self.subTest(content=content[-50:]), self.assertRaises(OfficialDatasetError):
                load_mid_test(self.rewritten_archive(changes={path: content}))

    def test_duplicate_role_identity_is_rejected(self):
        path = 'scenario_1_software_engineering 2/01_role_initialization.md'
        with ZipFile(ARCHIVE) as source:
            content = source.read(path).replace(b'| `dev` |', b'| `lead` |')
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(self.rewritten_archive(changes={path: content}))

    def test_changed_readme_cannot_silently_change_the_imported_protocol(self):
        with ZipFile(ARCHIVE) as source:
            changed = source.read('README.md').replace(b'to the same group', b'to a fresh independent group')
        with self.assertRaisesRegex(OfficialDatasetError, 'adapter protocol review'):
            load_mid_test(self.rewritten_archive(changes={'README.md': changed}))

    def test_oversized_archive_member_and_member_count_fail_closed(self):
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(self.rewritten_archive(changes={'README.md': b'x' * (70 * 1024)}))
        additions = [(f'__MACOSX/._extra-{index}', b'') for index in range(129)]
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(self.rewritten_archive(additions=additions))
        compressed_bomb = [(f'__MACOSX/._large-{index}', b'x' * (60 * 1024))
                           for index in range(20)]
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(self.rewritten_archive(additions=compressed_bomb))
        large = self.path / 'oversized.zip'
        large.write_bytes(ARCHIVE.read_bytes() + b'x' * (1024 * 1024))
        with self.assertRaises(OfficialDatasetError):
            load_mid_test(large)

    def test_bad_truncated_missing_and_directory_archives_raise_domain_errors(self):
        for name, content in [('not-a-zip.zip', b'not a zip'),
                              ('truncated.zip', ARCHIVE.read_bytes()[:100])]:
            path = self.path / name
            path.write_bytes(content)
            with self.subTest(name=name), self.assertRaises(OfficialDatasetError):
                load_mid_test(path)
        for path in (self.path / 'missing.zip', self.path):
            with self.subTest(path=path.name), self.assertRaises(OfficialDatasetError):
                load_mid_test(path)


if __name__ == '__main__':
    unittest.main()
