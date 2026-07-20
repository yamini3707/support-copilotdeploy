# CloudDesk Support Copilot

An **eval-driven** build of an AI support agent for a fictional B2B SaaS company (CloudDesk).
We build **one** project across the course and add **one capability at a time** — and every
capability has to *prove its value by moving a score* on a graded test set. Show, don't tell.

The brief students work from: [`docs/CloudDesk_Support_Copilot_Challenge.pdf`](docs/CloudDesk_Support_Copilot_Challenge.pdf).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your OpenAI key (+ Weaviate creds for the RAG week)
```

All code reads credentials from `.env` — nothing is hard-coded. `.env` is git-ignored; never commit it.

## Layout

```
data/            world_state.json (the company), train.json (graded cases), rag_cases.json (RAG cases)
data_gen/        scripts that generate the data above (+ labeling.py = the priority rule)
eval/            the scorer: schema, scoring rubric, LLM-as-judge, harness, retry
tools/           the agent's tools (read tools + logging stubs) and their function-calling schemas
SUPPORT_PLAYBOOK.md   the rules that define every label (categories, priority, escalation)
sessions/
  s1_classifier/          ticket classifier + first eval run
  s2_prompt_engineering/  prompt strategies, measured
  s3_tools/               tools + the agentic loop (LLM in a loop with tools)
  s4_router_specialists/  router → specialists graph (LangGraph)
  s5_rag/                 RAG — see the homework below
kb/              the knowledge-base corpus (policies, how-tos, troubleshooting, distractors)
```

## How the sessions map to class

| Session | Idea | Score arc |
|---|---|---|
| S1 | classify tickets; stand up the eval harness | ~30/100 baseline (most dimensions honestly at 0) |
| S2 | prompt engineering, done empirically | routing improves; overall barely moves — prompting has a ceiling |
| S3 | tools + the agentic loop | tool_use 0→~74, grounded climbs |
| S4 | router → specialists (LangGraph), tool scoping | ~60/100; isolation is the real win |
| S5 | **RAG** — retrieval for the facts that live in *documents* | **this week's homework** |

## This week — RAG homework

In class we saw retrieval **fail** (`python3 sessions/s5_rag/retrieval_failures.py`). Your job is to
build the retriever that makes those failures reproducible, then fix them. Full instructions:
[`sessions/s5_rag/HOMEWORK.md`](sessions/s5_rag/HOMEWORK.md).
