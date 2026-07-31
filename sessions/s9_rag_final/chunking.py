"""
Chunking for the unified index — normal docs vs parent-child docs.

  normal doc        -> fixed 120-word windows (role="chunk"); a match returns THAT chunk.
  parent-child doc  -> split into ~120-word PARENT BLOCKS; each block into sentence children
                       (role="child") that carry their block as `parent_text`. A child match
                       returns its BLOCK — a bounded, relevant slice — NOT the whole document.

Classic small-to-big done right: we search the small sentence but return the enclosing block, so we
restore the diluted context without dumping the entire file into the prompt. `parent_text` is
denormalized onto each child (no separate parent rows, no second lookup). BM25 is restricted to the
`text` field at search time, so matching still happens on the small child sentence.
"""

import re

from sessions.s9_rag_final import log as L

CHUNK_WORDS = 120        # normal-doc window size
PARENT_BLOCK_WORDS = 120 # parent-block size for parent-child docs (the unit we RETURN)
OVERLAP = 25
MIN_CHILD_CHARS = 30


def _windows(body, size, overlap):
    w = body.split()
    if len(w) <= size:
        return [body]
    step = size - overlap
    return [" ".join(w[i:i + size]) for i in range(0, len(w), step) if w[i:i + size]]


def naive_chunks(body):
    return _windows(body, CHUNK_WORDS, OVERLAP)


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= MIN_CHILD_CHARS]


def rows_for(doc, body):
    """doc = a manifest entry (dict). Return the index rows for this document."""
    base = {"doc_id": doc["doc_id"], "title": doc["title"],
            "doc_type": doc["doc_type"], "plan": doc["plan"]}
    if doc.get("parent_child"):
        rows = []
        # non-overlapping parent blocks so each sentence belongs to exactly one block
        for bi, block in enumerate(_windows(body, PARENT_BLOCK_WORDS, 0)):
            for sent in _sentences(block):
                rows.append({**base, "text": sent, "role": "child",
                             "parent_id": f"{doc['doc_id']}#{bi}", "parent_text": block,
                             "chunk_index": bi})
        L.detail(f"{doc['doc_id']}: parent-child -> {len(rows)} sentence children across "
                 f"{len(_windows(body, PARENT_BLOCK_WORDS, 0))} block(s)",
                 why="search matches a tiny child sentence; we return its ~120-word BLOCK (bounded), "
                     "restoring context without sending the whole document.")
        return rows
    rows = [{**base, "text": c, "role": "chunk", "parent_id": "", "parent_text": "", "chunk_index": i}
            for i, c in enumerate(naive_chunks(body))]
    L.detail(f"{doc['doc_id']}: normal -> {len(rows)} fixed {CHUNK_WORDS}-word window(s)")
    return rows
