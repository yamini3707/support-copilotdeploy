# GraphRAG, from scratch

A small, self-contained **knowledge-graph RAG**: build a graph from a few incident postmortems,
link a user query to graph entities, traverse to the connected documents, and answer — beating plain
vector RAG on a **multi-hop** question ("has this same root cause hit us before, and how do we
prevent it?"). Every script narrates each step with the *reason why*, so you can watch it think.

## Setup
```bash
pip install openai numpy python-dotenv
export OPENAI_API_KEY=sk-...        # or put it in a .env at the repo root
```

## Run (in order, from the repo root)
```bash
python3 sessions/s8_graphrag/build_graph.py   # extract triples -> resolve entities/relations -> graph.json
python3 sessions/s8_graphrag/link_query.py    # a query -> the graph entities it mentions (seeds)
python3 sessions/s8_graphrag/retrieve.py      # seeds -> traverse the graph -> docs (checked vs gold)
python3 sessions/s8_graphrag/generate.py      # docs -> grounded answer, vs a vector-RAG baseline
```
Set `VERBOSE = False` in `log.py` for headline-only output.

## What each file does
| File | Role |
|---|---|
| `build_graph.py` | **Build the graph** — LLM extracts `(subject, relation, object)` triples, then *hybrid entity resolution*: `identifier` entities match **exactly** (INC-2041 ≠ INC-2042); `descriptive` entities are matched by **embedding shortlist → LLM decides**; relations snap to a **closed set**. Saves `graph.json`. |
| `link_query.py` | **Query → seeds** — LLM pulls entity names from the query, then resolves each to a graph node (exact → embed-shortlist → LLM decide). |
| `retrieve.py` | **Seeds → docs** — BFS the graph from the seeds, collect docs by edge provenance, check recall against gold. |
| `generate.py` | **Docs → answer** — grounded answer, contrasted with a plain vector-RAG baseline (which misses the connection). |
| `embeddings.py` | tiny OpenAI-embeddings cache. `log.py` — the narrated logger. `docs/` — the 5 source documents. `graph.json` — the built graph. |

## The key idea to play with
The graph connects two incidents that share a root cause but are **worded differently** — something
vector search can't link. Things to try:
- change the **entity types / relations / `SHORTLIST`** threshold in `build_graph.py`,
- change **`HOPS`** in `retrieve.py` (fewer = more precise, more = broader recall),
- drop your **own docs** into `docs/` and rebuild.

Depends on the repo's `eval/` package (retry + LLM judge) — no other project code needed.
