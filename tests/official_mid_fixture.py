"""Synthetic inputs for the C06 tests."""

from hashlib import sha256
from zipfile import ZIP_DEFLATED, ZipFile


README = "# Synthetic scenario fixture\n\nPost the second task to the same group.\n"
README_SHA256 = sha256(README.encode("utf-8")).hexdigest()
SCENARIOS = (
    ("scenario_1_software_engineering 2", "software-engineering",
     [("lead", "Role A"), ("dev", "Role B"), ("qa", "Role C"), ("release", "Role D")]),
    ("scenario_2_newsroom 2", "newsroom",
     [("chief_editor", "Role A"), ("reporter", "Role B"), ("fact_checker", "Role C"), ("editor", "Role D")]),
    ("scenario_3_securities_fund 2", "securities-fund",
     [("fund_manager", "Role A"), ("research", "Role B"), ("risk", "Role C"), ("marketing", "Role D")]),
)


def write_archive(path):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("README.md", README)
        archive.writestr("__MACOSX/._README.md", b"synthetic metadata")
        for number, (folder, _, roles) in enumerate(SCENARIOS, start=1):
            body = [f"# Scenario {number}: Fixture {number}", ""]
            body.extend(f"| `{identifier}` | {name} |" for identifier, name in roles)
            for identifier, name in roles:
                body.extend(["", f"## {name} ({identifier})", "", "```text",
                             f"Synthetic role instructions for {identifier}.", "```"])
            archive.writestr(f"{folder}/01_role_initialization.md", "\n".join(body) + "\n")
            for sequence in (1, 2):
                prompt = f"Synthetic request for scenario {number}, task {sequence}."
                if (number, sequence) == (3, 2):
                    prompt += " Render the sample as HTML slides."
                archive.writestr(
                    f"{folder}/0{sequence + 1}_task_{sequence}.md",
                    f"# Scenario {number}, Task {sequence}: Fixture request {sequence}\n"
                    f"\n```text\n{prompt}\n```\n",
                )
