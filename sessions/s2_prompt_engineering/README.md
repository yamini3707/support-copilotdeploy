# Session 2 — Prompt engineering, done empirically

**Milestone:** improve the classifier's *routing* — and learn the discipline that separates real
prompt engineering from vibes: **you propose strategies, then you measure. The winner is decided
by the score, not by which idea sounds cleverest.**

We try four strategies on the *same* golden dataset and compare. Two surprises land:
1. the fanciest strategy (a two-stage router) does **not** win;
2. even the best strategy barely moves the **overall** score — because routing is only ~20% of
   the job. Prompt engineering has a ceiling that only tools / RAG / memory can break.

---

## The four strategies (`variants.py`)

| Variant | Idea | Calls/ticket |
|---|---|---|
| `few_shot` | add hand-written worked examples of the hard *edges* | 1 |
| `reasoning` | let the model derive impact/scope step-by-step before the labels | 1 |
| `router` | stage 1 routes category + impact/scope; stage 2 is a category-specialist | 2 |
| `perception` | the LLM only *perceives* (impact/scope); **Python computes priority** with the exact rule | 1 |

## Run it (live in class)

```bash
python3 sessions/s2_prompt_engineering/run.py --fast     # all four, quick leaderboard (no judge)
python3 sessions/s2_prompt_engineering/run.py            # all four, full scoring (LLM judge)
python3 sessions/s2_prompt_engineering/run.py perception  # one variant, full per-case report
```

---

## What we saw (gpt-4o-mini; your live numbers will vary slightly)

Leaderboard (`--fast`):

```
variant        overall  category  invalid
perception       42.1     76.8       0
few_shot         38.1     75.0       0
router           37.7     78.6       0      ← 2 calls/ticket, and still not the winner
reasoning        35.9     75.0       4      ← the scratchpad sometimes leaks into fields
```

Full run of the winner (`perception`) shows the real story in the breakdown:

```
category        76.8      priority  87.5      requires_human  96.4     ← routing now strong
tool_use         0.0      retrieval  0.0      memory           0.0     ← still zero
OVERALL         34.6 / 100    (was ~30 at Session 1)
```

---

## The two lessons (say these out loud)

1. **Measure, don't assume.** The two-stage "router → specialist" is the most sophisticated design
   and costs *double* the API calls — yet it loses to a single-call variant. The winner is the one
   that stopped asking the LLM to do arithmetic and moved the priority *rule into code*
   (`perception`). You could not have known this without running it.
2. **Prompting has a ceiling.** Perfecting the prompt took routing from good to great (priority
   67 → 87), but the **overall barely moved (30 → ~35)**. Why? The agent still can't look up a
   policy, call a tool, or remember a customer — so `tool_use`, `retrieval`, and `memory` are still
   0. That gap is the rest of the course.

## Eval hygiene (important, and a real-world trap)

The few-shot examples in `variants.py` are **hand-written and never reuse a ticket from
`data/train.json`**. Few-shotting with your own test set leaks answers and measures memorisation,
not skill — the score looks great and means nothing. Rule: teach the model with *fresh* examples;
keep your eval set unseen.

## Problems (for students)

1. *(warmup)* Add one more worked example to `few_shot` targeting a case it gets wrong. Does the
   score go up — or does it overfit and hurt another case?
2. *(medium)* `reasoning` produced a few invalid responses. Read them: what leaked into which
   field, and how would you constrain the output to prevent it?
3. *(hard)* Combine strategies: few-shot *perception* + code-computed priority. Measure it. Does
   the combination beat the best single strategy, or just add complexity? (Let the number decide.)

## Deliberate knowledge gap

- We only improved routing. The agent still invents nothing-but-plausible answers with no sources.
  That's why `grounded` is stuck ~14 — Session 3 (tools) and Session 4 (RAG) fix it.
- Which single variant should become the project's classifier going forward? Pick the one your
  live run crowns — and keep it swappable.
