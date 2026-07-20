"""
schema.py — the agent's response contract.

The agent's job is a full support reply, even though most of it is empty at first:
  category, priority, requires_human, confidence  — routing (works now)
  answer                                          — the customer-facing reply (works now, thin)
  citations                                       — doc_ids grounding the answer (empty until RAG)
  tool_calls                                      — tools the agent used (empty until tools)

Cases are graded on ALL of these (see scoring.py), so an agent that only routes + writes a
one-liner scores low — that gap is the room later sessions reclaim.
"""

CATEGORIES = ["billing", "technical", "account", "feature_request", "other"]
PRIORITIES = ["low", "medium", "high", "urgent"]

REQUIRED = ["category", "priority", "requires_human", "confidence", "answer"]


def validate(response: dict) -> list[str]:
    """Return a list of schema errors (empty = valid)."""
    errors = []
    for field in REQUIRED:
        if field not in response:
            errors.append(f"missing required field: {field}")

    if response.get("category") not in CATEGORIES:
        errors.append(f"category must be one of {CATEGORIES}, got {response.get('category')!r}")
    if response.get("priority") not in PRIORITIES:
        errors.append(f"priority must be one of {PRIORITIES}, got {response.get('priority')!r}")
    if not isinstance(response.get("requires_human"), bool):
        errors.append("requires_human must be a bool")
    conf = response.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        errors.append(f"confidence must be a number in 0..1, got {conf!r}")
    if not isinstance(response.get("answer"), str) or not response.get("answer"):
        errors.append("answer must be a non-empty string")

    return errors
