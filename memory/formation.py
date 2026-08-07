"""
The WRITE path — memory formation.

When a ticket ends, distill it into long-term memory:
  - append an EPISODIC record to the customer's history (what they wanted + how it ended), and
  - extract any DURABLE facts/preferences and add them to SEMANTIC memory.

One LLM call summarizes + extracts; the actual writes go through the MemoryStore primitives
(add_history / add_semantic), which dedupe. Store stays pure-data; the LLM lives here.

    from memory.formation import form_memory
    form_memory(store, cid, ticket, agent_outcome)   # call this when a ticket conversation ends
"""

import json
import os
import sys
import uuid

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from eval.retry import call_with_retry


def _today():
    ws = json.load(open(os.path.join(ROOT, "data", "world_state.json")))
    return (ws.get("_meta") or {}).get("today") or "2026-03-15"     # frozen sim clock


def form_memory(store, cid, ticket, outcome):
    """Distill a finished ticket into memory. Returns what was written."""
    resolved = not bool(outcome.get("requires_human"))
    system = (
        "A support ticket just ended. Produce a long-term MEMORY record for THIS specific customer.\n"
        "Return JSON:\n"
        '{"summary": "one concise line — what the customer wanted and how it ended",\n'
        ' "durable_facts": ["lasting preferences or facts about THIS customer worth recalling in '
        'FUTURE tickets — a language preference, their environment/integrations, a recurring '
        'constraint. Only durable facts, NOT one-off details. [] if none."]}')
    user = f"TICKET:\n{ticket}\n\nAGENT REPLY:\n{outcome.get('answer', '')}\n\nRESOLVED: {resolved}"
    from openai import OpenAI
    r = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    rec = json.loads(r.choices[0].message.content)
    summary = (rec.get("summary") or "").strip()
    facts = [f.strip() for f in rec.get("durable_facts", []) if f and f.strip()]

    store.add_history(cid, {"ticket_id": f"t_{uuid.uuid4().hex[:6]}", "date": _today(),
                            "category": outcome.get("category", "other"),
                            "resolved": resolved, "summary": summary})
    for f in facts:
        store.add_semantic(cid, f)
    return {"summary": summary, "durable_facts": facts, "resolved": resolved}
