"""
Build the knowledge graph: extract triples, resolve entities/relations, assemble nodes+edges, save.

Entity resolution (hybrid — embedding for RECALL, LLM for PRECISION):
  identifier  -> EXACT match (INC-2041 stays != INC-2042).
  descriptive -> embed -> shortlist existing entities in its type above a LOW threshold (high recall)
                 -> if candidates exist, the LLM decides "same as one of these, or NEW?" (precision).
                 -> no candidates => trivially NEW (no LLM call). Decisions are cached.

Closed relation set (snapped) + closed entity TYPES (junk dropped). The graph (nodes + edges) is
assembled in main() and persisted to graph.json. Runs with narrated step-by-step logging.

Run:  python3 sessions/s8_graphrag/build_graph.py
"""

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
from sessions.s8_graphrag.embeddings import embed   # self-contained OpenAI embeddings (disk-cached)
from eval.retry import call_with_retry
from sessions.s8_graphrag import log as L           # neat step-by-step logging

DOCS = ["postmortem_inc2041", "postmortem_inc2042", "postmortem_inc2037",
        "cert_rotation_runbook", "arch_saml_cert"]              # the source docs (all under docs/)
DOCDIR = os.path.join(os.path.dirname(__file__), "docs")

ENTITY_TYPES = ["Incident", "Component", "Service", "Feature", "Runbook"]
RELATIONS = ["CAUSED_BY", "AFFECTS", "DEPENDS_ON", "REMEDIATED_BY", "REQUIRES"]
SHORTLIST = 0.45
TOP_K = 5
GRAPH_PATH = os.path.join(os.path.dirname(__file__), "graph.json")


def _read(doc_id):
    md = open(os.path.join(DOCDIR, f"{doc_id}.md")).read()
    return re.sub(r"^---\n.*?\n---\n", "", md, flags=re.DOTALL).strip()   # strip YAML frontmatter


def _emb(t):
    v = np.array(embed(t)); return v / np.linalg.norm(v)   # unit vector -> dot product == cosine


def _link(etype, mention, cands):
    """LLM precision step: does `mention` refer to one of the candidate entities, or is it new?"""
    listing = "\n".join(f"  {i}) {disp}" for i, (_, disp) in enumerate(cands))
    prompt = (f'Building a knowledge graph. Entity type: {etype}.\n'
              f'New mention: "{mention}"\nExisting entities of this type:\n{listing}\n\n'
              'Does the new mention refer to the SAME real-world entity as one of these (e.g. an alias '
              'or paraphrase), or is it genuinely NEW/different (e.g. "old cert" vs "new cert")?\n'
              'Return JSON {"match": <index, or -1 if new>}.')
    from openai import OpenAI
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_RERANK_MODEL", "gpt-4o-mini"), temperature=0,
        response_format={"type": "json_object"}, messages=[{"role": "user", "content": prompt}])
    i = json.loads(resp.choices[0].message.content).get("match", -1)
    return cands[i][0] if isinstance(i, int) and 0 <= i < len(cands) else None


class TypedRegistry:
    """Resolves entity mentions to canonical node ids, per type. identifier=exact, descriptive=embed+LLM."""
    def __init__(self):
        self.exact = {}    # type -> {normalized_name: id}
        self.desc = {}     # type -> {"embs": [vecs], "ids": [ids]}
        self.display = {}  # id -> canonical name
        self.cache = {}    # (type, name.lower()) -> id
        self._n = 0

    def _new(self, name):
        self._n += 1; self.display[self._n] = name; return self._n

    def resolve(self, etype, name, mode):
        name = (name or "").strip()
        if etype not in ENTITY_TYPES or not name or name.lower() == etype.lower():
            L.detail(f"drop '{name}' [{etype}]",
                     why="its type is not in the closed set, or the name is just a bare type word — "
                         "so it isn't a real entity and must not become a node.")
            return None

        if mode == "identifier":                          # ---- exact path ----
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            d = self.exact.setdefault(etype, {})
            if key in d:
                L.detail(f"'{name}' [{etype}/identifier] -> exact match #{d[key]} '{self.display[d[key]]}'")
                return d[key]
            nid = d.setdefault(key, self._new(name))
            L.detail(f"'{name}' [{etype}/identifier] -> NEW node #{nid}",
                     why="identifiers must match EXACTLY — embeddings would wrongly merge INC-2041 "
                         "with INC-2042 (one digit apart), so we never fuzzy-match these.")
            return nid

        ck = (etype, name.lower())                        # ---- descriptive path ----
        if ck in self.cache:
            L.detail(f"'{name}' [{etype}/descriptive] -> cached #{self.cache[ck]} '{self.display[self.cache[ck]]}'")
            return self.cache[ck]
        reg = self.desc.setdefault(etype, {"embs": [], "ids": []})
        v = _emb(name)
        cid = None
        if reg["embs"]:                                   # gather candidates (recall) then let LLM decide
            sims = np.array(reg["embs"]) @ v
            cands, seen = [], set()
            for j in np.argsort(-sims):
                if sims[j] < SHORTLIST or len(cands) >= TOP_K:
                    break
                i = reg["ids"][j]
                if i not in seen:
                    seen.add(i); cands.append((i, self.display[i], float(sims[j])))
            if cands:
                L.detail(f"'{name}' [{etype}/descriptive] -> shortlist: "
                         + ", ".join(f"'{d}'({s:.2f})" for _, d, s in cands),
                         why=f"embedding is a cheap recall filter: it narrows this type's entities to the "
                             f"few above cosine {SHORTLIST}; the LLM then judges meaning.")
                cid = _link(etype, name, [(i, d) for i, d, _ in cands])
                if cid is not None:
                    if len(name) > len(self.display[cid]):
                        self.display[cid] = name          # keep the more specific name
                    L.detail(f"   LLM decision: SAME as '{self.display[cid]}' (#{cid}) -> merge",
                             why="cosine can't tell an alias from a near-opposite; the LLM decides on meaning.")
                else:
                    L.detail("   LLM decision: NEW (none of the candidates is the same real-world thing)")
            else:
                L.detail(f"'{name}' [{etype}/descriptive] -> no candidate >= {SHORTLIST}",
                         why="nothing existing is close enough to possibly be the same thing, so no LLM "
                             "call is needed — it's trivially a new node.")
        else:
            L.detail(f"'{name}' [{etype}/descriptive] -> first entity of this type")
        if cid is None:
            cid = self._new(name)
        reg["embs"].append(v); reg["ids"].append(cid)     # store this surface form for future recall
        self.cache[ck] = cid
        return cid


class RelationSnapper:
    """Forces any relation phrase into the CLOSED relation set (so traversal-by-relation stays meaningful)."""
    def __init__(self):
        self.embs = [_emb(r) for r in RELATIONS]

    def snap(self, phrase):
        u = re.sub(r"[^A-Z]+", "_", (phrase or "").upper()).strip("_")
        if u in RELATIONS:
            L.detail(f"relation '{phrase}' -> {u} (already canonical)")
            return u
        best = RELATIONS[int((np.array(self.embs) @ _emb(phrase or "x")).argmax())]
        L.detail(f"relation '{phrase}' -> {best} (nearest canonical)",
                 why="relations are a CLOSED set so traversal-by-relation stays meaningful; any phrase "
                     "is snapped to the closest of the five.")
        return best


def _extract(text):
    """LLM extraction: turn a document into (subject, relation, object) triples with types + match modes."""
    prompt = (
        "Extract (subject, relation, object) triples for a knowledge graph.\n"
        f"Each subject/object needs a TYPE from EXACTLY: {ENTITY_TYPES}. If it isn't one of these "
        "(a metric, duration, percentage, vague noun), DO NOT include it.\n"
        "Each subject/object also needs a MATCH MODE: 'identifier' for a code/id like INC-2041 "
        "(exact), 'descriptive' for a concept that could be phrased differently (the signing cert).\n"
        f"Each relation MUST be one of: {RELATIONS}. Name incidents by id (INC-XXXX). "
        "Only assert relationships actually stated.\n\n"
        f"DOCUMENT:\n{text}\n\n"
        'Return JSON: {"triples":[{"subject","subject_type","subject_mode",'
        '"relation","object","object_type","object_mode"}]}')
    from openai import OpenAI
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"}, messages=[{"role": "user", "content": prompt}])
    return json.loads(resp.choices[0].message.content).get("triples", [])


def main():
    L.section(f"BUILD GRAPH — {len(DOCS)} source documents")
    ents, rels = TypedRegistry(), RelationSnapper()
    edges, dropped = {}, 0

    for doc_id in DOCS:
        L.step(f"DOCUMENT: {doc_id}")
        L.step("extract triples with the LLM", level=2,
               why="an LLM reads the prose and proposes structured (subject, relation, object) facts, "
                   "constrained to our closed entity types and relations.")
        triples = _extract(_read(doc_id))
        L.detail(f"got {len(triples)} raw triples")
        for t in triples:
            raw = f"{t.get('subject')} --{t.get('relation')}--> {t.get('object')}"
            L.detail(f"triple: {raw}")
            # resolve each side to a canonical node id (using its own match mode)
            s = ents.resolve(t.get("subject_type", ""), t.get("subject", ""), t.get("subject_mode", "descriptive"))
            o = ents.resolve(t.get("object_type", ""), t.get("object", ""), t.get("object_mode", "descriptive"))
            if not s or not o:
                dropped += 1
                L.detail("   -> triple DROPPED (an endpoint wasn't a valid entity)")
                continue
            r = rels.snap(t.get("relation", ""))          # snap the relation into the closed set
            new = (s, r, o) not in edges
            edges.setdefault((s, r, o), set()).add(doc_id)
            L.detail(f"   -> edge {'ADDED' if new else 'reinforced'}: "
                     f"'{ents.display[s]}' --{r}--> '{ents.display[o]}'  (doc {doc_id})")

    L.section("RESULTING GRAPH")
    by_type = {}
    for etype in ENTITY_TYPES:
        ids = list(dict.fromkeys(list(ents.exact.get(etype, {}).values()) + ents.desc.get(etype, {}).get("ids", [])))
        if ids:
            by_type[etype] = [ents.display[i] for i in ids]
            L.step(f"{etype} ({len(ids)}): {by_type[etype]}")
    L.step(f"edges: {len(edges)}   dropped triples: {dropped}")
    for (s, r, o), docs in edges.items():
        L.detail(f"{ents.display[s]}  --{r}-->  {ents.display[o]}   {sorted(docs)}")

    json.dump({"entities": by_type, "nodes": ents.display,
               "edges": [{"subject": ents.display[s], "relation": r, "object": ents.display[o],
                          "doc_ids": sorted(d)} for (s, r, o), d in edges.items()]},
              open(GRAPH_PATH, "w"), indent=2)
    L.step(f"saved graph -> {GRAPH_PATH}")


if __name__ == "__main__":
    main()
