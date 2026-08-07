"""
Guardrails that wrap the agent's OUTPUT.

The course built three guardrail layers; here is where each one lives in the deployed service:
  - access_control   (deterministic, WHOSE data): folded into app/agent.py `_run_tool` — a cross-account
    tool call is blocked before it runs.
  - output_redaction (LLM, this file): the disclosure filter below scrubs internal reasoning / named
    execs / internal financials from the reply AFTER generation, before it reaches the customer.
  - ingest_visibility (deterministic backstop): tag chunks public/internal at ingest and filter
    `visibility != internal` for external callers, so private content never reaches the answer LLM.
    That lives at the RAG/ingest layer (guardrails/ingest_visibility); the output filter here is the
    paraphrase-proof complement to it.
"""

import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from eval.retry import call_with_retry

_DISCLOSURE_SYSTEM = (
    "You are a disclosure filter for a customer-facing support reply. Ensure it NEVER exposes "
    "confidential or internal information.\n\n"
    "REMOVE entirely — do not reveal, even paraphrased, softened, or generalized — any of:\n"
    "- the internal REASONING or RATIONALE behind a company decision or policy: WHY it was chosen, "
    "what trade-offs were weighed (e.g. better customer experience vs. revenue/cost), or what the "
    "company was trying to protect or avoid (e.g. revenue loss, margins, churn, financial impact). "
    "A decision that would improve customer experience but cost the company money, so the company "
    "chose the cheaper option — that whole line of reasoning is INTERNAL and must not be shared;\n"
    "- internal deliberations, debates or disagreements, and who decided (CEO/CXOs/VPs/named staff);\n"
    "- internal financial figures, revenue or cost estimates or projections;\n"
    "- unreleased plans or anything a company keeps private.\n\n"
    "KEEP only the plain customer-facing FACT (e.g. 'refunds are available within 14 days'). Do NOT "
    "explain WHY the policy exists.\n"
    "If the customer asked WHY and the only reason available is internal, do NOT invent or hint at it. "
    "Give a brief, polite, non-committal reply — state the policy and add, in a natural way, that you "
    "don't have the specific reasoning behind that decision to share (it was set as part of the "
    "company's standard terms after internal review).\n\n"
    'Return JSON {"flagged": true|false, "safe_reply": "<the cleaned, customer-safe reply>"}.')


def disclosure_filter(reply: str) -> dict:
    """Scan a customer-facing reply and strip internal/confidential content.
    Returns {'flagged': bool, 'safe_reply': str}. Fails open on the original reply if the call errors."""
    if not reply or not reply.strip():
        return {"flagged": False, "safe_reply": reply}
    from openai import OpenAI
    try:
        r = call_with_retry(OpenAI().chat.completions.create,
            model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _DISCLOSURE_SYSTEM}, {"role": "user", "content": reply}])
        out = json.loads(r.choices[0].message.content)
        return {"flagged": bool(out.get("flagged")), "safe_reply": out.get("safe_reply", reply)}
    except Exception:
        return {"flagged": False, "safe_reply": reply}
