# Evidence sessions (GeoHackathon 2026)

Copies of the agent sessions cited in the technical report and in `Appendix_A_Agent_Evidence.md`
(the appendix is generated from these files by `python -m gemini_agent.evidence`).

Provenance: the nine `qwen3:4b-instruct-2507` sessions from 15:19 on 5 Nov 2026 are the final batch (one code version of the agent, identical to this commit; laptop CPU via SSH tunnel; memory reset to the seed at batch start). The two `qwen3:8b` sessions (10:24 and 10:33) are a drop-in check run earlier the same day, before the last verifier upgrade. The two `20261104-*` qwen2.5:7b sessions are kept as claim-check failure examples from the model bake-off period.

| Session | Scenario | Model · LLM host |
|---|---|---|
| 20261104-113804-7248 | S5 follow-up what-ifs · lean · claim-check failure example | qwen2.5:7b · VPS CPU |
| 20261104-142656-3676 | S5 follow-up what-ifs · lean · claim-check failure example | qwen2.5:7b · VPS CPU |
| 20261105-102426-8628 | S6 missing model (Model Forge) · lean | qwen3:8b · laptop CPU |
| 20261105-103313-9944 | S1 full design (batch) · lean | qwen3:8b · laptop CPU |
| 20261105-151955-ba06 | S1 full design (batch) · lean | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-152650-fb88 | S2 incomplete request · lean | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-153710-2e45 | S5 follow-up what-ifs · lean | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-154654-03db | S3 off-topic question · lean | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-154819-a047 | S4 infeasible request · lean | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-154853-e96a | S2 incomplete request · deep | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-161158-b038 | S6 missing model (Model Forge) · lean | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-162349-2ea3 | S6 missing model (Model Forge) · deep | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| 20261105-164203-9ead | S1 full design (batch) · deep | qwen3:4b-instruct-2507-q4_K_M · laptop CPU |
| bakeoff/ | 8 micro-tasks per model | 7 open-weight models |
| router/router_eval.json | router calibration on 40 labelled turns | qwen3:4b-instruct-2507 |
| memory_AGENTS.md | the agent's persistent memory after the evidence batch (lessons written by verifier rejections) | — |
| run_evidence.sh | the batch script that produced the sessions | — |

Each session: `transcript.md` (the readable transcript: prompts, answers, rejected drafts, harness notes, tokens and tool calls per turn), `meta.json` (incl. `llm_host`, `inputs`, `memory_at_start`), `transcript.jsonl` (per turn: answer, verifier result, rejected first draft, harness notes, memory lessons written, tokens, tool sequence), `trace.jsonl` (every LLM and tool call with tokens and latency), `ledger.jsonl` (fact ledger), `gemini_project_*.json` (native GEMINI exports), `agent_generated_*.py` (Model Forge output).
