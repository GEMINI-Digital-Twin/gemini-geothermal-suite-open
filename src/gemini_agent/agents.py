"""Deep-agent assembly: open-weight LLM + skills + memory + specialist subagents.

Profiles
--------
deep  Orchestrator plans (todos) and delegates to three specialists through the
      ``task`` tool: requirements-analyst, design-engineer, risk-verifier.
lean  One agent with all tools (fewest tokens; baseline for the bake-off).

Both use deepagents' planning, skills (progressive disclosure from
``workspace/skills``) and persistent memory (``memory/AGENTS.md``).

LLM: Ollama (default, local, open-weight) or any OpenAI-compatible endpoint
(``GEODESIGN_PROVIDER=openai``, ``OPENAI_BASE_URL``, ``OPENAI_API_KEY`` --
placeholder only, e.g. a vLLM/llama.cpp server hosting the same open weights).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware

from gemini_agent.tools import Session, build_tools

PKG_WS = Path(__file__).resolve().parent / "workspace"

SYSTEM_PROMPT = """You are GeoDesign, an engineering agent that designs geothermal district \
heating and cooling \
systems with GEMINI digital-twin physics tools.

RULES
1. Never invent numbers. Every engineering number must come from a tool result; cite it as [F<n>].
2. Stay in scope (geothermal heating/cooling design for the loaded brief). Off-topic: one
sentence, no tools.
3. Hard limits come from get_brief. Refuse infeasible requests and propose the closest feasible
option.
4. Missing input that changes the design: call ask_user once with a concrete question and a default.
5. Only recommend a design whose checks all pass ("feasible": true).
6. Skills hold domain knowledge: read a skill's SKILL.md before using it (read_file).
7. Be brief: act through tool calls; keep text between tool calls to one short sentence.
8. Never ask the user for data a tool can provide (demand, brief, models, results): call the tool.
9. Quote numbers with the unit given in the tool result field name (e.g. *_eur_per_mwh ->
EUR/MWh, co2_t -> t).
10. Final answer: at most 150 words -- the design (with its design_id), 3-6 key numbers with
[F<n>], and the main reasons. No tables, no repeated lists.

PROCEDURE for a design request
1. write_todos with your plan.
2. Requirements: get_brief, analyze_demand, list_gemini_models. If the user has not stated the \
cost vs CO2 priority, call ask_user ONCE about it. The site is not in the brief: never ask for it; \
call fetch_weather without coordinates (documented default site, logged as an assumption).
3. Subsurface screening: reservoir_at_depth for 2-3 depths between 2000 and 3500 m (reference
2500 m); \
well_performance at 300 m3/h.
4. search_designs with the objective: balanced for a balance or "low CO2 at reasonable cost" \
(CO2 priced at \
200 EUR/t); min_lcoe only for "cheapest"; min_co2 only if the user accepts any cost. If the \
result carries a \
trade_off_vs_balanced note, present the balanced design unless the user accepted any cost, and \
state the trade-off.
5. verify_design on the best design (stress tests, uncertainty, sensitivity, GEMINI solver
check and \
package in one call). If a check fails: add_capacity_margin with the part it names, then
verify_design again.
6. Give the final answer (rule 10); the harness checks every number automatically."""

LEAN_SUFFIX = "\nYou have all tools yourself; do not delegate."
DEEP_SUFFIX = """
DELEGATION: use the task tool; do not read skills yourself (the specialists do). Always in this
order:
requirements-analyst -> step 2; design-engineer -> steps 3-4 (it returns the FINAL design_id);
then ALWAYS
risk-verifier -> step 5 on that design_id before you answer; model-builder -> only when a
needed model is missing.
Give each a precise instruction and ask for fact IDs. Write the final answer about the design
the risk-verifier
approved, from their reports."""

SUBAGENTS = {
    "requirements-analyst": {
        "description": "Reads the brief and demand, lists GEMINI model coverage, identifies "
        "missing "
        "inputs and asks the user. Returns a brief card with fact IDs.",
        "tools": ["get_brief", "analyze_demand", "list_gemini_models", "ask_user", "fetch_weather"],
        "prompt": "You are the requirements analyst. Use your tools, then return a short brief "
        "card: demand peaks/energies, constraints, missing inputs (with defaults), model gaps. "
        "The site is not in the brief: do not ask for it; fetch_weather without coordinates uses "
        "the documented default site. Cite fact IDs [F<n>]. Never invent numbers.",
    },
    "design-engineer": {
        "description": "Screens reservoir depths and well performance with GEMINI, runs the design "
        "search/optimisation and compares alternatives. Returns ranked designs with IDs.",
        "tools": [
            "reservoir_at_depth",
            "well_performance",
            "evaluate_design",
            "search_designs",
            "compare_designs",
            "add_capacity_margin",
        ],
        "prompt": "You are the design engineer. Screen 2-3 depths between 2000 and 3500 m "
        "(reference "
        "2500 m), then run search_designs with the "
        "requested objective. Objective: balanced for a balance or 'low CO2 at reasonable cost', min_lcoe only "  # noqa: E501
        "for 'cheapest', min_co2 only if any cost is accepted (then present the balanced design if the "  # noqa: E501
        "result notes a trade_off_vs_balanced). Return the FINAL design_id (if you changed the design, e.g. with "  # noqa: E501
        "add_capacity_margin, the new one), the main alternatives and why "
        "(deeper wells vs heat pump, cooling technology, gas handling), with fact IDs. "
        "Read skills geothermal-subsurface and heat-upgrade-and-cooling first.",
    },
    "model-builder": {
        "description": "Creates a missing component model with the Model Forge (declarative "
        "spec -> tested "
        "GEMINI component) and evaluates it, e.g. seasonal storage, network losses.",
        "tools": ["list_gemini_models", "seasonal_balance", "generate_model", "run_model"],
        "prompt": "You are the model builder. Read skill model-forge (read_file "
        "/skills/model-forge/SKILL.md). "
        "Check list_gemini_models; if the needed model is missing, write a JSON spec and call "
        "generate_model. If it reports problems, fix the spec and retry (max 3 times). Then use "
        "run_model with inputs from tools (e.g. seasonal_balance). Report fact IDs.",
    },
    "risk-verifier": {
        "description": "Stress-tests and Monte-Carlo-tests a design, fixes robustness gaps, "
        "and checks "
        "that every number in a draft is traceable. Returns pass/fail with fact IDs.",
        "tools": [
            "verify_design",
            "stress_test_design",
            "uncertainty_analysis",
            "add_capacity_margin",
            "compare_designs",
            "check_numbers",
            "evaluate_design",
            "export_gemini_project",
            "sensitivity_analysis",
            "break_even_analysis",
        ],
        "prompt": "You are the risk & verification engineer. Run verify_design on the given "
        "design_id "
        "(stress tests, uncertainty, sensitivity, GEMINI solver check, package). If a check fails, "
        "use add_capacity_margin and verify_design the new design. If given a draft text, run "
        "check_numbers and list unsupported numbers. Report with fact IDs.",
    },
}

TODO_PROMPT = (
    "PLANNING: for a multi-step task call write_todos once with 4-7 short steps (status "
    "pending/in_progress/completed) and update it as steps finish. Skip it for one-step requests."
)
TODO_TOOL_DESC = (
    "Create or update your task list. Args: todos = list of {content, status} with status in "
    "pending | in_progress | completed."
)

SHORT_TOOL_DESCRIPTIONS = {
    "read_file": "Read a file from the workspace (e.g. /skills/<name>/SKILL.md). Args: file_path.",
    "ls": "List files in a workspace directory.",
    "write_file": "Write a file in the workspace (e.g. /reports/design.md).",
    "edit_file": "Edit a workspace file (e.g. append a lesson to /memory/AGENTS.md).",
}


def _register_profiles(harness: str = "lean"):
    """Trim deepagents for small local models.

    harness="lean"    : skip deepagents' generic memory/skills middleware (~2,150 tokens of
                        explainers per LLM call); build_agent injects a compact skill index +
                        the memory content instead (same files, same read/edit workflow).
    harness="default" : deepagents' stock memory/skills middleware (baseline for token study).
    """
    profile = HarnessProfile(
        excluded_tools=frozenset({"glob", "grep", "delete", "execute"}),
        tool_description_overrides=SHORT_TOOL_DESCRIPTIONS,
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )
    for key in ("ollama", "openai"):
        register_harness_profile(key, profile)


def skill_index(ws: Path) -> str:
    """Compact skill listing (name: description) parsed from SKILL.md front matter."""
    lines = ["SKILLS (domain knowledge; read_file /skills/<name>/SKILL.md before relying on it):"]
    for md in sorted((ws / "skills").glob("*/SKILL.md")):
        meta = md.read_text(encoding="utf-8").split("---")[1]
        name = re.search(r"name:\s*(.+)", meta).group(1).strip()
        desc = re.search(r"description:\s*(.+)", meta).group(1).strip()
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def memory_block(ws: Path) -> str:
    """Persistent memory content (lessons from earlier sessions)."""
    mem = ws / "memory" / "AGENTS.md"
    body = mem.read_text(encoding="utf-8").strip() if mem.exists() else ""
    return f"MEMORY (/memory/AGENTS.md; append new lessons with edit_file):\n{body}"


# Bake-off winner (runs/bakeoff): non-thinking Qwen3 4B -- 6/8 tasks, ~40 s/call on 6 CPU cores.
# Note: Ollama's plain "qwen3:4b" tag is the 2507 *thinking* build and ignores think=false.
DEFAULT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def make_model(model: str | None = None, temperature: float = 0.0, num_ctx: int = 16384):
    """Chat model for the configured provider (open-weight by default)."""
    provider = os.environ.get("GEODESIGN_PROVIDER", "ollama")
    model = model or os.environ.get("GEODESIGN_MODEL", DEFAULT_MODEL)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", "PLACEHOLDER-not-used-for-local-servers"),
        )
    from langchain_ollama import ChatOllama

    kwargs = {}
    if model.startswith("qwen3"):
        kwargs["reasoning"] = os.environ.get("GEODESIGN_THINK", "0") == "1"
    # llama.cpp threads synchronise at barriers: on a shared/oversubscribed CPU fewer threads
    # are much faster (measured on the dev VM: 2 threads -> 1.9 tok/s, 4 -> 0.15 tok/s).
    num_thread = (
        int(os.environ.get("GEODESIGN_THREADS", "0")) or None
    )  # 0 = Ollama decides; use 2 on a busy shared CPU
    return ChatOllama(
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
        num_thread=num_thread,
        num_predict=int(os.environ.get("GEODESIGN_MAX_TOKENS", "600")),
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        keep_alive="30m",
        **kwargs,
    )


def prepare_workspace(root: Path) -> Path:
    """Runtime workspace: read-only skills copy + persistent memory (seeded once)."""
    root.mkdir(parents=True, exist_ok=True)
    if (root / "skills").exists():
        shutil.rmtree(root / "skills")
    shutil.copytree(PKG_WS / "skills", root / "skills")
    (root / "memory").mkdir(exist_ok=True)
    mem = root / "memory" / "AGENTS.md"
    if not mem.exists():
        shutil.copy(PKG_WS / "memory" / "AGENTS.md", mem)
    (root / "reports").mkdir(exist_ok=True)
    return root


def build_agent(
    session: Session,
    profile: str = "deep",
    model=None,
    workspace: Path | None = None,
    harness: str = "lean",
    checkpointer=None,
):
    """Compile the deep agent for a session."""
    _register_profiles(harness)
    llm = model if model is not None and not isinstance(model, str) else make_model(model)
    ws = prepare_workspace(workspace or Path("runs/workspace"))
    tools = build_tools(session)
    by_name = {t.name: t for t in tools}
    if profile == "lean":
        prompt, subagents, main_tools = SYSTEM_PROMPT + LEAN_SUFFIX, [], tools
    else:
        prompt = SYSTEM_PROMPT + DEEP_SUFFIX
        subagents = [
            {
                "name": n,
                "description": d["description"],
                "system_prompt": d["prompt"],
                "tools": [by_name[t] for t in d["tools"]],
            }
            for n, d in SUBAGENTS.items()
        ]
        main_tools = [
            by_name[n]
            for n in ("ask_user", "check_numbers", "save_design_package", "compare_designs")
        ]
    if harness == "lean":
        prompt = f"{prompt}\n\n{skill_index(ws)}\n\n{memory_block(ws)}"
        for sa in subagents:
            sa["system_prompt"] += "\n\n" + skill_index(ws)
    # Planning tool with a compact prompt (~100 tokens instead of ~1,300 for the stock text).
    middleware = [TodoListMiddleware(system_prompt=TODO_PROMPT, tool_description=TODO_TOOL_DESC)]
    return create_deep_agent(
        model=llm,
        tools=main_tools,
        system_prompt=prompt,
        middleware=middleware,
        subagents=subagents,
        skills=["/skills/"] if harness == "default" else None,
        memory=["/memory/AGENTS.md"] if harness == "default" else None,
        backend=FilesystemBackend(root_dir=str(ws), virtual_mode=True),
        checkpointer=checkpointer,
        name="geodesign",
    )
