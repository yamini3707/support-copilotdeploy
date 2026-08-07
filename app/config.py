"""
App configuration + singletons.

Importing this module (a) loads .env, (b) imports app.agent FIRST so the Langfuse-instrumented
OpenAI client is swapped in before anything makes a call, and (c) boots the memory service once.
Everything else imports the shared MEMORY from here.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# import the agent first: it swaps in langfuse.openai so every downstream OpenAI call is traced
import app.agent  # noqa: F401  (side effect: instrument OpenAI + build the graph)
from app.memory_service import MemoryService

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")

# one process-wide, boot-once memory service (in-memory; resets on restart)
MEMORY = MemoryService().boot()
