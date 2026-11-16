"""Command line: python -m dealagent <command>."""
from __future__ import annotations

import argparse
import os
import sys

from . import approval
from .agent import ClaudeBrain, ScriptedBrain, review_deal
from .data import generate, read_csvs, write_csvs
from .metrics import Store, deal_metrics
from .rules import verdict
from .tools import ToolBox

DATA = os.environ.get("DEAL_AGENT_DATA", "data")
PROPOSALS = os.environ.get("DEAL_AGENT_PROPOSALS", os.path.join("runs", "proposals.jsonl"))


def _store() -> Store:
    if not os.path.exists(os.path.join(DATA, "deals.csv")):
        sys.exit(f"No data in '{DATA}'. Run: python -m dealagent generate")
    return Store(read_csvs(DATA))


def scoreboard(store: Store) -> str:
    head = ("| Deal | SKU | Units spike | GMS spike | Investment % of GMS | Incremental profit | ROI | Action |\n"
            "|---|---|---|---|---|---|---|---|")
    lines = [head]
    for deal_id in sorted(store.deals):
        m = deal_metrics(store, deal_id)
        lines.append(f"| {deal_id} | {m['sku']} | {m['units_spike']}x | {m['gms_spike']}x | "
                     f"{m['investment_pct_of_gms']}% | {m['incremental_profit']:,} | {m['roi']} | "
                     f"{verdict(m)['action']} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dealagent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write a synthetic dataset to ./data")
    g.add_argument("--seed", type=int, default=7)
    sub.add_parser("score", help="score every deal (no model involved)")
    r = sub.add_parser("review", help="have the agent review one deal, or all of them")
    r.add_argument("deal_id", help="a deal id such as D-0003, or 'all'")
    r.add_argument("--live", action="store_true", help="use Claude instead of the scripted brain")
    sub.add_parser("proposals", help="list proposals and their status")
    for name in ("approve", "reject"):
        a = sub.add_parser(name, help=f"{name} a proposal")
        a.add_argument("proposal_id")
        a.add_argument("--by", required=True, help="name of the person deciding")
    args = p.parse_args(argv)

    if args.cmd == "generate":
        write_csvs(generate(seed=args.seed), DATA)
        print(f"Synthetic dataset written to {DATA}/")
    elif args.cmd == "score":
        print(scoreboard(_store()))
    elif args.cmd == "review":
        store = _store()
        box = ToolBox(store, PROPOSALS)
        brain = ClaudeBrain() if args.live else ScriptedBrain()
        ids = sorted(store.deals) if args.deal_id == "all" else [args.deal_id]
        for deal_id in ids:
            out = review_deal(deal_id, box, brain)
            print(f"{out['summary'] or deal_id + ': stopped (' + out['stopped'] + ')'}  [{out['steps']} steps, proposal {out['proposal']}]")
    elif args.cmd == "proposals":
        for r_ in approval.list_all(PROPOSALS):
            print(f"{r_['proposal_id']}  {r_['deal_id']}  {r_['action']:<12} {r_['status']:<9} {r_['decided_by'] or ''}")
            print(f"    {r_['rationale']}")
    else:
        row = approval.decide(PROPOSALS, args.proposal_id, args.by, approve=(args.cmd == "approve"))
        print(f"{row['proposal_id']} {row['status']} by {row['decided_by']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
