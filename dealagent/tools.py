"""The agent's tools. Each one is a narrow door onto the data or the proposal file."""
from __future__ import annotations

from . import approval
from .grounding import ungrounded_numbers
from .metrics import Store, category_benchmark, deal_metrics
from .rules import ACTIONS, verdict

TOOLS = [
    {
        "name": "get_deal_metrics",
        "description": "Performance and economics of one deal, plus the action the decision rule reaches.",
        "input_schema": {"type": "object", "properties": {"deal_id": {"type": "string"}}, "required": ["deal_id"]},
    },
    {
        "name": "get_category_benchmark",
        "description": "Median units spike, ROI and investment share across all deals in a category.",
        "input_schema": {"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
    },
    {
        "name": "propose_action",
        "description": ("Record one recommended action for a deal, for a human to approve. "
                        "The action must equal the rule_action from get_deal_metrics, and every "
                        "number in the rationale must come from the tool results."),
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "action": {"type": "string", "enum": list(ACTIONS)},
                "rationale": {"type": "string"},
            },
            "required": ["deal_id", "action", "rationale"],
        },
    },
]


class ToolBox:
    def __init__(self, store: Store, proposals_path: str):
        self.store = store
        self.proposals_path = proposals_path
        self.seen: dict[str, dict] = {}        # results the agent has actually looked at
        self.benchmarks: dict[str, dict] = {}

    def call(self, name: str, args: dict) -> dict:
        try:
            return getattr(self, f"_{name}")(**args)
        except (KeyError, TypeError, AttributeError) as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def _get_deal_metrics(self, deal_id: str) -> dict:
        m = deal_metrics(self.store, deal_id)
        v = verdict(m)
        out = dict(m, rule_action=v["action"], rule_reason=v["reason"])
        if v["target_platform_share_pct"] is not None:
            out["target_platform_share_pct"] = v["target_platform_share_pct"]
        self.seen[deal_id] = out
        return out

    def _get_category_benchmark(self, category: str) -> dict:
        b = category_benchmark(self.store, category)
        self.benchmarks[category] = b
        return b

    def _propose_action(self, deal_id: str, action: str, rationale: str) -> dict:
        m = self.seen.get(deal_id)
        if m is None:
            return {"error": "Call get_deal_metrics for this deal before proposing."}
        if action != m["rule_action"]:
            return {"error": f"Action must be {m['rule_action']}; the decision rule is not yours to override."}
        bad = ungrounded_numbers(rationale, m, *self.benchmarks.values())
        if bad:
            return {"error": f"These numbers are not in the tool results: {bad}. Rewrite the rationale."}
        for existing in approval.list_all(self.proposals_path):
            if existing["deal_id"] == deal_id and existing["status"] == "pending":
                return {"already_pending": existing["proposal_id"], "status": "pending",
                        "note": "This deal already has a proposal waiting for a decision. Nothing new was recorded."}
        p = approval.add(self.proposals_path, {
            "deal_id": deal_id, "sku": m["sku"], "action": action, "rationale": rationale,
            "target_platform_share_pct": m.get("target_platform_share_pct"),
        })
        return {"recorded": p["proposal_id"], "status": p["status"]}
