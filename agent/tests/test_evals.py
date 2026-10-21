"""The stage 4 runner, offline: the committed baseline holds, and a worse answer is caught as a regression."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

EVALS = Path(__file__).parent.parent.parent / "evals"
sys.path.insert(0, str(EVALS))

import run as evals  # noqa: E402


def replay():
    lines = (EVALS / "replay.jsonl").read_text(encoding="utf-8").splitlines()
    return {s["id"]: s for s in map(json.loads, lines)}


def baseline():
    return json.loads((EVALS / "baseline.json").read_text(encoding="utf-8"))["offline"]


def test_the_offline_run_matches_the_baseline_and_exits_0():
    done = subprocess.run([sys.executable, str(EVALS / "run.py"), "--offline"], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "No regressions." in done.stdout


def test_the_case_that_fails_on_purpose_is_caught_by_the_grader_not_the_guard():
    found = evals.outcomes(asyncio.run(evals.run(offline=True)))
    assert baseline()["rev-03"] == "fail" and found["rev-03"]["status"] == "fail"
    # The answer was backed by a tool call with the right arguments; only the facts were wrong.
    assert [why.split(":")[0] for why in found["rev-03"]["why"]] == ["facts_present"]


def test_an_answer_from_memory_is_a_regression():
    scripts = replay()
    scripts["rev-01"] = {"calls": [], "answer": "Drawing DU700001042 is at revision C, from ECN70000051."}
    found = evals.outcomes(asyncio.run(evals.run(offline=True, scripts=scripts)))
    # The guard turned it into the refusal, so the facts are missing even though the memory was right.
    assert found["rev-01"]["status"] == "fail"
    assert evals.compare(found, baseline()) == ["rev-01"]


def test_a_known_failure_is_reported_but_does_not_block():
    found = {case: {"status": status, "why": []} for case, status in baseline().items()}
    assert evals.compare(found, baseline()) == []
    assert "| rev-03 | trap | fail | fail |" in evals.report("offline", found, baseline(), [])
