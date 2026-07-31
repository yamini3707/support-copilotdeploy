"""
The unified retrieval pipeline — DIVIDE (parallel strategies) then CONQUER (merge, rerank, abstain).

  unified_search(query, plan):
    1. run hybrid + hyde + graph IN PARALLEL (thread pool), each applying the plan filter
    2. merge + dedupe by doc_id (tracking which strategies found each; a child's doc_id == its doc)
    3. LLM rerank the merged pool
    4. CRAG abstention gate — if nothing relevant, say so
    5. return the top-N docs (full text from the corpus) for the agent's next turn

Everything is a Langfuse span; the OTel context is propagated into the worker threads so the parallel
strategies nest correctly under the trace.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from opentelemetry import context as otel_ctx
from langfuse import observe
from eval.retry import call_with_retry
from sessions.s9_rag_final import strategies, kb_index
from sessions.s9_rag_final import log as L

TOP_N = 5
NAMED = [("hybrid", strategies.hybrid_strategy),
         ("hyde", strategies.hyde_strategy),
         ("graph", strategies.graph_strategy)]


@observe(name="rerank")
def _rerank(query, candidates):
    if len(candidates) <= 1:
        return candidates
    listing = "\n".join(f"[{i}] ({c['doc_id']}) {c['text'][:200]}" for i, c in enumerate(candidates))
    system = ("Rank the passages by how well each ANSWERS the query. "
              'Return JSON {"order": [indices, best first]} covering ALL indices.')
    from openai import OpenAI
    try:
        resp = call_with_retry(OpenAI().chat.completions.create,
            model=os.getenv("SUPPORT_COPILOT_RERANK_MODEL", "gpt-4o-mini"), temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": f"Query: {query}\n\nPassages:\n{listing}"}])
        order = json.loads(resp.choices[0].message.content).get("order", [])
    except Exception:
        order = []
    seen, ranked = set(), []
    for i in order:
        if isinstance(i, int) and 0 <= i < len(candidates) and i not in seen:
            ranked.append(candidates[i]); seen.add(i)
    ranked += [c for j, c in enumerate(candidates) if j not in seen]     # keep any the LLM dropped
    return ranked


@observe(name="abstain")
def _abstain(query, docs):
    if not docs:
        return True
    ctx = "\n\n".join(f"[{d['doc_id']}] {d['text'][:1200]}" for d in docs)   # judge the full top-N (ample text)
    system = ("Decide whether the passages DIRECTLY answer the specific customer question. A passage "
              "that is merely on a related topic, or that assumes/implies an answer without stating "
              "it, does NOT count. If none of the passages actually contain the specific information "
              'asked for, set can_answer false. Return JSON {"can_answer": true|false}.')
    from openai import OpenAI
    try:
        resp = call_with_retry(OpenAI().chat.completions.create,
            model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": f"QUESTION: {query}\n\nPASSAGES:\n{ctx}"}])
        return not json.loads(resp.choices[0].message.content).get("can_answer", True)
    except Exception:
        return False       # fail open — don't abstain on grader error


@observe(name="unified_search")
def unified_search(query, plan=None):
    L.step(f"unified_search(query={query!r}, plan={plan})",
           why="the agent decided the plan filter; now we DIVIDE across strategies, then CONQUER.")

    kb_index.warm()          # connect once from the main thread before the threads race to connect

    # 1) run the strategies in parallel; carry the trace context into each worker thread
    parent_ctx = otel_ctx.get_current()

    def run(fn):
        token = otel_ctx.attach(parent_ctx)              # so the strategy's span nests under this trace
        try:
            return fn(query, plan)
        finally:
            otel_ctx.detach(token)

    L.step("DIVIDE: run hybrid + hyde + graph in parallel (each applies the plan filter)",
           why="the three strategies find different things (lexical, semantic, relational); running "
               "them together and combining beats any one retriever alone.")
    with ThreadPoolExecutor(max_workers=len(NAMED)) as ex:
        futs = {name: ex.submit(run, fn) for name, fn in NAMED}
        results = {name: f.result() for name, f in futs.items()}
    for name, hits in results.items():
        L.detail(f"{name}: {len(hits)} hits -> {[d for d, _, _ in hits][:5]}")

    # 2) merge + dedupe by doc_id (a child's doc_id already IS its document)
    L.step("CONQUER: merge + dedupe by doc_id, tracking which strategies found each doc",
           why="the same doc surfacing via several strategies is a strong relevance signal; we keep the "
               "longest snippet and the union of sources.")
    merged = {}
    for name, hits in results.items():
        for doc_id, text, score in hits:
            e = merged.setdefault(doc_id, {"doc_id": doc_id, "text": text, "sources": set(), "score": 0.0})
            e["sources"].add(name)
            e["score"] = max(e["score"], score)
            if len(text) > len(e["text"]):
                e["text"] = text
    candidates = list(merged.values())
    L.detail(f"merged -> {len(candidates)} unique docs")

    # 3) rerank — but TRUST graph connections: graph-found docs are relevant *by structure* even when
    #    they read nothing like the query, so keep them and only semantic-rerank the rest.
    graph_docs = [c for c in candidates if "graph" in c["sources"]]
    others = [c for c in candidates if "graph" not in c["sources"]]
    L.step(f"rerank graph-first: pin {len(graph_docs)} graph doc(s), LLM-rerank the other "
           f"{len(others)} by the query",
           why="graph docs are relevant BY STRUCTURE even when they read nothing like the query, so a "
               "semantic reranker would wrongly bury them — we pin them and only rerank the rest.")
    ranked = (graph_docs + _rerank(query, others))[:TOP_N]
    L.detail(f"final top-{TOP_N} (graph-first): {[c['doc_id'] for c in ranked]}")

    # 4) keep the MATCHED retrieval unit (chunk / parent block / graph slice) — NOT the whole document,
    #    so we don't pollute the context with unrelated sections.
    docs = [{"doc_id": c["doc_id"], "sources": sorted(c["sources"]), "text": c["text"]} for c in ranked]

    # 5) abstention gate — judged on the retrieved units
    abstain = _abstain(query, docs)
    L.step(f"CRAG abstention gate -> abstain={abstain}",
           why="if the retrieved passages don't DIRECTLY answer the question, we return nothing rather "
               "than let the agent fabricate from loosely-related text.")
    return {"abstain": True, "docs": []} if abstain else {"abstain": False, "docs": docs}
