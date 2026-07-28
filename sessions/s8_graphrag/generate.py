"""
GraphRAG generation — the end-to-end payoff.

Same query, same model. WITHOUT the graph (plain vector RAG over the same docs) the assistant only
sees the doc that matches the query wording and answers wrong. WITH the graph it also gets the
docs connected through the shared entity, and answers right.

Full graph path: query -> link -> traverse -> docs -> grounded answer. Narrated with logging.
    python3 sessions/s8_graphrag/generate.py
"""

import os
import re
import sys

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from sessions.s8_graphrag.embeddings import embed
from eval.retry import call_with_retry
from eval.judge import judge_answer
from sessions.s8_graphrag.link_query import link
from sessions.s8_graphrag.retrieve import traverse
from sessions.s8_graphrag import log as L

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")
QUERY = ("We had the EU SSO login outage, INC-2041. Has this same underlying cause hit us before, "
         "and how do we prevent it from recurring?")
MUST_CONVEY = ["the same signing-certificate root cause previously caused incident INC-2037, and "
               "recurrence is prevented by the certificate-rotation runbook"]
CORPUS = ["postmortem_inc2041", "postmortem_inc2042", "postmortem_inc2037",
          "cert_rotation_runbook", "arch_saml_cert"]
DOCDIR = os.path.join(os.path.dirname(__file__), "docs")


def _text(doc_id):
    p = os.path.join(DOCDIR, f"{doc_id}.md")
    return re.sub(r"^---\n.*?\n---\n", "", open(p).read(), flags=re.DOTALL).strip() if os.path.exists(p) else ""


def _answer(context):
    prompt = ("You are an SRE assistant. Using ONLY the context, answer the question. If the context "
              "has no prior incident with the same cause or concrete prevention, say you don't know.\n\n"
              f"CONTEXT:\n{context}\n\nQUESTION: {QUERY}\n\nAnswer in 2-3 sentences.")
    from openai import OpenAI
    r = call_with_retry(OpenAI().chat.completions.create, model=MODEL, temperature=0,
                        messages=[{"role": "user", "content": prompt}])
    return r.choices[0].message.content.strip()


def vector_docs(k=2):
    """The 'without graph' retrieval: plain vector search — top-k docs most similar to the query."""
    qv = np.array(embed(QUERY)); qv /= np.linalg.norm(qv)
    scored = []
    for d in CORPUS:
        v = np.array(embed(_text(d))); v /= np.linalg.norm(v)
        scored.append((float(qv @ v), d))
    top = [d for _, d in sorted(scored, reverse=True)[:k]]
    L.detail("similarity to query: " + ", ".join(f"{d}({s:.2f})" for s, d in sorted(scored, reverse=True)))
    return top


def main():
    L.section("GRAPHRAG GENERATION — with vs without the graph")
    L.step(f"QUERY: {QUERY}")

    # ---- WITHOUT graph: vector RAG ----
    L.step("WITHOUT graph: plain vector RAG", level=2,
           why="retrieval by similarity alone only surfaces the doc whose wording matches the query — "
               "it can't reach a related doc that shares a cause but is worded differently.")
    v_docs = vector_docs()
    L.detail(f"vector docs: {v_docs}")
    v_ans = _answer("\n\n".join(f"[{d}]\n{_text(d)}" for d in v_docs))
    L.detail(f"RESPONSE: {v_ans}")

    # ---- WITH graph: link -> traverse -> answer ----
    L.step("WITH graph: link -> traverse -> answer", level=2,
           why="linking the query to graph entities and walking edges pulls in the connected docs "
               "(the prior incident, the runbook) that vector search misses.")
    seeds = link(QUERY)
    g_docs, _ = traverse(seeds)
    L.detail(f"graph docs: {g_docs}")
    g_ans = _answer("\n\n".join(f"[{d}]\n{_text(d)}" for d in g_docs))
    L.detail(f"RESPONSE: {g_ans}")

    # ---- score both answers against the required fact ----
    L.step("judge both answers against the required fact", level=2,
           why="an LLM judge checks whether each answer conveys the prior incident + the prevention.")
    v_m = judge_answer(QUERY, v_ans, MUST_CONVEY, [], [])["mention"]
    g_m = judge_answer(QUERY, g_ans, MUST_CONVEY, [], [])["mention"]
    L.section("RESULT")
    L.step(f"names prior incident + prevention?   without {v_m:.2f} {'✅' if v_m>=0.99 else '❌'}"
           f"    with {g_m:.2f} {'✅' if g_m>=0.99 else '❌'}")
    L.step("DEMO STATUS: " + ("✅ graph turns a wrong answer into a right one"
                              if v_m < 0.5 and g_m >= 0.99 else "⚠ re-run (LLM variance)"))


if __name__ == "__main__":
    main()
