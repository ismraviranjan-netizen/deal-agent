import json

import pytest

from dealagent import approval
from dealagent.agent import MAX_STEPS, ScriptedBrain, review_deal
from dealagent.data import generate
from dealagent.grounding import numbers_in, ungrounded_numbers
from dealagent.metrics import Store
from dealagent.tools import ToolBox


@pytest.fixture
def box(tmp_path):
    return ToolBox(Store(generate(seed=7)), str(tmp_path / "proposals.jsonl"))


def test_scripted_review_records_one_grounded_proposal(box):
    out = review_deal("D-0001", box)
    assert out["stopped"] == "done" and out["proposal"] == "PRP-0001"
    rows = approval.list_all(box.proposals_path)
    assert len(rows) == 1 and rows[0]["status"] == "pending"
    assert rows[0]["action"] == box.seen["D-0001"]["rule_action"]


def test_cannot_propose_before_looking(box):
    res = box.call("propose_action", {"deal_id": "D-0001", "action": "REPEAT", "rationale": "Looks fine."})
    assert "error" in res and approval.list_all(box.proposals_path) == []


def test_cannot_override_the_rule(box):
    m = box.call("get_deal_metrics", {"deal_id": "D-0001"})
    wrong = "STOP" if m["rule_action"] != "STOP" else "REPEAT"
    res = box.call("propose_action", {"deal_id": "D-0001", "action": wrong, "rationale": "I disagree."})
    assert "not yours to override" in res["error"]


def test_invented_numbers_are_rejected(box):
    m = box.call("get_deal_metrics", {"deal_id": "D-0001"})
    res = box.call("propose_action", {"deal_id": "D-0001", "action": m["rule_action"],
                                      "rationale": "Units rose 987.6x and profit was 123456789."})
    assert "not in the tool results" in res["error"]
    assert approval.list_all(box.proposals_path) == []


def test_unknown_deal_returns_an_error_not_a_crash(box):
    assert "error" in box.call("get_deal_metrics", {"deal_id": "D-9999"})
    assert "error" in box.call("no_such_tool", {})


def test_kill_switch_stops_before_any_step(box, monkeypatch):
    monkeypatch.setenv("DEAL_AGENT_KILL", "1")
    out = review_deal("D-0001", box)
    assert out["stopped"] == "kill_switch" and out["steps"] == 0
    assert approval.list_all(box.proposals_path) == []


def test_step_cap_stops_a_brain_that_never_finishes(box):
    class Looper:
        def reply(self, messages):
            return {"stop_reason": "tool_use", "output_tokens": 10, "content": [
                {"type": "tool_use", "id": "x", "name": "get_deal_metrics", "input": {"deal_id": "D-0001"}}]}
    out = review_deal("D-0001", box, Looper())
    assert out["stopped"] == "step_cap" and out["steps"] == MAX_STEPS and out["proposal"] is None


def test_token_budget_stops_a_wasteful_brain(box):
    class Chatty:
        def reply(self, messages):
            return {"stop_reason": "tool_use", "output_tokens": 5000, "content": [
                {"type": "tool_use", "id": "x", "name": "get_deal_metrics", "input": {"deal_id": "D-0001"}}]}
    assert review_deal("D-0001", box, Chatty())["stopped"] == "budget"


def test_approval_needs_a_name_and_is_final(box):
    review_deal("D-0001", box)
    with pytest.raises(ValueError):
        approval.decide(box.proposals_path, "PRP-0001", " ", approve=True)
    row = approval.decide(box.proposals_path, "PRP-0001", "Asha Rao", approve=True)
    assert row["status"] == "approved" and row["decided_by"] == "Asha Rao"
    with pytest.raises(ValueError):
        approval.decide(box.proposals_path, "PRP-0001", "Asha Rao", approve=False)


def test_number_extraction_ignores_ids():
    assert numbers_in("D-0007 on SKU-0012 ran at 2.5x for 1,200 units, ROI -0.4.") == [2.5, 1200.0, -0.4]
    assert ungrounded_numbers("ran at 2.5x", {"units_spike": 2.5}) == []
    assert ungrounded_numbers("ran at 2.9x", {"units_spike": 2.5}) == [2.9]


def test_tool_results_are_json_serialisable(box):
    json.dumps(box.call("get_deal_metrics", {"deal_id": "D-0002"}))
    json.dumps(box.call("get_category_benchmark", {"category": "Toys"}))


def test_reviewing_a_deal_twice_does_not_duplicate_the_proposal(box):
    first = review_deal("D-0001", box)
    second = review_deal("D-0001", box)
    assert first["proposal"] == second["proposal"] == "PRP-0001"
    assert "already waiting" in second["summary"]
    assert len(approval.list_all(box.proposals_path)) == 1
    # once a person has decided, a fresh review may propose again
    approval.decide(box.proposals_path, "PRP-0001", "Asha Rao", approve=False)
    assert review_deal("D-0001", box)["proposal"] == "PRP-0002"
