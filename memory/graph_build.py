"""
MEMORY · Step 5a — build the customer's MEMORY GRAPH (build + print only; traversal comes next).

Same discipline as our GraphRAG build (s8/s9):
  - CLOSED entity TYPES + CLOSED relations   -> junk is dropped, edges line up
  - hybrid entity RESOLUTION                 -> embedding shortlist then LLM decides same-vs-new,
                                                so 'Acme'/'Acme Robotics' merge, 'Globex'/'Globex
                                                Corporation' merge (reusing s9's _emb/_link/thresholds)
  - PROVENANCE + a fact reverse-index         -> every node/edge remembers which memory fact it came
                                                from (the Class-2 `entity_to_facts` idea), so a later
                                                traversal can map reached nodes back to real facts.

The "documents" here are the customer's memory items (semantic facts + episodic ticket summaries).

    python3 memory/graph_build.py
"""

import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass
from eval.retry import call_with_retry
from sessions.s9_rag_final.graph_build import SHORTLIST, TOP_K, _emb, _link   # reuse the proven resolver

# closed vocabularies for the CUSTOMER-MEMORY domain
ENTITY_TYPES = ["Organization", "Person", "Location", "Policy", "Product", "Integration", "Preference"]
RELATIONS = ["SUBSIDIARY_OF", "MANAGES", "REQUIRES", "USES", "PREFERS", "HAS_ADMIN",
             "LOCATED_IN", "REPORTED", "HAS_ATTRIBUTE"]

# The Acme fixture (same customer as graph_motivation_demo; ★ markers dropped).
SEMANTIC = [
    "Acme is a subsidiary of Globex Corporation, and Globex's central finance team handles all of Acme's account matters.",
    "Acme operates under a strict data-residency policy: all of Acme's data must remain within the EU.",
    "Acme is billed annually in US dollars.",
    "Acme's billing contact is finance@acme.example.",
    "Acme's renewal date is April 1.",
    "Acme relies heavily on the analytics dashboard.",
    "Acme previously asked for a US-based support contact.",
    "Acme has 40 seats purchased and typically uses about 32.",
    "Acme authenticates users through Okta as their identity provider.",
    "Acme prefers to be contacted by email rather than live chat.",
    "Acme's primary admin is Priya Nair.",
    "Acme defaults to the Kanban board view.",
    "Acme requested SSO enforcement for all members.",
    "Acme onboarded in 2024 and renews annually.",
]
HISTORY = [
    "Ticket 2026-02-23 (technical, UNRESOLVED): Audit-log export returned partial data; promised follow-up.",
    "Ticket 2026-02-10 (billing, resolved): Question about the annual invoice.",
    "Ticket 2026-01-30 (account, resolved): Enabled SSO enforcement.",
    "Ticket 2026-01-12 (account, resolved): Increased seats from 30 to 40.",
    "Ticket 2025-12-05 (feature_request, resolved): Asked for a new analytics add-on.",
]


def _memory_items():
    return [("F%02d" % i, t) for i, t in enumerate(SEMANTIC + HISTORY)]


# ── entity resolution, per type (identifier=exact, descriptive=embedding shortlist + LLM decide) ──
class TypedRegistry:
    def __init__(self):
        self.exact, self.desc, self.display, self.cache, self.type_of, self._n = {}, {}, {}, {}, {}, 0

    def _new(self, name, etype):
        self._n += 1; self.display[self._n] = name; self.type_of[self._n] = etype; return self._n

    def resolve(self, etype, name, mode):
        name = (name or "").strip()
        if etype not in ENTITY_TYPES or not name or name.lower() == etype.lower():
            return None
        if mode == "identifier":
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            d = self.exact.setdefault(etype, {})
            return d[key] if key in d else d.setdefault(key, self._new(name, etype))
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
            cid = self._new(name, etype)
        reg["embs"].append(v); reg["ids"].append(cid); self.cache[ck] = cid
        return cid


class RelationSnapper:
    def __init__(self):
        self.embs = [_emb(r) for r in RELATIONS]

    def snap(self, phrase):
        u = re.sub(r"[^A-Z]+", "_", (phrase or "").upper()).strip("_")
        if u in RELATIONS:
            return u
        return RELATIONS[int((np.array(self.embs) @ _emb(phrase or "x")).argmax())]


def _extract(text):
    system = (
        "Extract (subject, relation, object) triples describing THIS customer from the memory note.\n"
        f"Each subject/object needs a TYPE from EXACTLY: {ENTITY_TYPES}. Skip anything that isn't one "
        "of these (a bare number, a date, a vague noun).\n"
        "Each also needs a MATCH MODE: 'identifier' for codes/emails, 'descriptive' for names/concepts.\n"
        f"Each relation MUST be one of: {RELATIONS}. Only assert what the note states.\n"
        'Return JSON {"triples":[{"subject","subject_type","subject_mode","relation",'
        '"object","object_type","object_mode"}]}')
    from openai import OpenAI
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": text}])
    return json.loads(resp.choices[0].message.content).get("triples", [])


def build_from_items(items, verbose=True):
    """Build a memory graph from ANY list of (fact_id, text) items — the customer's real semantic +
    episodic memory in production, or the demo fixture in the teaching scripts. Same discipline either
    way. Returns (entities, edges{(s,r,o)->set(fids)}, entity_to_facts{node->set(fids)})."""
    ents, rels = TypedRegistry(), RelationSnapper()
    edges = {}                                   # (s, r, o) -> set(fact_ids)   [provenance]
    entity_to_facts = defaultdict(set)           # node_id -> set(fact_ids)     [reverse index]

    for fid, text in items:
        if verbose:
            print(f"  · {fid}: {text[:74]}")
        for t in _extract(text):
            s = ents.resolve(t.get("subject_type", ""), t.get("subject", ""), t.get("subject_mode", "descriptive"))
            o = ents.resolve(t.get("object_type", ""), t.get("object", ""), t.get("object_mode", "descriptive"))
            if not s or not o:
                continue
            r = rels.snap(t.get("relation", ""))
            edges.setdefault((s, r, o), set()).add(fid)
            entity_to_facts[s].add(fid); entity_to_facts[o].add(fid)
    return ents, edges, entity_to_facts


def build():
    """The teaching demo's graph — built from the hardcoded Acme fixture (SEMANTIC + HISTORY)."""
    return build_from_items(_memory_items())


def main():
    print("\n" + "#" * 100)
    print("  MEMORY · GRAPH BUILD — extract entities/relations from the customer's memory, resolve, link")
    print("#" * 100 + "\n")
    ents, edges, e2f = build()

    print("\n" + "=" * 100)
    print("  ENTITIES (by type, after resolution):")
    by_type = defaultdict(list)
    for nid, name in ents.display.items():
        by_type[ents.type_of[nid]].append(name)
    for et in ENTITY_TYPES:
        if by_type[et]:
            print(f"    {et:13}: {by_type[et]}")

    print(f"\n  EDGES ({len(edges)}):")
    for (s, r, o), fids in edges.items():
        print(f"    {ents.display[s]:42} --{r:13}--> {ents.display[o]:34} {sorted(fids)}")

    print("\n  FACT REVERSE-INDEX (node -> facts that mention it) for the key nodes:")
    for nid, name in ents.display.items():
        if name.lower() in ("globex corporation", "globex", "the eu", "eu", "european union",
                             "priya nair", "okta") or "globex" in name.lower() or "eu" == name.lower():
            print(f"    {name:34} <- {sorted(e2f[nid])}")

    print("\n  SANITY — do the two multi-hop chains exist?")
    names = {n.lower(): i for i, n in ents.display.items()}
    def has(sub_sub, rel, obj_sub):
        return any(rel == r and sub_sub in ents.display[s].lower() and obj_sub in ents.display[o].lower()
                   for (s, r, o) in edges)
    print(f"    Acme --SUBSIDIARY_OF--> Globex : {has('acme','SUBSIDIARY_OF','globex')}")
    print(f"    Acme --REQUIRES--> (EU) residency : "
          f"{any('acme' in ents.display[s].lower() and r=='REQUIRES' for (s,r,o) in edges)}")
    print("\n" + "#" * 100 + "\n")


if __name__ == "__main__":
    main()
