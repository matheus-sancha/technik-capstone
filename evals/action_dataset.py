"""Write evals/action_dataset.json, the eval set in the format microsoft/ai-agent-evals reads.

The Action invokes the deployed agent with each query and runs Foundry's judges on the answers, so it
gets the questions and ground truths only. The tool-call and facts checks stay in evals/run.py.
Run from agent/ after changing eval_set.jsonl: uv run ../evals/action_dataset.py
"""
import json
from pathlib import Path

EVALS = Path(__file__).parent
DATASET = EVALS / "action_dataset.json"
EVALUATORS = ["builtin.intent_resolution", "builtin.task_adherence", "builtin.tool_call_accuracy"]


def dataset():
    cases = [json.loads(line) for line in (EVALS / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()]
    return {"name": "technik-production-assistant", "evaluators": EVALUATORS,
            "data": [{"query": c["query"], "ground_truth": c["ground_truth"]} for c in cases]}


if __name__ == "__main__":
    DATASET.write_text(json.dumps(dataset(), indent=2) + "\n", encoding="utf-8")
