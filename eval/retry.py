"""
retry.py — retry an OpenAI call with exponential backoff on transient rate limits (429 TPM).

Big eval runs bump the per-minute token limit; without this a single 429 leaves a hole in the
results (a case scored 0). We back off and retry. A genuine quota exhaustion
(insufficient_quota) won't recover by waiting, so we re-raise it immediately.

    from eval.retry import call_with_retry
    resp = call_with_retry(client.chat.completions.create, model=..., messages=...)
"""

import time


def call_with_retry(fn, *args, max_retries: int = 6, base_delay: float = 2.0, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            is_rate_limit = "rate_limit" in msg or "429" in msg
            if not is_rate_limit or "insufficient_quota" in msg or attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))   # 2s, 4s, 8s, ...
