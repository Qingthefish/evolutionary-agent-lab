# Audit a saved development batch

The ordinary batch evaluator saves `results.json` and a `run-progress.json`
checkpoint. This reader checks their **internal consistency** without starting a
runtime, reading credentials, calling a model, opening task databases or rewriting
the original files. It supports the recorded completion/time evidence in
[R13 and R17](requirements.md), not an instructor-issued score.

From the repository root, using Python 3.12 or newer, run the existing offline
batch, then audit the run directory printed by it:

```bash
python -m agent_lab.evaluation run --output runs/evaluations
python -m agent_lab.evaluation.run_audit --run runs/evaluations/RUN_ID
python -m agent_lab.evaluation.run_audit --run runs/evaluations/RUN_ID --format markdown
```

Only the audit commands are read-only. Output goes to stdout; redirect it to a
separate file if needed. No optional dependencies, API key or network are needed.
Each input must be a regular UTF-8 JSON file of at most 16 MiB; symlinks, FIFOs,
duplicate JSON keys and non-finite numbers are refused.

| Status / exit code | Meaning |
| --- | --- |
| `consistent` / `0` | A complete final batch agrees with its saved manifest, outcomes and optional checkpoint. Failed or unconfigured cases can still be consistently recorded. |
| `incomplete` / `1` | A valid checkpoint survives without a final report, or finalization has not completed. Returned, active and unstarted cases remain separate. |
| `invalid` / `2` | Missing, malformed, unsupported or inconsistent records; inspect fixed finding codes and JSON locations. |

The audit checks unique case coverage, case definitions including supplied inputs,
manifest fingerprints, check inventory and Boolean types, failure classification,
task trees and timing, recomputed summary metrics and ordered checkpoint progress.
It uses the evaluator's existing `summarize` and classification rules. Negative
controls stay outside the scored denominator; unconfigured cases remain unrun;
accepted rejection contracts are distinct from verified goal completion. Earlier
report-only batches are supported if they contain the current manifest/outcome
schema. Historical code fingerprints are checked internally, not compared against
the current checkout.

The JSON output includes source SHA-256 fingerprints, sanitized findings and
recomputed metrics. It excludes raw prompts, case text, notes, model responses and
exception messages. `model_calls: 0` describes the audit itself; unknown source
model usage is not converted to zero. Audit stopped/quiescent runs: files are read
in sequence, not as an atomic snapshot of a changing directory.

An internally consistent record can still be forged or describe incorrect work.
The audit does **not** recheck artifacts, approval events, execution provenance,
provider responses or database integrity. It cannot establish model ability,
learning gains, official results or a grade. `authenticity_verified` and
`benchmark_valid` remain `false`.

Topology and frozen-memory experiments have their existing protocol-specific
comparison commands. Official preparation records are a different schema. This
tool accepts only ordinary development batches and does not replace those tools.
