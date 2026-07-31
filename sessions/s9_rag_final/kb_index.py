"""
The unified Weaviate index (one collection) — schema, ingest, and search.

One collection `KBChunk` holds normal chunks and parent-child children, each with metadata
(doc_type, plan), a role, and — for children — the `parent_text` block they resolve to. Because the
`text` property is BM25-indexed and we supply our own vectors, the SAME collection supports hybrid
(BM25 + vector) search and a metadata filter (by plan). A child match returns its parent BLOCK, not
the whole document.

  create_collection()                    (re)build the schema — deletes the old one
  add_rows(rows)                         embed + push index rows
  search(query, k, plan, mode, ...)      hybrid|dense; child hit -> parent block, chunk hit -> chunk
"""

import atexit
import os
import sys
import threading
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass
import weaviate
from weaviate.classes.init import Auth, AdditionalConfig, Timeout
from weaviate.classes.config import Configure, Property, DataType, Tokenization
from weaviate.classes.query import Filter, MetadataQuery
from sessions.s9_rag_final.embeddings import embed, embed_many      # thread-safe embeddings
from sessions.s9_rag_final.trace import span                        # I/O latency spans
from sessions.s9_rag_final import log as L

COLLECTION = "KBChunk"
_wlock = threading.Lock()      # the Weaviate client isn't guaranteed thread-safe; serialize queries
_client = None


def get_client():
    """One cached connection. skip_init_checks avoids the flaky upfront gRPC health-check on the free cluster."""
    global _client
    if _client is None:
        _client = weaviate.connect_to_weaviate_cloud(
            cluster_url=os.getenv("WEAVIATE_URL"),
            auth_credentials=Auth.api_key(os.getenv("WEAVIATE_API_KEY")),
            skip_init_checks=True,
            additional_config=AdditionalConfig(timeout=Timeout(init=30, query=90, insert=120)))
        atexit.register(_client.close)
    return _client


def _retry(fn, tries=3):
    """Retry a Weaviate query — the free cluster occasionally returns a transient Deadline Exceeded."""
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            L.detail(f"weaviate call failed (attempt {attempt + 1}/{tries}) — backing off then retrying",
                     why="the free cluster occasionally returns a transient Deadline Exceeded; a short "
                         "backoff usually clears it.")
            time.sleep(1.5 * (attempt + 1))


def warm():
    """Connect once from the main thread before spawning parallel strategies."""
    with _wlock:
        get_client()


def _coll():
    return get_client().collections.get(COLLECTION)


def create_collection():
    client = get_client()
    if client.collections.exists(COLLECTION):
        L.detail(f"collection {COLLECTION!r} exists — deleting it to rebuild the schema from scratch")
        client.collections.delete(COLLECTION)          # rebuild from scratch
    L.detail(f"creating collection {COLLECTION!r}: BYOV vectors + BM25 on `text` + doc_type/plan props",
             why="one collection with our own vectors AND a BM25-indexed text field is what lets the "
                 "same store serve hybrid search, the plan metadata filter, and parent lookup.")
    client.collections.create(
        name=COLLECTION,
        vectorizer_config=Configure.Vectorizer.none(),         # we bring our own vectors
        vector_index_config=Configure.VectorIndex.hfresh(),    # this cluster mandates the hfresh index
        properties=[
            Property(name="text", data_type=DataType.TEXT),                        # the SEARCHED unit (chunk / child sentence)
            Property(name="parent_text", data_type=DataType.TEXT),                 # a child's parent BLOCK (return-only)
            Property(name="doc_id", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="doc_type", data_type=DataType.TEXT),
            Property(name="plan", data_type=DataType.TEXT),                        # metadata filter
            Property(name="chunk_index", data_type=DataType.INT),
            Property(name="role", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),      # chunk|child
            Property(name="parent_id", data_type=DataType.TEXT, tokenization=Tokenization.FIELD),
        ],
    )


def add_rows(rows):
    L.detail(f"embedding {len(rows)} rows, then batch-pushing them with their vectors to Weaviate")
    vectors = embed_many([r["text"] for r in rows])
    coll = _coll()
    with coll.batch.dynamic() as batch:
        for r, v in zip(rows, vectors):
            batch.add_object(properties=r, vector=v)
    return len(coll.batch.failed_objects)


def _filter(plan):
    if plan:                                            # own-account question -> restrict to plan + plan-agnostic
        return Filter.by_property("plan").contains_any([plan, "all"])
    return None


def _unit(o, score):
    """The retrieval unit to return: a child resolves to its parent BLOCK; a chunk stays itself."""
    p = o.properties
    text = p.get("parent_text") or p["text"]            # child -> bounded block; chunk -> the chunk
    return {"doc_id": p["doc_id"], "title": p["title"], "text": text,
            "role": p["role"], "score": score}


def search(query, k=8, plan=None, mode="hybrid", embed_text=None):
    """Return top-k hits [{doc_id, title, text, role, score}]. A child hit's text is its parent BLOCK
    (bounded), a chunk hit's text is the chunk. mode: 'hybrid' or 'dense'."""
    qv = embed(embed_text or query)                     # embed_text lets HyDE embed a hypothetical answer
    flt = _filter(plan)
    if plan:
        L.detail(f"{mode} search (k={k}) with plan filter -> {plan!r} + 'all'",
                 why="an own-account question must only see this customer's tier (plus plan-agnostic docs).")
    else:
        L.detail(f"{mode} search (k={k}), no plan filter",
                 why="a cross-plan/general question searches all tiers.")
    props = ["doc_id", "title", "text", "parent_text", "role"]

    def _do():
        with _wlock:                                    # serialize the DB query (client not thread-safe)
            if mode == "hybrid":                        # query_properties=["text"] -> BM25 matches the small unit, not parent_text
                res = _coll().query.hybrid(query=query, vector=qv, alpha=0.5, limit=k, filters=flt,
                                           query_properties=["text"],
                                           return_metadata=MetadataQuery(score=True), return_properties=props)
                return [_unit(o, float(o.metadata.score or 0)) for o in res.objects]
            res = _coll().query.near_vector(near_vector=qv, limit=k, filters=flt,
                                            return_metadata=MetadataQuery(distance=True), return_properties=props)
            return [_unit(o, 1 - o.metadata.distance) for o in res.objects]

    # traced I/O span (captures the gRPC query latency, retries included) — no-op outside a trace
    with span("weaviate_search", mode=mode, plan=plan or "none", k=k) as s:
        hits = _retry(_do)
        if s:
            s.update(metadata={"mode": mode, "plan": plan or "none", "k": k, "results": len(hits)})
        return hits
