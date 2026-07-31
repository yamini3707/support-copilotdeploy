"""
Tiny tracing helper for I/O spans (Weaviate queries, etc.).

`span(name, **meta)` is a context manager that:
  - adds a Langfuse child span ONLY when we're already inside an active trace (so the agent run nests
    it under the current strategy span),
  - is a no-op otherwise (standalone ingest / plain scripts) — so it never spawns orphan traces and
    never requires Langfuse to be configured.

This is how we capture DB/network latency that the auto-traced OpenAI calls don't cover.
"""

import contextlib

from opentelemetry import trace as _otel


@contextlib.contextmanager
def span(name, **meta):
    current = _otel.get_current_span()
    if not getattr(current, "is_recording", lambda: False)():   # no active trace -> no-op
        yield None
        return
    try:
        from langfuse import get_client
        with get_client().start_as_current_observation(name=name, as_type="span") as s:
            if meta:
                s.update(metadata=meta)
            yield s
    except Exception:
        yield None          # never let tracing break the actual work
