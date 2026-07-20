# RAG Homework — build the retriever, then fix the failures

In class we ended by running `retrieval_failures.py` and watching naive retrieval **fail** on six
kinds of query. That script is in this folder, but it won't run yet — it imports a `rag` package
that **you** are going to build. That's the assignment, in two parts.

> **Rule of the course:** eval-driven. You don't get to *claim* a fix works — you have to *show* the
> recall number move. `rageval.py` (provided) is your scorer. Run it before and after every change.

---

## What you're given

- `kb/` — the knowledge-base corpus (~80 docs: real policy/how-to/troubleshooting docs **plus**
  distractors that look relevant but don't answer). `kb/_manifest.json` has each doc's metadata
  (`doc_id`, `title`, `doc_type`, `plan`).
- `data/rag_cases.json` — the test set: 22 cases across 6 **slices**, each engineered to break naive
  dense retrieval one specific way. Each case has `gold_docs` (the doc that truly answers it),
  `must_mention`, and `answerable` (false for the "should abstain" cases).
- `sessions/s5_rag/retrieval_failures.py` — the failure gallery you saw in class (runs once you've
  built Part A).
- `sessions/s5_rag/rageval.py` — the scorer. Call `report(fn, "title")` with any retrieval function
  `fn(query, plan) -> [doc_id, ...]` (ordered) and it prints **Recall@1 / @3 / @5** per slice.

You'll also need a free **Weaviate Cloud** cluster and an **OpenAI** key — put both in `.env`
(see `.env.example`).

---

## Part A — build the RAG pipeline

Create a `rag/` package with these modules and **exact signatures** (the provided scripts import
them by these names):

**`rag/chunker.py`**
```python
def load_chunks() -> list[dict]:
    """Read kb/*.md (skip _manifest.json) + kb/_manifest.json, split each doc into overlapping
    word-window chunks. Return [{text, doc_id, title, doc_type, plan, chunk_index}, ...].
    Start naive on purpose: fixed-size windows (~120 words) with a small overlap (~25)."""
```

**`rag/embeddings.py`** — bring-your-own-vectors (embed yourself; don't use Weaviate's vectorizer)
```python
def embed(text: str) -> list[float]: ...
def embed_many(texts: list[str]) -> list[list[float]]:
    """OpenAI text-embedding-3-small. Cache to disk (key on a hash of the text) so re-runs are free."""
```

**`rag/weaviate_client.py`**
```python
COLLECTION = "KBChunk"
def get_client():
    """One cached connection to Weaviate Cloud, creds from .env (WEAVIATE_URL, WEAVIATE_API_KEY)."""
```

**`rag/ingest.py`** — run once to populate the cluster
```python
# Create the KBChunk collection with the vectorizer set to NONE (you supply vectors) and a vector
# index your cluster allows. Embed every chunk with embed_many and push {properties, vector}.
# Store doc_id/title/doc_type/plan/chunk_index as properties so you can filter + report later.
```

**`rag/search.py`** — the retriever behind everything
```python
def search_kb(query, k=5, plan=None, mode="dense", embed_text=None) -> list[dict]:
    """Return [{doc_id, title, text}, ...] for the top-k chunks.
    - mode="dense": pure vector search (embed the query, near_vector).
    - plan=<tier>: metadata filter to that plan + plan-agnostic docs (used in Part B).
    - embed_text: if given, embed THIS instead of `query` (used by HyDE in Part B).
    Keep the signature stable — Part B only flips how it's called."""
```

**Milestone:** once `search.py` works and the corpus is ingested, run
`python3 sessions/s5_rag/retrieval_failures.py` and you should reproduce the six failing slices you
saw in class. Then run `rageval.report(...)` on a naive-dense retrieval function to get your
**baseline** recall table. Save it — it's the number every fix has to beat.

---

## Part B — fix the failures, one technique per slice

Grow **one** function, `rag/retrieval_pipeline.py`, where each flag turns on one technique:

```python
def retrieve(query, plan=None, k=5,
             use_metadata=False, use_rerank=False, use_hyde=False) -> list[dict]: ...

def should_abstain(query, hits) -> bool: ...
```

Build the techniques in this order and, after each, run `rageval.report` and confirm the target
slice's recall moves (and nothing else regresses):

| # | Slice it fixes | Technique | What to implement | Target |
|---|---|---|---|---|
| 1 | `metadata` | **Metadata filter** | pass `plan` to `search_kb` so only the customer's tier (+ plan-agnostic docs) is searched | metadata Recall@3 → ~1.0 |
| 2 | `rerank` | **Reranking** | retrieve a wide pool (~20), then have an LLM reorder by true relevance and keep top-k | rerank Recall@1 climbs |
| 3 | `hyde` | **HyDE** | generate a short hypothetical *answer* and embed THAT (via `embed_text`) instead of the raw query | hyde Recall@5 → ~1.0 |
| 4 | `abstention` | **Relevance gate (CRAG)** | grade whether the retrieved passages actually answer; if not, `should_abstain` returns True | null cases abstain; answerable ones don't |

**Tips from class:**
- For **rerank**, remember Recall@1 measures *ordering* — you always retrieve a pool and hand k to the
  agent; @1 just asks "is the best slot correct?"
- For **HyDE**, the hypothetical must use the corpus's *real* terminology or its embedding lands in the
  wrong neighborhood. A small **product glossary** in the prompt (general canonical terms — NOT a
  mapping of test cases; that would be cheating the eval) is the trick that makes it work.
- Two slices are deliberately tricky. **`hybrid`** may already work on pure dense at this corpus size —
  if it does, say so honestly rather than forcing a "win." **`cross_plan`** asks about a *different*
  plan than the customer's, so a blind metadata filter *removes* the answer — think about who should
  decide whether to filter.

---

## What to submit

1. Your `rag/` package (Part A).
2. Your `rag/retrieval_pipeline.py` + a short `step*.py` per technique (Part B) that prints the
   before/after `rageval` table for that fix.
3. A one-page note: your baseline recall table, the table after each fix, and one paragraph on the
   two tricky slices (`hybrid`, `cross_plan`) — what you found and why.
