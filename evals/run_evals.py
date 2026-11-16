"""Eval gate: does the full pipeline reach the planted answer, with grounded reasons?

Each synthetic deal is generated from a known archetype (winner, fixable, dud, thin data).
The agent must reach the matching action, record exactly one proposal, and quote only numbers
that exist in its tool results. Run over several seeds so one lucky dataset cannot pass the gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dealagent import approval                      # noqa: E402
from dealagent.agent import ScriptedBrain, review_deal  # noqa: E402
from dealagent.data import EXPECTED_ACTION, generate   # noqa: E402
from dealagent.grounding import ungrounded_numbers     # noqa: E402
from dealagent.metrics import Store                    # noqa: E402
from dealagent.tools import ToolBox                    # noqa: E402

SEEDS = [7, 11, 23, 42, 101]


def run(seeds=SEEDS) -> dict:
    total = correct = grounded = 0
    misses = []
    for seed in seeds:
        dataset = generate(seed=seed)
        store = Store(dataset)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "proposals.jsonl")
            box = ToolBox(store, path)
            for deal in dataset["deals"]:
                out = review_deal(deal["deal_id"], box, ScriptedBrain())
                proposals = [p for p in approval.list_all(path) if p["deal_id"] == deal["deal_id"]]
                want = EXPECTED_ACTION[deal["archetype"]]
                got = proposals[0]["action"] if len(proposals) == 1 and out["stopped"] == "done" else None
                total += 1
                if got == want:
                    correct += 1
                else:
                    misses.append({"seed": seed, "deal": deal["deal_id"], "want": want, "got": got})
                if proposals and not ungrounded_numbers(
                        proposals[0]["rationale"], box.seen[deal["deal_id"]], *box.benchmarks.values()):
                    grounded += 1
    return {"cases": total, "action_accuracy": round(correct / total, 3),
            "grounded_rate": round(grounded / total, 3), "misses": misses}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.9)
    args = ap.parse_args()
    result = run()
    result["gate"] = "PASS" if (result["action_accuracy"] >= args.threshold
                                and result["grounded_rate"] == 1.0) else "FAIL"
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["gate"] == "PASS" else 1)
