"""Read the instructor's mid-term scenario archive without executing its text.

This is a source adapter, not a driver or a grading rubric.  In particular,
the two tasks in each scenario retain their ordering and shared-group contract;
they are not converted into independent development evaluation cases.
"""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import stat
from zipfile import BadZipFile, LargeZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
from zlib import error as ZlibError

from ..core import WorkflowError


class OfficialDatasetError(WorkflowError):
    """The supplied archive does not match the supported mid-test contract."""


_MAX_ARCHIVE_BYTES = 1024 * 1024
_MAX_MEMBER_BYTES = 64 * 1024
_MAX_TOTAL_BYTES = 1024 * 1024
_MAX_ENTRIES = 128
# Protocol labels below interpret this issued README only.  Repacking the ZIP
# or removing Apple metadata is harmless, but changed protocol prose requires
# review rather than silently inheriting continuity/human-intervention rules.
_README_SHA256 = "9bc106f579ba7fbc3ee536b83d390c906e64cff69294c915e65134f7a3b9134b"

# The trailing spaces and ' 2' suffixes are part of the issued ZIP filenames.
_SCENARIOS = (
    ("software-engineering", "scenario_1_software_engineering 2",
     ("lead", "dev", "qa", "release")),
    ("newsroom", "scenario_2_newsroom 2",
     ("chief_editor", "reporter", "fact_checker", "editor")),
    ("securities-fund", "scenario_3_securities_fund 2",
     ("fund_manager", "research", "risk", "marketing")),
)
_FILES = ("01_role_initialization.md", "02_task_1.md", "03_task_2.md")
_EXPECTED_FILES = {"README.md"} | {
    f"{directory}/{filename}"
    for _, directory, _ in _SCENARIOS for filename in _FILES
}
_EXPECTED_DIRECTORIES = {directory + "/" for _, directory, _ in _SCENARIOS}
_TEXT_BLOCK = re.compile(
    r"^```text[ \t]*\r?\n(?P<text>.*?)\r?\n```[ \t]*(?:\r?\n|$)",
    re.MULTILINE | re.DOTALL,
)
_ROLE_ROW = re.compile(
    r"^\|[ \t]*`([a-z][a-z0-9_]*)`[ \t]*\|[ \t]*([^|\r\n]+?)[ \t]*\|[ \t]*\r?$",
    re.MULTILINE,
)
_ROLE_HEADING = re.compile(
    r"^## ([^\r\n]+) \(([a-z][a-z0-9_]*)\)\r?$", re.MULTILINE,
)


def _safe_member(info):
    name = info.filename
    # ZipInfo truncates filenames at NUL.  Do not let that turn an invalid name
    # into a supported member or hide a duplicate of a supported document.
    if (not name or info.orig_filename != name or "\x00" in name
            or "\\" in name or name.startswith("/")):
        raise OfficialDatasetError("Archive member has an unsafe path")
    parts = name.removesuffix("/").split("/")
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        raise OfficialDatasetError("Archive member has an unsafe path")
    mode = stat.S_IFMT(info.external_attr >> 16)
    if mode == stat.S_IFLNK:
        raise OfficialDatasetError("Archive symbolic links are not supported")
    if mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise OfficialDatasetError("Archive special files are not supported")
    if (mode == stat.S_IFDIR and not info.is_dir()) or (info.is_dir() and info.file_size):
        raise OfficialDatasetError("Archive directory metadata is invalid")
    if info.flag_bits & 1:
        raise OfficialDatasetError("Encrypted archive members are not supported")
    if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
        raise OfficialDatasetError("Unsupported archive compression method")
    if not 0 <= info.file_size <= _MAX_MEMBER_BYTES:
        raise OfficialDatasetError("Archive member exceeds the size limit")


def _read_members(raw):
    documents, ignored = {}, []
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > _MAX_ENTRIES:
            raise OfficialDatasetError("Archive has too many members")
        seen = set()
        total = 0
        for info in entries:
            _safe_member(info)
            name = info.filename
            if name in seen:
                raise OfficialDatasetError("Archive contains duplicate member names")
            seen.add(name)
            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                raise OfficialDatasetError("Archive exceeds the uncompressed size limit")
            if name.startswith("__MACOSX/"):
                ignored.append(name)
                continue  # Apple metadata is never decoded or interpreted.
            if info.is_dir():
                if name not in _EXPECTED_DIRECTORIES:
                    raise OfficialDatasetError("Unexpected directory in mid-test archive")
                continue
            if name not in _EXPECTED_FILES:
                raise OfficialDatasetError("Unexpected document in mid-test archive")
            content = archive.read(info)
            if len(content) != info.file_size or len(content) > _MAX_MEMBER_BYTES:
                raise OfficialDatasetError("Archive member size does not match its content")
            try:
                text = content.decode("utf-8")
            except UnicodeError:
                raise OfficialDatasetError("Mid-test documents require valid UTF-8") from None
            if "\x00" in text:
                raise OfficialDatasetError("Mid-test documents cannot contain NUL characters")
            documents[name] = (content, text)
    if set(documents) != _EXPECTED_FILES:
        raise OfficialDatasetError("Mid-test archive is missing required documents")
    return documents, sorted(ignored)


def _one_text_block(text, source):
    blocks = list(_TEXT_BLOCK.finditer(text))
    if len(blocks) != 1 or text.count("```") != 2:
        raise OfficialDatasetError(f"Expected one fenced text prompt in {source}")
    prompt = blocks[0]["text"]
    if not prompt.strip():
        raise OfficialDatasetError(f"Empty prompt in {source}")
    return prompt


def _scenario_roles(text, source, number, expected_ids):
    titles = re.findall(r"^# Scenario ([1-3]): ([^\r\n]+)\r?$", text, re.MULTILINE)
    if len(titles) != 1 or int(titles[0][0]) != number:
        raise OfficialDatasetError(f"Invalid scenario heading in {source}")
    rows = [(match[1], match[2].strip()) for match in _ROLE_ROW.finditer(text)]
    if tuple(identifier for identifier, _ in rows) != expected_ids:
        raise OfficialDatasetError(f"Invalid, missing, or duplicate role table IDs in {source}")
    headings = list(_ROLE_HEADING.finditer(text))
    if [(heading[2], heading[1]) for heading in headings] != rows:
        raise OfficialDatasetError(f"Role headings differ from the role table in {source}")
    if text.count("```") != 2 * len(expected_ids):
        raise OfficialDatasetError(f"Unexpected fenced blocks in {source}")
    roles = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        prompt = _one_text_block(text[heading.end():end], source)
        roles.append({"id": heading[2], "name": heading[1], "prompt": prompt})
    return titles[0][1], roles


def _scenario_task(text, source, scenario_number, sequence):
    titles = re.findall(
        r"^# Scenario ([1-3]), Task ([1-2]): ([^\r\n]+)\r?$", text, re.MULTILINE,
    )
    if (len(titles) != 1
            or tuple(map(int, titles[0][:2])) != (scenario_number, sequence)):
        raise OfficialDatasetError(f"Invalid task heading in {source}")
    identifier = f"scenario-{scenario_number}-task-{sequence}"
    return {
        "id": identifier,
        "sequence": sequence,
        "title": titles[0][2],
        "source": source,
        "prompt": _one_text_block(text, source),
        "depends_on": None if sequence == 1 else f"scenario-{scenario_number}-task-1",
        "requested_format": "html_slides" if (scenario_number, sequence) == (3, 2) else "unspecified",
    }


def load_mid_test(archive_path):
    """Return a deterministic, JSON-serializable source manifest for Mid_Test.zip.

    Reading makes no network/model calls, extracts no files and creates no run
    state.  Prompts are returned as data: they grant no runtime permissions and
    cannot change provider, approval, document-format or grading policies.
    """
    try:
        path = Path(archive_path)
        with path.open("rb") as stream:
            raw = stream.read(_MAX_ARCHIVE_BYTES + 1)
        if len(raw) > _MAX_ARCHIVE_BYTES:
            raise OfficialDatasetError("Mid-test archive exceeds the size limit")
        documents, ignored = _read_members(raw)
    except OfficialDatasetError:
        raise
    except (OSError, ValueError, TypeError, EOFError, RuntimeError, NotImplementedError,
            BadZipFile, LargeZipFile, ZlibError):
        raise OfficialDatasetError("Cannot read a valid bounded mid-test ZIP archive") from None

    if sha256(documents["README.md"][0]).hexdigest() != _README_SHA256:
        raise OfficialDatasetError("Changed README requires a new adapter protocol review")

    scenarios = []
    for number, (identifier, directory, expected_ids) in enumerate(_SCENARIOS, 1):
        role_source = f"{directory}/{_FILES[0]}"
        title, roles = _scenario_roles(documents[role_source][1], role_source, number, expected_ids)
        tasks = []
        for sequence, filename in enumerate(_FILES[1:], 1):
            source = f"{directory}/{filename}"
            tasks.append(_scenario_task(documents[source][1], source, number, sequence))
        scenarios.append({"id": identifier, "title": title, "role_source": role_source,
                          "roles": roles, "tasks": tasks})

    return {
        "schema_version": 1,
        "dataset_id": "nlp-mid-test-2026",
        "split": "official_mid",
        "source": {
            "archive_name": path.name,
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
            "members": [
                {"path": name, "sha256": sha256(content).hexdigest(), "bytes": len(content)}
                for name, (content, _) in sorted(documents.items())
            ],
            "ignored_members": ignored,
        },
        "readme": {"source": "README.md", "text": documents["README.md"][1]},
        "scenarios": scenarios,
        "protocol": {
            "within_scenario": "same_group_same_context",
            "between_scenarios": "separate_group",
            "human": "real_unscripted",
            "acceptance": "negotiated_with_human",
            "memory_reset_rules": "unspecified",
            "repeat_rules": "unspecified",
            "scoring_rubric": "unspecified",
            "timing_rule": "unspecified",
            "format_conflict_task_ids": ["scenario-3-task-2"],
        },
    }
