"""
The CloudDesk Support Copilot API.

    POST /ticket   → run one ticket end to end (memory + agent + guardrails), return the reply + trace
    GET  /health   → liveness probe for the platform
    GET  /eval     → run the eval harness over data/train.json and return the per-dimension scoreboard
                     (the eval-driven story, live: watch each capability's score). ?limit=N&judge=bool
    GET  /docs     → auto-generated Swagger UI (click-to-test)

Run locally:  uvicorn app.server:app --reload
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException

from app.pipeline import handle_ticket, flush
from app.schemas import TicketRequest, TicketResponse

app = FastAPI(title="CloudDesk Support Copilot",
              description="Router + specialists + tools + unified RAG + guardrails + memory, Langfuse-traced.",
              version="1.0")


@app.get("/health")
def health():
    return {"status": "ok", "model": os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")}


@app.post("/ticket", response_model=TicketResponse)
def ticket(req: TicketRequest):
    try:
        ctx = {"customer_id": req.customer_id, "plan": req.plan, "region": req.region}
        out = handle_ticket(req.ticket, ctx, form_memory=req.form_memory)
        flush()
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/eval")
def run_eval(limit: int = 8, judge: bool = True):
    """Run the harness (read-only: memory is recalled but NOT written) and summarize scores per dimension."""
    from eval.harness import evaluate
    from eval.scoring import WEIGHTS

    data = os.path.join(ROOT, "data", "train.json")
    classify = lambda t, c: handle_ticket(t, c, form_memory=False)   # read-only during eval
    cases, results = evaluate(classify, data, use_judge=judge)
    if limit:
        results = results[:limit]

    dims = list(WEIGHTS)                 # category, priority, requires_human, tool_use, retrieval, grounded, memory
    per_dim = {}
    for d in dims:
        vals = [r["dims"].get(d) for r in results if r.get("dims", {}).get(d) is not None]
        per_dim[d] = round(sum(vals) / len(vals), 3) if vals else None
    composite = round(sum(r["composite"] for r in results) / len(results), 3) if results else 0.0
    flush()
    return {
        "cases_run": len(results),
        "weights": WEIGHTS,
        "per_dimension": per_dim,
        "composite": composite,
        "cases": [{"id": r["id"], "composite": round(r["composite"], 3),
                   "safety": r.get("safety"), "answer": r["answer"][:200]} for r in results],
    }
