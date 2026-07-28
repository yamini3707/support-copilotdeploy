"""
Minimal OpenAI embeddings with an on-disk cache — vendored so this GraphRAG folder is self-contained.

Every embedding is cached to .emb_cache.json (keyed by a hash of the text), so re-runs are free.
Set OPENAI_API_KEY in your environment (or a .env at the repo root).

    from sessions.s8_graphrag.embeddings import embed
    v = embed("some text")     # -> list[float]
"""

import hashlib
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")))
except ImportError:
    pass

MODEL = os.getenv("SUPPORT_COPILOT_EMBED_MODEL", "text-embedding-3-small")
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".emb_cache.json")
_cache = json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}


def _key(text: str) -> str:
    return hashlib.sha1((MODEL + "\n" + text).encode()).hexdigest()


def embed_many(texts: list) -> list:
    from openai import OpenAI
    client = OpenAI()
    missing = list({t for t in texts if _key(t) not in _cache})     # only embed unseen texts
    for i in range(0, len(missing), 256):                           # OpenAI allows many inputs per call
        batch = missing[i:i + 256]
        resp = client.embeddings.create(model=MODEL, input=batch)
        for t, d in zip(batch, resp.data):
            _cache[_key(t)] = d.embedding
    if missing:
        json.dump(_cache, open(CACHE_FILE, "w"))                    # persist the cache
    return [_cache[_key(t)] for t in texts]


def embed(text: str) -> list:
    return embed_many([text])[0]
