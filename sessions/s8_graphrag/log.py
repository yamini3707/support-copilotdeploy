"""
Tiny neat logger for the GraphRAG steps — narrates every step and the reason WHY.

Levels of output:
  section(title)          a big banner for a phase
  step(msg, why=...)      a numbered/bulleted step, optionally with an elaborate reason
  detail(msg)            a fine-grained sub-line (per entity, per candidate) — gated by VERBOSE
Set VERBOSE = False for a quieter run (keeps sections + steps, drops the fine detail).
"""

import textwrap

VERBOSE = True          # flip to False to hide the fine-grained per-item detail lines
_IND = "    "           # one indent level


def section(title):
    print("\n" + "═" * 94)
    print(f"  {title}")
    print("═" * 94)


def step(msg, why=None, level=1):
    print(_IND * level + f"▸ {msg}")
    if why:
        _reason(why, level + 1)


def detail(msg, why=None, level=2):
    if not VERBOSE:
        return
    print(_IND * level + f"· {msg}")
    if why:
        _reason(why, level + 1)


def _reason(why, level):
    width = max(40, 94 - 4 * level - 7)
    for i, line in enumerate(textwrap.wrap(why, width)):
        print(_IND * level + ("why: " if i == 0 else "     ") + line)
