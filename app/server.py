"""
The CloudDesk Support Copilot API.

    POST /ticket   → run one ticket end to end (memory + agent + guardrails), return the reply + trace
    GET  /health   → liveness probe for the platform
    GET  /eval     → run the eval harness over data/train.json and return the per-dimension scoreboard
                     (the eval-driven story, live: watch each capability's score). ?limit=N&judge=bool
    GET  /docs     → auto-generated Swagger UI (click-to-test)

The heavy machinery (agent graph, unified RAG, memory boot) is loaded LAZILY, not at import: uvicorn
imports this module before it binds the port, so importing the pipeline here would delay the port
bind and make the platform report "no open ports detected". Instead we bind fast (this module is
light) and load the pipeline on first use — with a background warm-up so the first real request isn't
cold. /health answers immediately regardless.

Run locally:  uvicorn app.server:app --reload
"""

import os
import sys
import threading

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import TicketRequest, TicketResponse

app = FastAPI(title="CloudDesk Support Copilot",
              description="Router + specialists + tools + unified RAG + guardrails + memory, Langfuse-traced.",
              version="1.0")

# allow the standalone HTML tester (and any browser client) to call the API cross-origin
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_lock = threading.Lock()
_fns = {}                                   # lazily filled with the heavy pipeline callables


def _pipeline():
    """Import + initialise the full pipeline on first use (thread-safe)."""
    if not _fns:
        with _lock:
            if not _fns:
                from app.pipeline import handle_ticket, flush   # triggers the heavy import chain + memory boot
                _fns["handle_ticket"], _fns["flush"] = handle_ticket, flush
    return _fns


# warm the pipeline in the background so the port binds now and the first /ticket isn't cold
threading.Thread(target=_pipeline, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "model": os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"),
            "ready": bool(_fns)}


@app.post("/ticket", response_model=TicketResponse)
def ticket(req: TicketRequest):
    fns = _pipeline()
    try:
        ctx = {"customer_id": req.customer_id, "plan": req.plan, "region": req.region}
        out = fns["handle_ticket"](req.ticket, ctx, form_memory=req.form_memory)
        fns["flush"]()
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/eval")
def run_eval(limit: int = 8, judge: bool = True):
    """Run the harness (read-only: memory is recalled but NOT written) and summarize scores per dimension."""
    fns = _pipeline()
    from eval.harness import evaluate
    from eval.scoring import WEIGHTS

    data = os.path.join(ROOT, "data", "train.json")
    classify = lambda t, c: fns["handle_ticket"](t, c, form_memory=False)   # read-only during eval
    cases, results = evaluate(classify, data, use_judge=judge)
    if limit:
        results = results[:limit]

    dims = list(WEIGHTS)                 # category, priority, requires_human, tool_use, retrieval, grounded, memory
    per_dim = {}
    for d in dims:
        vals = [r["dims"].get(d) for r in results if r.get("dims", {}).get(d) is not None]
        per_dim[d] = round(sum(vals) / len(vals), 3) if vals else None
    composite = round(sum(r["composite"] for r in results) / len(results), 3) if results else 0.0
    fns["flush"]()
    return {
        "cases_run": len(results),
        "weights": WEIGHTS,
        "per_dimension": per_dim,
        "composite": composite,
        "cases": [{"id": r["id"], "composite": round(r["composite"], 3),
                   "safety": r.get("safety"), "answer": r["answer"][:200]} for r in results],
    }
