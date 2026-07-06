# FDE Build Plan — Project Instructions

## What This Project Is
Aditya's FDE (Founding Data Engineer) job-hunt build plan.
Timeline: Jul 2 – Sep 22, 2026 · 6 hrs/day · 6 days/week · Sunday rest.
Goal: land ₹18+ LPA FDE role by end of September.
Full plan: fde-daily-plan.html (open in browser for the day-by-day breakdown).

## Stack
- LLM: Groq (qwen/qwen3-32b) via OpenAI-compatible SDK — primary
- Local fallback: Ollama (qwen2.5:3b) — set USE_OLLAMA=1 in .env
- Python 3.14, venv at phase1/.venv
- Rate approval project: D:\System_Data\Desktop\Work\Project\Rate Approval\Automation - UI

## Current Phase Progress

### P1 — Agent Foundations (Jul 2–15)
- [x] Jul 2 — Raw agent loop skeleton (phase1/agent.py)
- [x] Jul 3 — Wire first 2 in-process tools (phase1/tools.py)
- [ ] Jul 4 — Complete raw loop end-to-end (add remaining 2 tools, test 5-10 questions)
- [ ] Jul 6 — LangGraph StateGraph skeleton
- [ ] Jul 7 — Conditional edges + tool nodes
- [ ] Jul 8 — Finalize + first commit (milestone)
- [ ] Jul 9 — MCP server with FastMCP
- [ ] Jul 10 — Connect agent to MCP server
- [ ] Jul 11 — Tool quality + error handling
- [ ] Jul 13 — LangSmith tracing
- [ ] Jul 14 — Langfuse side-by-side
- [ ] Jul 15 — HITL gate (phase1-complete milestone)

### P2 — RAG + Text-to-SQL + Doc Intelligence (Jul 16–Aug 5)
### P3 — Production Hardening + Evals (Aug 6–19)
### P4 — Flagship Enterprise Agent (Aug 20–Sep 9)
### P5 — Articulation + Outreach (Sep 9–22)
### P6 — Interviews + Close (Sep 23+)

---

## Testing Before Marking Done

When implementing any feature, function, or pipeline step:

1. First, build it to work on the intended/happy-path case.
2. Then, before telling me it's done, automatically test it against:
   - malformed or unexpected input/tool output
   - an empty or missing result
   - the operation being interrupted or failing mid-way
   - the most ambiguous case relevant to this feature
3. Show me what happened in each case, and fix anything that breaks ungracefully, before reporting the task complete.

Do this by default, without me asking each time.
