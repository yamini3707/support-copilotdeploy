# CloudDesk Support Copilot — the deployable capstone

Everything built across the course, composed into one traced service.

## The request lifecycle (`app/pipeline.py`)

```
POST /ticket
  1. MEMORY RECALL   → unified (embedding + graph) recall for this customer, injected as context
  2. AGENT           → router → specialist → scoped tools + unified RAG (s9)
                       · access-control guardrail enforced inside the tool dispatch
  3. OUTPUT GUARDRAIL→ disclosure filter scrubs the reply before it reaches the customer
  4. MEMORY FORMATION→ distill the finished ticket into durable facts + an episodic record
```
The whole call is one Langfuse span (`support_copilot`); agent, RAG, tools and memory nest under it.

## Where each capability lives

| Capability | Course origin | In the app |
|---|---|---|
| Router + specialists | s4 | `app/agent.py` |
| Structured tools | s3 | `tools/` via `app/agent.py` |
| Unified RAG (hybrid+HyDE+graph+parent-child, rerank, abstain) | s5–s9 | `search_knowledge_base` in `app/agent.py` |
| Access control (whose-data) | guardrails/access_control | `_run_tool` in `app/agent.py` |
| Output redaction | guardrails/output_redaction | `app/guardrails.py` |
| Ingest visibility (deterministic backstop) | guardrails/ingest_visibility | RAG/ingest layer (see note) |
| Long-term memory (recall + formation + graph) | memory/ | `app/memory_service.py` |
| Langfuse tracing | s7 onward | instrumented client in `app/agent.py`, `@observe` spans |

## Endpoints
- `POST /ticket` — `{ticket, customer_id, plan, region, form_memory}` → reply + `trace`
- `GET /health` — liveness probe
- `GET /eval?limit=8&judge=true` — run the harness, return the per-dimension scoreboard (eval-driven, live)
- `GET /docs` — Swagger UI (click-to-test)

## Run locally
```bash
pip install -r ../requirements.txt
# .env must have OPENAI_API_KEY, WEAVIATE_URL/API_KEY, LANGFUSE_PUBLIC/SECRET_KEY(/HOST)
uvicorn app.server:app --reload      # run from the support-copilot/ dir
```

## Deploy (Render)
1. Push the repo (exclude `.env`). `render.yaml` defines a free Python web service.
2. Create a Blueprint from the repo; set the secret env vars in the dashboard.
3. Start command: `uvicorn app.server:app --host 0.0.0.0 --port $PORT`.

## Notes / limitations
- **Memory is in-memory (ephemeral):** seeded on boot from `world_state` + a rich Acme demo fixture
  (`cust_enterprise_003`, carries the multi-hop graph showcase); new memories reset on restart.
- **RAG needs a populated Weaviate Cloud cluster.** KB answers only work if the s9 corpus is ingested
  in the cluster your env points to.
- **Per-customer memory graphs are built lazily and cached**, invalidated on write — the first ticket
  for a customer warms it, the rest are fast.
- **Ingest-visibility** filtering is the deterministic ingest-side layer; the live output disclosure
  filter is its paraphrase-proof complement. Wiring the `visibility` filter into `unified_search`
  requires the corpus to be re-ingested with the visibility split (see `guardrails/ingest_visibility`).
