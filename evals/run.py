"""Stage 4: run the evaluation set through the agent, grade it, and compare against the baseline.

Run from agent/, which holds Agent Framework:
  uv run ../evals/run.py --offline     replayed model, fake Snowflake: what CI runs
  uv run ../evals/run.py               the Foundry model, real Snowflake, plus Foundry's judges
Add --update-baseline to accept this run as the new baseline. Exits 1 on a regression.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

EVALS = Path(__file__).parent
AGENT = EVALS.parent / "agent"
sys.path[:0] = [str(AGENT), str(AGENT / "tests")]

from agent_framework import (  # noqa: E402
    CheckResult, ExpectedToolCall, LocalEvaluator, evaluate_agent, evaluator, tool_call_args_match,
    tool_calls_present)
from dotenv import load_dotenv  # noqa: E402
from fake_model import FakeChatClient  # noqa: E402
from main import ROOT, TOOL_LOOP, build_agent, teamcenter_server  # noqa: E402

CASES = [json.loads(line) for line in (EVALS / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()]
BY_QUERY = {case["query"]: case for case in CASES}
BASELINE = EVALS / "baseline.json"


@evaluator
def facts_present(query: str, response: str) -> CheckResult:
    """Every must_include entry appears in the answer; "a|b" accepts either wording."""
    missing = [want for want in BY_QUERY[query]["must_include"]
               if not any(alt.lower() in response.lower() for alt in want.split("|"))]
    return CheckResult(passed=not missing, check_name="facts_present",
                       reason=f"missing {missing}" if missing else "all facts present")


class ReplayChatClient(FakeChatClient):
    """Offline stand-in for the model: replays evals/replay.jsonl, picking the script by the question."""

    def __init__(self, scripts=None, **kwargs):
        super().__init__(**kwargs)
        lines = (EVALS / "replay.jsonl").read_text(encoding="utf-8").splitlines()
        self.scripts = scripts or {s["id"]: s for s in map(json.loads, lines)}

    async def _inner_get_response(self, *, messages, **kwargs):
        script = self.scripts[BY_QUERY[next(m.text for m in messages if m.role == "user")]["id"]]
        self.calls, self.answer = script["calls"], script["answer"]
        return await super()._inner_get_response(messages=messages, **kwargs)


async def run(offline, scripts=None):
    graders = [LocalEvaluator(tool_calls_present, tool_call_args_match, facts_present)]
    if offline:
        client = ReplayChatClient(scripts, function_invocation_configuration=TOOL_LOOP)
        server = teamcenter_server(args=("run", "--directory", str(ROOT), "tests/fake_server.py"))
    else:
        from agent_framework.foundry import FoundryChatClient, FoundryEvals
        from azure.identity.aio import AzureCliCredential
        client = FoundryChatClient(credential=AzureCliCredential(), function_invocation_configuration=TOOL_LOOP)
        server = teamcenter_server()
        graders.append(FoundryEvals(client=client, evaluators=[
            FoundryEvals.INTENT_RESOLUTION, FoundryEvals.TASK_ADHERENCE, FoundryEvals.TOOL_CALL_ACCURACY]))
    async with server:
        return await evaluate_agent(
            agent=build_agent(client, server), queries=[c["query"] for c in CASES],
            expected_output=[c["ground_truth"] for c in CASES],
            expected_tool_calls=[[ExpectedToolCall(t["name"], t["arguments"]) for t in c["expected_tool_calls"]]
                                 for c in CASES],
            evaluators=graders, eval_name="technik-production-assistant")


def outcomes(results):
    """Per case: pass only if every grader passed it, with the reasons of the checks that failed."""
    found = {c["id"]: {"status": "pass", "why": []} for c in CASES}
    for provider in results:
        for item in provider.items:
            case = found[BY_QUERY[item.input_text]["id"]]
            if not item.is_passed:
                case["status"] = "error" if item.is_error else "fail"
            case["why"] += [f"{s.name}: {(s.sample or {}).get('reason', 'failed')}"
                            for s in item.scores if s.passed is False]
    return found


def compare(found, baseline):
    """A regression is a case the baseline passes that this run doesn't."""
    return [case for case, then in baseline.items() if then == "pass" and found.get(case, {}).get("status") != "pass"]


def report(mode, found, baseline, regressions):
    now, then = sum(o["status"] == "pass" for o in found.values()), sum(s == "pass" for s in baseline.values())
    lines = [f"## Evals: {mode}", "",
             f"**{now}/{len(found)} pass** (baseline {then}/{len(baseline)}). "
             + (f"**Regressions: {', '.join(regressions)}.**" if regressions else "No regressions."), "",
             "| Case | Category | Baseline | Now | Why it failed |", "|---|---|---|---|---|"]
    for case in CASES:
        o = found[case["id"]]
        why = "<br>".join(re.sub(r"\s+", " ", w) for w in o["why"])
        lines.append(f"| {case['id']} | {case['category']} | {baseline.get(case['id'], 'new')} | {o['status']} | {why} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="replayed model and fake Snowflake")
    parser.add_argument("--update-baseline", action="store_true", help="accept this run as the baseline")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    mode = "offline" if args.offline else "live"
    found = outcomes(asyncio.run(run(args.offline)))
    baselines = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    if args.update_baseline:
        baselines[mode] = {case: o["status"] for case, o in found.items()}
        BASELINE.write_text(json.dumps(baselines, indent=2) + "\n", encoding="utf-8")
    baseline = baselines.get(mode, {})
    regressions = compare(found, baseline)
    text = report(mode, found, baseline, regressions)
    print(text)
    (EVALS / "report.md").write_text(text, encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    sys.exit(1 if regressions else 0)


if __name__ == "__main__":
    main()
