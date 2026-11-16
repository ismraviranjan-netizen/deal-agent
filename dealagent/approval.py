"""Proposals wait in a file until a named person approves or rejects them."""
from __future__ import annotations

import json
import os


def _load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _save(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def add(path: str, proposal: dict) -> dict:
    rows = _load(path)
    proposal = dict(proposal, proposal_id=f"PRP-{len(rows) + 1:04d}", status="pending", decided_by=None)
    rows.append(proposal)
    _save(path, rows)
    return proposal


def list_all(path: str) -> list[dict]:
    return _load(path)


def decide(path: str, proposal_id: str, by: str, approve: bool) -> dict:
    if not by.strip():
        raise ValueError("A named person must make the decision.")
    rows = _load(path)
    for r in rows:
        if r["proposal_id"] == proposal_id:
            if r["status"] != "pending":
                raise ValueError(f"{proposal_id} is already {r['status']}.")
            r["status"] = "approved" if approve else "rejected"
            r["decided_by"] = by
            _save(path, rows)
            return r
    raise KeyError(proposal_id)
