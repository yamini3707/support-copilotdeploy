"""
Thread-safe OpenAI embeddings with a disk cache (needed because the unified pipeline runs strategies
in PARALLEL, so several threads embed at once).

The OpenAI API call happens OUTSIDE the lock (so parallel embeds still overlap); only the shared cache
read / update / save is guarded by a lock — that's what the non-thread-safe rag/embeddings tripped on.
"""

import hashlib
import json
import os
import threading

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")))
except ImportError:
    pass

MODEL = os.getenv("SUPPORT_COPILOT_EMBED_MODEL", "text-embedding-3-small")
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".emb_cache.json")
_lock = threading.Lock()
_cache = json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}


def _key(text):
    return hashlib.sha1((MODEL + "\n" + text).encode()).hexdigest()


def embed_many(texts):
    from openai import OpenAI
    with _lock:                                              # snapshot which texts we still need
        missing = list({t for t in texts if _key(t) not in _cache})
    if missing:
        client, fresh = OpenAI(), {}
        for i in range(0, len(missing), 256):               # API call OUTSIDE the lock
            batch = missing[i:i + 256]
            resp = client.embeddings.create(model=MODEL, input=batch)
            for t, d in zip(batch, resp.data):
                fresh[_key(t)] = d.embedding
        with _lock:                                         # update + persist under the lock
            _cache.update(fresh)
            with open(CACHE_FILE, "w") as f:
                json.dump(_cache, f)
    with _lock:
        return [_cache[_key(t)] for t in texts]


def embed(text):
    return embed_many([text])[0]
