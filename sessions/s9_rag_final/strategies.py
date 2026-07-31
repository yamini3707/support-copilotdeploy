"""
The three retrieval strategies that run in parallel. Each returns [(doc_id, text, score), ...] and
applies the metadata (plan) filter it was given. Each is a Langfuse span (@observe) so it shows up
in the trace with its own latency.

  hybrid_strategy : BM25 + vector on the raw query
  hyde_strategy   : rewrite the query into a hypothetical answer, then BM25 + vector on THAT
  graph_strategy  : link the query to graph entities, traverse, return the connected docs
"""

import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from langfuse import observe
from eval.retry import call_with_retry
from sessions.s9_rag_final import kb_index, graph_search
from sessions.s9_rag_final import log as L

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "corpus")
K = 6

# short controlled vocabulary so HyDE writes hypotheticals in the corpus's real terms
GLOSSARY = """CloudDesk canonical terms: audit logs (who-changed-what, Enterprise); SSO/SAML
(single sign-on); data retention window (how long deleted data is recoverable); API rate limit /
HTTP 429; refund policy (14-day window); seats; past due; incident (a tracked outage)."""


GRAPH_MAX_WORDS = 220     # cap graph-neighbour docs so a huge doc can't flood the context


def doc_text(doc_id):
    p = os.path.join(CORPUS, f"{doc_id}.md")
    if not os.path.exists(p):
        return ""
    with open(p) as f:
        return re.sub(r"^---\n.*?\n---\n", "", f.read(), flags=re.DOTALL).strip()


def _graph_slice(doc_id):
    """A bounded slice of a graph-connected doc. Short, self-contained docs (a postmortem) come whole;
    a large doc is capped to GRAPH_MAX_WORDS. (A production system would sub-retrieve the query-relevant
    chunk of the neighbour doc; capping is the simple, bounded stand-in.)"""
    words = doc_text(doc_id).split()
    return " ".join(words[:GRAPH_MAX_WORDS])


def _hyde(query):
    """Rewrite the query into a hypothetical answer passage (embeds/matches closer to real docs)."""
    from openai import OpenAI
    system = ("Write a short (~60 words) CloudDesk help-center passage that would ANSWER the "
              "customer's question, using the product's canonical terminology below. Approximate is "
              f"fine — it's only used to improve search.\n\n{GLOSSARY}")
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": query}])
    return resp.choices[0].message.content.strip()


@observe(name="hybrid")
def hybrid_strategy(query, plan):
    L.detail("hybrid strategy: BM25 + vector on the raw query",
             why="lexical BM25 catches exact terms/ids; the vector catches paraphrases — hybrid gets both.")
    hits = [(h["doc_id"], h["text"], h["score"]) for h in kb_index.search(query, k=K, plan=plan, mode="hybrid")]
    L.detail(f"hybrid retrieved {len(hits)} hits: {[d for d, _, _ in hits]}")
    return hits


@observe(name="hyde")
def hyde_strategy(query, plan):
    hypo = _hyde(query)                                    # BM25 + vector on the hypothetical answer
    L.detail(f"hyde strategy: rewrote query into a hypothetical answer -> {hypo[:150]!r}",
             why="a made-up ANSWER sits closer to real doc passages than the terse question does, so "
                 "searching on it retrieves better even when the question shares few words with the docs.")
    hits = [(h["doc_id"], h["text"], h["score"]) for h in kb_index.search(hypo, k=K, plan=plan, mode="hybrid")]
    L.detail(f"hyde retrieved {len(hits)} hits: {[d for d, _, _ in hits]}")
    return hits


@observe(name="graph")
def graph_strategy(query, plan):
    L.detail("graph strategy: link query to graph entities, then traverse for connected docs",
             why="answers that depend on RELATIONSHIPS (e.g. same root cause across incidents) live in "
                 "the graph's structure, not in any single passage's words.")
    seeds = graph_search.link(query)
    docs = graph_search.traverse(seeds) if seeds else []
    L.detail(f"graph retrieved {len(docs)} connected docs: {docs}")
    return [(d, _graph_slice(d), 0.5) for d in docs]       # bounded slice; neutral score, rerank decides
