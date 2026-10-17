# ruff: noqa: E501  (long document text)
"""Step 54 part A: ``python tasks.py results`` (scripts/results.py) and ``python tasks.py proof`` (scripts/proof.py), the
two data files they read, and docs/SAFETY_MATRIX.md (every file, function and golden case it names exists)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import proof  # noqa: E402
import results  # noqa: E402

import tasks  # noqa: E402

MATRIX = (ROOT / "docs" / "SAFETY_MATRIX.md").read_text(encoding="utf-8")
GOLDEN = {
    c["id"] for c in json.loads((ROOT / "data" / "eval" / "golden_cases.json").read_text(encoding="utf-8"))["cases"]
}
EVALS_SAMPLE = """# Golden eval results (v0)

Run 2026-10-07T00:28:54+05:30, mock mode.

| Case | Result | Detail |
|---|---|---|
| a-case | PASS | - |
| b-case | FAIL | boom |
| c-case | PASS | - |

**Score: 2/3**
"""
REPLAY_SAMPLE = """p50 and p95 per step over 20 rounds (milliseconds; the budget is 500 ms at p95):
{"replay_summary": {"initialize": {"p50": 15.1, "p95": 27.1}, "tools/list": {"p50": 4.7, "p95": 7.9}}}
"""


def test_the_two_commands_exist_in_the_task_runner_and_its_help():
    assert tasks.COMMANDS["results"] is tasks.results and tasks.COMMANDS["proof"] is tasks.proof
    assert "python tasks.py results" in tasks.__doc__ and "python tasks.py proof" in tasks.__doc__


def test_the_eval_table_is_read_not_typed():
    got = results.parse_evals(EVALS_SAMPLE)
    assert got == {
        "run": "2026-10-07T00:28:54+05:30",
        "cases": 3,
        "passed": 2,
        "failed": ["b-case"],
        "score_line": "2/3",
    }


def test_the_replay_summary_and_rounds_are_read_from_the_output():
    steps, rounds = results.parse_replay(REPLAY_SAMPLE)
    assert steps == [("initialize", 15.1, 27.1), ("tools/list", 4.7, 7.9)] and rounds == 20
    assert results.parse_replay("nothing here") == ([], None)


def test_the_check_summary_is_taken_from_the_saved_check_output():
    log = "== unit tests ==\n12 passed\n\n== check summary ==\n  PASS  lint (ruff)\n  FAIL  unit tests\ncheck: FAILED\n"
    assert results.parse_check_log(log) == ["PASS  lint (ruff)", "FAIL  unit tests", "check: FAILED"]
    assert results.parse_check_log("no summary") == []


def test_the_collected_count_is_read_from_the_pytest_line():
    assert results.collected("1550 tests collected in 2.66s") == 1550
    assert results.collected("1 test collected in 0.1s") == 1
    assert results.collected("error") is None


def test_the_mutation_totals_equal_the_sum_of_the_rows_and_every_row_is_valid():
    data = json.loads(results.MUTATIONS.read_text(encoding="utf-8"))
    rows = data["rows"]
    assert rows
    for r in rows:
        assert 0 < r["caught"] <= r["total"], r
        if r["caught"] < r["total"]:
            assert r["note"], f"a part with survivors must name them: {r}"
    table = results.mutation_table(data)
    caught, total = sum(r["caught"] for r in rows), sum(r["total"] for r in rows)
    assert f"**{caught} / {total}**" in table
    assert "cannot be reproduced from a clone" in data["source"]


def test_the_review_rounds_file_has_a_scope_a_finding_and_an_outcome_for_every_round():
    data = json.loads(results.REVIEWS.read_text(encoding="utf-8"))
    assert len(data["rounds"]) >= 5
    for r in data["rounds"]:
        assert r["scope"] and r["found"] and r["fixed"], r
    assert "not reproduced here" in data["source"]


def _render(check_summary: list[str]) -> str:
    return results.render(
        today="2026-10-07",
        commit="abc1234",
        tree="clean",
        counts={"harness": 1, "unit": 2, "contract": None},
        evals=results.parse_evals(EVALS_SAMPLE),
        conformance="21 passed in 3.0s",
        probe_rows=["2025-11-25 | 200 | 2025-11-25"],
        replay=results.parse_replay(REPLAY_SAMPLE),
        readiness_line="6 runtime checks met; 2 document-structure checks met; not an Amazon verdict.",
        not_checkable="4 requirements are not checkable locally",
        telugu=results.telugu_sentence("**Pending: 3** · Approved: 2"),
        check_summary=check_summary,
        mutations=json.loads(results.MUTATIONS.read_text(encoding="utf-8")),
        reviews=json.loads(results.REVIEWS.read_text(encoding="utf-8")),
        history=[("2026-09-27", 9), ("2026-09-28", 2)],
    )


def test_the_rendered_results_label_the_latency_and_the_readiness_and_keep_the_pilot_placeholder():
    text = _render([])
    assert "server time on localhost, mock mode, not Amazon's 500 ms round trip" in text
    assert "not an Amazon verdict" in text
    assert "No pilot usage numbers recorded yet." in text
    assert "| `tests/contract` | not recorded |" in text  # a missing count is said, never invented
    assert "**3**" in text  # the total adds the counts that exist
    assert "Failing cases: `b-case`." in text and "2 of 3 cases passed" in text


def test_the_header_says_which_sections_are_generated_and_which_are_copied_by_hand():
    head = _render([]).split("## 1.")[0]
    assert "Nothing here is typed by hand" not in head
    assert "Sections 1, 2, 4, 5, 6 and 8 are generated" in head and "sections 3 and 7 are copied by hand" in head
    assert "4 requirements are not checkable locally" in _render([])


def test_only_the_generated_files_are_ignored_when_judging_the_tree():
    assert results.tree_state("") == "clean"
    assert results.tree_state(" M docs/RESULTS.md\n M docs/proof/verify.txt\n") == "clean"
    assert results.tree_state(" M docs/RESULTS.md\n M README.md\n") == "modified (uncommitted files)"
    assert results.tree_state("?? docs/proofs.md\n") == "modified (uncommitted files)"
    assert proof.tree_state(" M docs/proof/verify.txt\n") == "clean"
    assert proof.tree_state(" M scripts/proof.py\n") == "modified (uncommitted files)"


def test_the_telugu_sentence_takes_its_numbers_from_the_review_file():
    assert results.telugu_sentence("**Pending: 3** · Approved: 2") == (
        "2 of 5 strings reviewed by the builder, a native Telugu speaker (single reviewer, not independent); "
        "3 pending; the farmer-preferred wording for follow-up is still to be confirmed."
    )
    assert "not recorded" in results.telugu_sentence("no counts here")
    assert "- Telugu: 2 of 5 strings reviewed by the builder" in _render([])


def test_a_missing_check_log_is_said_and_a_given_one_is_shown():
    assert "not recorded" in _render([]).split("## 2.")[0]
    shown = _render(["PASS  lint (ruff)", "check: PASSED"])
    assert "PASS  lint (ruff)" in shown and "check: PASSED" in shown


def test_the_option_check_is_strict(capsys):
    assert results.main(["--bogus"]) == 2
    assert "only option" in capsys.readouterr().err


def test_a_proof_file_starts_with_the_command_the_date_and_the_commit():
    head = proof.header("verify", "2026-10-07", "abc1234", "clean", 0)
    for needle in ("Command: python tasks.py verify", "Date: 2026-10-07", "Commit: abc1234", "Working tree: clean"):
        assert needle in head
    assert set(proof.COMMANDS) == {"verify", "readiness", "probe-protocol-version", "inspector-replay"}


def test_a_temporary_folder_path_naming_the_local_account_is_replaced_in_proof_text():
    raw = r"Temporary state file: C:\Users\SomeName\AppData\Local\Temp\clucktalk_probe_x\probe.sqlite3"
    assert proof.scrub(raw) == "Temporary state file: <temporary folder>\\probe.sqlite3"
    assert "SomeName" not in proof.scrub(raw)
    assert proof.scrub("no path here") == "no path here"


# -- the safety matrix --------------------------------------------------------------------------------------
def test_every_path_the_safety_matrix_names_exists():
    paths = set(re.findall(r"`((?:src|tests|docs|data|scripts)/[\w./-]+)`", MATRIX))
    assert len(paths) > 30
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, missing


def test_every_function_the_matrix_names_is_in_the_file_named_next_to_it():
    pairs = re.findall(r"`(src/[\w./-]+\.py)` \(([^)]*)\)", MATRIX)
    assert len(pairs) >= 10
    for path, names in pairs:
        source = (ROOT / path).read_text(encoding="utf-8")
        for name in re.findall(r"`([A-Za-z_][\w*]*)`", names):
            stem = name.rstrip("*")
            assert stem in source, f"{name} is not in {path}"


def test_every_golden_case_the_matrix_names_exists():
    cases = set(re.findall(r"[Cc]ase `([\w-]+)`", MATRIX))
    assert len(cases) >= 8
    assert not (cases - GOLDEN), cases - GOLDEN


def test_the_matrix_has_a_row_for_each_of_the_eleven_rules_and_marks_what_may_not_fit():
    rows = re.findall(r"^\| (\d+) \| \*\*", MATRIX, re.M)
    assert rows == [str(n) for n in range(1, 12)]
    assert "No agronomic or veterinary review" in MATRIX and "General guidance may not fit a given farm" in MATRIX
    assert "**No.**" in MATRIX  # at least one threshold marked as not fitting every farm


def test_the_build_history_is_a_table_of_commits_per_day_with_the_first_and_latest_date():
    text = results.history_text([("2026-09-27", 9), ("2026-09-28", 2)])
    assert "first commit is dated 2026-09-27 and the latest 2026-09-28; 11 commits on 2 days" in text
    assert "| 2026-09-27 | 9 |" in text
    assert "The count does not include the commit that saves this page." in text
    assert "not recorded" in results.history_text([])
    assert "## 8. Build history" in _render([])


def test_the_history_comes_from_git_and_is_sorted_oldest_first():
    days = results.git_history()
    assert days and days == sorted(days)
    assert days[0][0] == "2026-09-27" and all(n > 0 for _d, n in days)
