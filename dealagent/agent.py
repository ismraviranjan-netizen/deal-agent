"""One agent loop with two brains: Claude for real runs, a scripted one for tests and evals."""
from __future__ import annotations

import json
import os

from .tools import TOOLS, ToolBox

SYSTEM = (
    "You review e-commerce promotional deals for a marketplace category manager. "
    "For the deal you are given: call get_deal_metrics, call get_category_benchmark for its category, "
    "then call propose_action exactly once. The action must be the rule_action you were given. "
    "Write the rationale in two or three plain sentences a category manager can check. "
    "Quote only numbers that appear in the tool results, and do no arithmetic of your own. "
    "After the proposal is recorded, reply with a one-line summary."
)
MAX_STEPS = 6
MAX_OUTPUT_TOKENS = 4000   # per review; the loop stops when this budget is spent


class ScriptedBrain:
    """Deterministic stand-in for the model. Follows the same tool protocol."""

    def reply(self, messages: list[dict]) -> dict:
        results = {}
        for msg in messages:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        results[block["tool_use_id"]] = json.loads(block["content"])
        deal_id = messages[0]["content"].split()[-1].rstrip(".")
        if "m" not in results:
            return self._use("m", "get_deal_metrics", {"deal_id": deal_id})
        m = results["m"]
        if "b" not in results:
            return self._use("b", "get_category_benchmark", {"category": m["category"]})
        if "p" not in results:
            return self._use("p", "propose_action", {
                "deal_id": deal_id, "action": m["rule_action"],
                "rationale": self._rationale(m, results["b"]),
            })
        return {"stop_reason": "end_turn", "output_tokens": 30,
                "content": [{"type": "text", "text": f"{deal_id}: {m['rule_action']} recorded for approval."}]}

    @staticmethod
    def _use(tool_id: str, name: str, args: dict) -> dict:
        return {"stop_reason": "tool_use", "output_tokens": 60,
                "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": args}]}

    @staticmethod
    def _rationale(m: dict, b: dict) -> str:
        head = (f"Units ran at {m['units_spike']}x baseline and GMS at {m['gms_spike']}x over {m['days']} days, "
                f"against a category median of {b['median_units_spike']}x. ")
        money = (f"The platform invested {m['investment']} ({m['investment_pct_of_gms']}% of deal GMS) "
                 f"for an incremental profit of {m['incremental_profit']}, an ROI of {m['roi']}. ")
        if m["rule_action"] == "RENEGOTIATE":
            tail = (f"The platform funds {m['platform_funding_share_pct']}% of the discount; "
                    f"ask the brand to bring that down to {m['target_platform_share_pct']}% before repeating.")
        elif m["rule_action"] == "TEST_AGAIN":
            tail = f"Only {m['baseline_days']} clean baseline days exist, so rerun it with a proper baseline."
        elif m["rule_action"] == "STOP":
            tail = m["rule_reason"]
        else:
            tail = f"About {m['pull_forward_units']} units were pulled forward from the following week."
        return head + money + tail


class ClaudeBrain:
    """Claude through the Anthropic SDK. Needs `pip install anthropic` and ANTHROPIC_API_KEY."""

    def __init__(self, model: str | None = None):
        import anthropic  # imported here so the offline path has no dependencies
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("DEAL_AGENT_MODEL", "claude-sonnet-5-5")

    def reply(self, messages: list[dict]) -> dict:
        r = self.client.messages.create(
            model=self.model, max_tokens=800, system=SYSTEM, tools=TOOLS, messages=messages)
        content = []
        for block in r.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        return {"stop_reason": r.stop_reason, "output_tokens": r.usage.output_tokens, "content": content}


def review_deal(deal_id: str, toolbox: ToolBox, brain=None) -> dict:
    """Run one review. Returns the transcript summary, including why the loop stopped."""
    if os.environ.get("DEAL_AGENT_KILL") == "1":
        return {"deal_id": deal_id, "stopped": "kill_switch", "steps": 0, "proposal": None, "summary": ""}
    brain = brain or ScriptedBrain()
    messages = [{"role": "user", "content": f"Review deal {deal_id}"}]
    proposal, summary, spent, stopped = None, "", 0, "step_cap"
    for step in range(1, MAX_STEPS + 1):
        out = brain.reply(messages)
        spent += out["output_tokens"]
        messages.append({"role": "assistant", "content": out["content"]})
        calls = [b for b in out["content"] if b["type"] == "tool_use"]
        if not calls:
            summary = " ".join(b["text"] for b in out["content"] if b["type"] == "text")
            stopped = "done"
            break
        results = []
        for c in calls:
            res = toolbox.call(c["name"], c["input"])
            if c["name"] == "propose_action" and "recorded" in res:
                proposal = res["recorded"]
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(res)})
        messages.append({"role": "user", "content": results})
        if spent >= MAX_OUTPUT_TOKENS:
            stopped = "budget"
            break
    return {"deal_id": deal_id, "stopped": stopped, "steps": step, "proposal": proposal,
            "summary": summary, "output_tokens": spent}
