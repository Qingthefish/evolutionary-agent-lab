"""Evaluation harness foundation: case loading, batch runs, metrics, and reports.

UI-independent. Offline fixture results are labelled `offline_fixture` and are
never live-model benchmarks.
"""

from .cases import CaseError, EvalCase, Expected, HumanExpected, SubtaskExpected, load_cases, parse_case
from .harness import Evaluator, compare_memory, list_runs, load_run, markdown_report, summarize

__all__ = ["CaseError", "EvalCase", "Expected", "HumanExpected", "SubtaskExpected", "Evaluator", "compare_memory", "list_runs", "load_cases",
           "load_run", "markdown_report", "parse_case", "summarize"]
