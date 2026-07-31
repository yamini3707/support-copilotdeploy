"""
Build corpus/manifest metadata for the unified RAG index.

For every doc in corpus/, record: doc_id, title, doc_type, plan (for the metadata filter), word_count,
and parent_child (True for long docs that a fixed-window chunker would split — they get indexed as
small children pointing to a parent, so a match on a child returns the whole parent).

Metadata comes from kb/_manifest.json where available, else the doc's YAML frontmatter.

    python3 sessions/s9_rag_final/manifest.py
"""

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
from sessions.s9_rag_final import log as L

CORPUS = os.path.join(HERE, "corpus")
OUT = os.path.join(HERE, "manifest.json")
PC_THRESHOLD = 250          # word count at/above which a doc is indexed parent-child


def _frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    d = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
    return d


def _body(text):
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()


def main():
    L.section("BUILD MANIFEST — one metadata row per corpus doc")
    L.step("load kb/_manifest.json for authoritative metadata",
           why="curated metadata (title/doc_type/plan) wins; we fall back to each doc's YAML "
               "frontmatter only when the kb manifest doesn't cover it.")
    kb_meta = {m["doc_id"]: m for m in json.load(open(os.path.join(ROOT, "kb", "_manifest.json")))}

    L.step(f"scan corpus/*.md and classify each doc (parent-child if >= {PC_THRESHOLD} words)",
           why="long docs would be sliced by a fixed-window chunker, so we index them as small "
               "children pointing to a parent — a child hit can then return the whole parent.")
    manifest = []
    for path in sorted(glob.glob(os.path.join(CORPUS, "*.md"))):
        did = os.path.splitext(os.path.basename(path))[0]
        text = open(path).read()
        fm, meta = _frontmatter(text), kb_meta.get(did, {})
        wc = len(_body(text).split())
        manifest.append({
            "doc_id": did,
            "title": meta.get("title") or fm.get("title") or did,
            "doc_type": meta.get("doc_type") or fm.get("doc_type") or "doc",
            "plan": meta.get("plan") or fm.get("plan") or "all",
            "word_count": wc,
            "parent_child": wc >= PC_THRESHOLD,
        })
        L.detail(f"{did}: {wc} words -> {'parent-child' if wc >= PC_THRESHOLD else 'normal'}")
    json.dump(manifest, open(OUT, "w"), indent=2)

    pc = [m["doc_id"] for m in manifest if m["parent_child"]]
    from collections import Counter
    L.step(f"wrote {OUT}  ({len(manifest)} docs)")
    L.step(f"doc_type spread: {dict(Counter(m['doc_type'] for m in manifest))}")
    L.step(f"plan spread:     {dict(Counter(m['plan'] for m in manifest))}")
    L.step(f"parent-child docs ({len(pc)}, >= {PC_THRESHOLD} words):")
    for did in pc:
        L.detail(f"- {did}")


if __name__ == "__main__":
    main()
