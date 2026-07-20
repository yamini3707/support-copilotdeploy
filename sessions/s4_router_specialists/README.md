# Session 4 — Router → Specialists with LangGraph

**Milestone:** stop stuffing every category's edge cases into one giant prompt. Split the agent
into a **router** and per-category **specialists**, wired as a LangGraph graph.
**Big idea:** the win isn't better routing — it's **isolation**. A billing edge-case rule lives in
the billing specialist and *cannot* ripple into technical behaviour, because they're never in the
same context. That's how you handle the long tail of edge cases without the prompt rotting.

---

## The graph

```
START → router → (conditional fan-out) → one or more specialists (parallel) → aggregator → END
```

- **router** (`graph.py:router`) — an LLM emits a confidence per category.
- **fan-out-on-low-margin** — if the top category dominates (`top1 - top2 >= MARGIN`) we run only
  that specialist; if it's a close call we run the tied specialists **in parallel** (LangGraph fans
  out by returning a list of node names from the conditional edge).
- **specialists** (`prompts.py`) — each is a small tool-using loop with its **own** prompt holding
  that category's edge cases. A specialist can **reject a misroute** (`handled: false`).
- **aggregator** — drops rejects, picks the highest-confidence handler, computes priority in code.

LangGraph concepts on display: nodes, conditional edges, **parallel fan-out (multiplex)**,
**fan-in with a reducer** (`Annotated[list, operator.add]` collects parallel specialist outputs),
and a compiled graph invoked per ticket.

## Run it

```bash
python3 sessions/s4_router_specialists/demo_routing.py   # see single vs fan-out decisions (cheap)
python3 sessions/s4_router_specialists/run.py            # full eval through the graph
python3 sessions/s4_router_specialists/run.py --fast      # skip the judge
```

---

## Why this, and when

We reached for this **after** the monolith started to strain: adding account edge cases
(seat-ceiling, blocked-downgrade, over-provisioned) meant piling more into one prompt, risking
ripple. The senior-engineer order of fixes still holds — **tool/data → general principle → code →
specific rule** — and only when specific rules multiply do you split into specialists.

- The account edge cases now live in the **account specialist**; they fixed `blocked_downgrade`
  (0.29 → ~0.74, using the new `get_plan_catalog` tool to compare against Pro's seat cap) and
  `over_provisioned` (0.29 → ~0.96) **without touching** the billing or technical prompts.
- Fan-out is a **rare fallback** for genuine ambiguity, not the default — it multiplies cost, so
  it should only fire on close calls.

## The threshold (`MARGIN`) — tune it, don't guess

Fan-out triggers when `top1 - top2 < MARGIN` (default 0.25, overridable via `ROUTER_MARGIN`). The
right value is an **eval question**: sweep it and watch routing accuracy vs. fan-out rate (cost),
then pick the knee. LLM confidences are poorly calibrated, so we rely on the **margin** (a relative
gap) rather than absolute scores.

## Deliberate knowledge gap

- Confidence calibration is imperfect — the margin heuristic manages it, but a mis-calibrated
  router will over- or under-fan-out. Tuning `MARGIN` on the eval is the mitigation.
- The aggregator picks by self-reported specialist confidence; a tie-break judge could be added if
  that proves unreliable (add it last — it's another call and another judgment surface).
