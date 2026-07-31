"""
Build the knowledge graph over the WHOLE corpus (run once) -> graph.json.

Same clean pipeline as before: LLM extracts (subject, relation, object) triples with closed entity
TYPES + closed RELATIONS; entities are resolved per type (identifier=exact, descriptive=embedding
shortlist -> LLM decides); relations snap to the closed set. Most non-relational docs (FAQs) yield
~no edges under the closed schema, so "graph of everything" stays clean. Extraction is cached per
doc, so re-runs are free.

    python3 sessions/s9_rag_final/graph_build.py
"""

import hashlib
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass
from sessions.s9_rag_final.embeddings import embed    # thread-safe embeddings (shared with runtime)
from eval.retry import call_with_retry
from sessions.s9_rag_final import log as L

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "corpus")
GRAPH_PATH = os.path.join(HERE, "graph.json")
CACHE_PATH = os.path.join(HERE, ".graph_cache.json")

ENTITY_TYPES = ["Incident", "Component", "Service", "Feature", "Runbook"]
RELATIONS = ["CAUSED_BY", "AFFECTS", "DEPENDS_ON", "REMEDIATED_BY", "REQUIRES"]
SHORTLIST = 0.45
TOP_K = 5

_cache = json.load(open(CACHE_PATH)) if os.path.exists(CACHE_PATH) else {}


def _body(doc_id):
    with open(os.path.join(CORPUS, f"{doc_id}.md")) as f:
        return re.sub(r"^---\n.*?\n---\n", "", f.read(), flags=re.DOTALL).strip()


def _emb(t):
    v = np.array(embed(t)); return v / np.linalg.norm(v)


def _link(etype, mention, cands):
    """LLM precision step: does `mention` refer to one of the candidate entities, or is it new?"""
    listing = "\n".join(f"  {i}) {disp}" for i, (_, disp) in enumerate(cands))
    system = ("You resolve entity mentions for a knowledge graph. Decide whether the new mention "
              "refers to the SAME real-world entity as one of the candidates (an alias/paraphrase) "
              'or is genuinely NEW/different (e.g. "old cert" vs "new cert"). '
              'Return JSON {"match": <index, or -1 if new>}.')
    user = f'Entity type: {etype}\nNew mention: "{mention}"\nCandidates:\n{listing}'
    from openai import OpenAI
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_RERANK_MODEL", "gpt-4o-mini"), temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    i = json.loads(resp.choices[0].message.content).get("match", -1)
    return cands[i][0] if isinstance(i, int) and 0 <= i < len(cands) else None


class TypedRegistry:
    """Resolve entity mentions to canonical node ids, per type. identifier=exact, descriptive=embed+LLM."""
    def __init__(self):
        self.exact, self.desc, self.display, self.cache, self._n = {}, {}, {}, {}, 0

    def _new(self, name):
        self._n += 1; self.display[self._n] = name; return self._n

    def resolve(self, etype, name, mode):
        name = (name or "").strip()
        if etype not in ENTITY_TYPES or not name or name.lower() == etype.lower():
            return None
        if mode == "identifier":
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            d = self.exact.setdefault(etype, {})
            return d[key] if key in d else d.setdefault(key, self._new(name))
        ck = (etype, name.lower())
        if ck in self.cache:
            return self.cache[ck]
        reg = self.desc.setdefault(etype, {"embs": [], "ids": []})
        v, cid = _emb(name), None
        if reg["embs"]:
            sims = np.array(reg["embs"]) @ v
            cands, seen = [], set()
            for j in np.argsort(-sims):
                if sims[j] < SHORTLIST or len(cands) >= TOP_K:
                    break
                i = reg["ids"][j]
                if i not in seen:
                    seen.add(i); cands.append((i, self.display[i]))
            if cands:
                cid = _link(etype, name, cands)
                if cid is not None and len(name) > len(self.display[cid]):
                    self.display[cid] = name
        if cid is None:
            cid = self._new(name)
        reg["embs"].append(v); reg["ids"].append(cid)
        self.cache[ck] = cid
        return cid


class RelationSnapper:
    def __init__(self):
        self.embs = [_emb(r) for r in RELATIONS]

    def snap(self, phrase):
        u = re.sub(r"[^A-Z]+", "_", (phrase or "").upper()).strip("_")
        if u in RELATIONS:
            return u
        return RELATIONS[int((np.array(self.embs) @ _emb(phrase or "x")).argmax())]


def _extract(doc_id, text):
    key = hashlib.sha1((doc_id + "\n" + text).encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    system = (
        "Extract (subject, relation, object) triples for a knowledge graph.\n"
        f"Each subject/object needs a TYPE from EXACTLY: {ENTITY_TYPES}. If it isn't one of these "
        "(a metric, duration, percentage, vague noun), DO NOT include it.\n"
        "Each subject/object also needs a MATCH MODE: 'identifier' for a code/id like INC-2041 "
        "(exact), 'descriptive' for a concept that could be phrased differently.\n"
        f"Each relation MUST be one of: {RELATIONS}. Name incidents by id (INC-XXXX). "
        "Only assert relationships actually stated. If the document has none, return an empty list.\n"
        'Return JSON: {"triples":[{"subject","subject_type","subject_mode","relation",'
        '"object","object_type","object_mode"}]}')
    from openai import OpenAI
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": text}])
    triples = json.loads(resp.choices[0].message.content).get("triples", [])
    _cache[key] = triples
    with open(CACHE_PATH, "w") as f:
        json.dump(_cache, f)
    return triples


def main():
    manifest = json.load(open(os.path.join(HERE, "manifest.json")))
    L.section(f"BUILD GRAPH — over {len(manifest)} docs (whole corpus)")
    ents, rels = TypedRegistry(), RelationSnapper()
    edges, dropped, with_edges = {}, 0, 0

    L.step("extract triples per doc, then resolve entities + snap relations onto the closed schema",
           why="a closed set of entity TYPES and RELATIONS keeps the whole-corpus graph clean — "
               "non-relational docs (FAQs) simply yield no edges, and off-schema mentions are dropped.")
    for doc in manifest:
        doc_id = doc["doc_id"]
        n_before = len(edges)
        triples = _extract(doc_id, _body(doc_id))
        L.detail(f"{doc_id}: LLM extracted {len(triples)} candidate triple(s)")
        for t in triples:
            s = ents.resolve(t.get("subject_type", ""), t.get("subject", ""), t.get("subject_mode", "descriptive"))
            o = ents.resolve(t.get("object_type", ""), t.get("object", ""), t.get("object_mode", "descriptive"))
            if not s or not o:
                dropped += 1
                continue
            edges.setdefault((s, rels.snap(t.get("relation", "")), o), set()).add(doc_id)
        added = len(edges) - n_before
        if added:
            with_edges += 1
            L.detail(f"{doc_id}: +{added} edges")

    L.section("RESULTING GRAPH")
    by_type = {}
    for etype in ENTITY_TYPES:
        ids = list(dict.fromkeys(list(ents.exact.get(etype, {}).values()) + ents.desc.get(etype, {}).get("ids", [])))
        if ids:
            by_type[etype] = [ents.display[i] for i in ids]
    L.step(f"docs contributing edges: {with_edges}/{len(manifest)}   (rest are non-relational — expected)")
    L.step(f"entities: {sum(len(v) for v in by_type.values())}   edges: {len(edges)}   dropped: {dropped}")
    for etype, names in by_type.items():
        L.detail(f"{etype} ({len(names)}): {names}")

    with open(GRAPH_PATH, "w") as f:
        json.dump({"entities": by_type, "nodes": ents.display,
                   "edges": [{"subject": ents.display[s], "relation": r, "object": ents.display[o],
                              "doc_ids": sorted(d)} for (s, r, o), d in edges.items()]}, f, indent=2)
    L.step(f"saved -> {GRAPH_PATH}")


if __name__ == "__main__":
    main()
