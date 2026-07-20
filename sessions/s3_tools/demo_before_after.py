"""
demo_before_after.py — a classroom demo: PROMPTING (Session 1) vs TOOLS (Session 3).

Runs a handful of handpicked cases through both agents and prints, side by side:
  ① the prompting-only response, and its grounded score
  ② the tool-using response, its grounded score, AND exactly how it got there —
     each step, whether calls ran in parallel, the arguments, and the tool outputs.

The last case (audit logs) is included on purpose: tools are NOT enough for it, which
motivates RAG (Session 4).

    python3 sessions/s3_tools/demo_before_after.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from sessions.s1_classifier.agent import classify as classify_prompt
from sessions.s3_tools.agent import classify as classify_tools
from tools.tools import REGISTRY
from eval.scoring import score_case

# Handpicked teaching cases, selected by NAME (not numeric id, which shifts as cases are added).
# First five: tools clearly win. Last: tools aren't enough → RAG.
CASE_KEYS = [
    "double_charge",           # multi-hop: get_invoices → check_refund_eligibility → refund
    "duplicate_old",           # tricky: duplicate is >14 days old → still refundable (policy beats window)
    "refund_old_ineligible",   # correctly REFUSES using the eligibility policy + a looked-up date
    "sso_on_pro",              # kills a confident hallucination
    "past_due",                # ground-truth status only in the system
    "data_recovery_overreach", # grounds a "no" in the real retention window
    "audit_broken_enterprise", # tools NOT enough — facts live in a doc → needs RAG
]

# ── pretty-print helpers ──────────────────────────────────────────────────────
C = {"dim": "\033[2m", "b": "\033[1m", "g": "\033[32m", "r": "\033[31m",
     "y": "\033[33m", "cy": "\033[36m", "x": "\033[0m"}


def _fmt_args(args):
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def _indent(text, pad="          "):
    return "\n".join(pad + line for line in text.splitlines())


def _run_quiet(fn, *a, **k):
    """Run an agent/tool while swallowing its stdout (e.g. [ACTION] logs)."""
    with redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def _show_tool_journey(tool_calls):
    """Group logged calls by step; re-run each (deterministic) to show its output."""
    steps = {}
    for tc in tool_calls:
        steps.setdefault(tc["step"], []).append(tc)

    for step, calls in sorted(steps.items()):
        kind = f"{len(calls)} calls IN PARALLEL" if len(calls) > 1 else "1 call"
        print(f"    {C['y']}Step {step}{C['x']}  [{kind}]")
        for tc in calls:
            print(f"      {C['cy']}• {tc['tool']}({_fmt_args(tc['args'])}){C['x']}")
            out = _run_quiet(REGISTRY[tc["tool"]], **tc["args"])
            pretty = json.dumps(out, indent=2, default=str)
            print(f"{C['dim']}{_indent(pretty)}{C['x']}")


# ── main ──────────────────────────────────────────────────────────────────────
def _first_case(all_cases, key):
    """Find the first case whose id ends with this name key (e.g. 'sso_on_pro')."""
    for c in all_cases:
        if c["id"].split("_", 2)[-1] == key:
            return c
    raise KeyError(f"no case matching key {key!r}")


def main():
    all_cases = json.load(open(os.path.join(ROOT, "data", "train.json")))

    for key in CASE_KEYS:
        c = _first_case(all_cases, key)
        ctx = c["customer_context"]

        p = _run_quiet(classify_prompt, c["ticket"], ctx)
        t = _run_quiet(classify_tools, c["ticket"], ctx)
        ps = score_case(p, c, use_judge=True)
        ts = score_case(t, c, use_judge=True)

        print("\n" + "═" * 92)
        print(f"{C['b']}{c['id']}{C['x']}   plan={ctx.get('plan')}")
        print(f"{C['b']}TICKET:{C['x']} {c['ticket']}")
        print(f"{C['dim']}expected the answer to convey: {c['expected'].get('must_mention') or '(doc facts)'}{C['x']}")

        print(f"\n{C['r']}① PROMPTING ONLY (Session 1, no tools){C['x']}")
        print(f"   routing: {p.get('category')} / {p.get('priority')} / human={p.get('requires_human')}")
        print(f"   answer : {p.get('answer')}")
        print(f"   {C['b']}grounded score: {ps['dims']['grounded']}{C['x']}")

        print(f"\n{C['g']}② TOOL-USING AGENT (Session 3){C['x']}")
        print(f"   routing: {t.get('category')} / {t.get('priority')} / human={t.get('requires_human')}")
        print(f"   answer : {t.get('answer')}")
        print(f"   {C['b']}grounded score: {ts['dims']['grounded']}{C['x']}")
        print(f"\n   {C['b']}How it got there — tool journey:{C['x']}")
        if t.get("tool_calls"):
            _show_tool_journey(t["tool_calls"])
        else:
            print("    (no tools called)")

    print("\n" + "═" * 92)
    print(f"{C['y']}Note:{C['x']} the last case calls tools but still can't fully answer — its facts live in a")
    print("knowledge-base document, not a tool result. That gap is what RAG (Session 4) fills.\n")


if __name__ == "__main__":
    main()
