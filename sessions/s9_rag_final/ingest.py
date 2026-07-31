"""
Build the unified vector index (run once).

Reads corpus/ + manifest.json, chunks each doc (parent-child docs -> children + parent; others ->
normal windows), embeds everything, and (re)builds the single Weaviate collection with metadata so
it supports hybrid search + the plan filter + parent lookup.

    python3 sessions/s9_rag_final/ingest.py

(Graph is built separately by build_graph.py — both are one-time preprocessing.)
"""

import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass
from sessions.s9_rag_final import kb_index, chunking
from sessions.s9_rag_final import log as L

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "corpus")


def _body(doc_id):
    with open(os.path.join(CORPUS, f"{doc_id}.md")) as f:
        text = f.read()
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()


def main():
    with open(os.path.join(HERE, "manifest.json")) as f:
        manifest = json.load(f)
    L.section(f"INGEST — {len(manifest)} docs into the unified index")

    L.step("chunk each doc according to its manifest classification",
           why="normal docs become fixed word-windows; parent-child docs become sentence-children that "
               "each carry their ~120-word parent block — a child match widens to its block, not the file.")
    rows = []
    for doc in manifest:
        rows += chunking.rows_for(doc, _body(doc["doc_id"]))

    roles = Counter(r["role"] for r in rows)
    L.step(f"built {len(rows)} index rows",
           why="parent-child docs become many small children (each pointing at its block); normal docs become windows.")
    L.detail(f"by role: {dict(roles)}   (both chunk and child are searchable; a child returns its parent block)")

    L.step("(re)create the collection", why="one collection holds everything; BM25 on `text` + our "
           "vectors gives hybrid, and doc_type/plan enable the metadata filter.")
    kb_index.create_collection()

    L.step("embed + push rows (BYOV OpenAI embeddings, cached)")
    failed = kb_index.add_rows(rows)
    total = kb_index._coll().aggregate.over_all(total_count=True).total_count
    L.step(f"done — collection rows: {total}   failed: {failed}")


if __name__ == "__main__":
    main()
