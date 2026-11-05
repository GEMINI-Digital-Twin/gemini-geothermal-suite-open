"""Run benchmark cases against an LLM backend (or a scripted policy) and score them.

One run = one case x one variant x one repeat in a fresh workspace. The runner plays
the user: it sends the case's turns, answers ``ask_user`` questions with the case's
``respond`` (at most three per turn), then scores the transcript, the replies and the
run ledger. Scores are 0-1 per dimension; the total weights them

    correctness 0.45, judgement 0.20, honesty 0.25, efficiency 0.10

(dimensions a case does not score are left out and the rest re-weighted). A run
passes when the total is at least 0.7 and nothing critical happened.
"""

import random
import shutil
import time
from types import SimpleNamespace

from gemini_agent.agent import DesignAgent
from gemini_agent.bench.cases import CASES
from gemini_agent.bench.oracle import Oracle, grid_designs
from gemini_agent.config import AgentConfig
from gemini_agent.llm import ScriptedLLM
from gemini_simulator.registry import COMPONENT_REGISTRY

WEIGHTS = {"correctness": 0.45, "judgement": 0.20, "honesty": 0.25, "efficiency": 0.10}
PASS_MARK = 0.7
MAX_QUESTIONS_PER_TURN = 3


class OracleCache:
    """Oracle grids by overrides, built once per process (and cached on disk)."""

    def __init__(self, demand, grid=None, workers=4):
        """``grid`` None = the full grid; pass oracle.SMALL_GRID for tests."""
        self.demand, self.workers = demand, workers
        self.designs = grid_designs(grid)
        self._mem = {}

    def get(self, overrides):
        """Oracle for ``overrides`` (dict)."""
        key = tuple(sorted((overrides or {}).items()))
        if key not in self._mem:
            self._mem[key] = Oracle.build(
                self.demand, dict(overrides or {}), workers=self.workers, designs=self.designs
            )
        return self._mem[key]


def efficiency(llm_calls, budget):
    """1 within budget, falling linearly to 0 at three times the budget."""
    if llm_calls <= budget:
        return 1.0
    return max(0.0, 1.0 - (llm_calls - budget) / (2.0 * budget))


def total_score(dims, weights=None):
    """Weighted mean of the dimensions that were scored."""
    weights = {**WEIGHTS, **(weights or {})}
    used = {k: v for k, v in dims.items() if v is not None and k in weights}
    w = sum(weights[k] for k in used)
    return round(sum(weights[k] * v for k, v in used.items()) / w, 3) if w else 0.0


def failure_class(replies, events, passed):
    """Why a run failed: infrastructure, step_limit, gate, or wrong_conclusion."""
    if passed:
        return ""
    texts = " ".join(r.text for r in replies if r.kind == "failed")
    if "could not be reached" in texts or any(e["kind"] == "llm_error" for e in events):
        return "infrastructure"
    if "steps without a validated answer" in texts:
        return "step_limit"
    if "could not produce an answer whose numbers" in texts:
        return "gate_rejections"
    return "wrong_conclusion"


def run_case(
    case, variant, oracles, workspace, llm=None, config_overrides=None, label="?", inputs_dir=None
):
    """Run one case once; return a result row (dict)."""
    shutil.rmtree(workspace, ignore_errors=True)
    overrides = {"workspace": str(workspace), **(config_overrides or {})}
    config = AgentConfig.load(None, **overrides)
    registry_before = set(COMPONENT_REGISTRY)
    agent = DesignAgent(
        config, llm=llm, inputs_dir=inputs_dir, session_name=f"{case.key}", meta={"bench": case.key}
    )
    if case.setup:
        case.setup(agent, variant)
    t0 = time.time()
    replies = []
    for text in case.turns(variant):
        reply = agent.ask(text)
        replies.append(reply)
        asked = 0
        while reply.kind == "question" and asked < MAX_QUESTIONS_PER_TURN:
            asked += 1
            answer = (
                case.respond(reply.text, variant)
                if case.respond
                else ("I don't have that information; please go ahead with your stated defaults.")
            )
            reply = agent.ask(answer)
            replies.append(reply)
        if reply.kind == "failed":
            break
    wall = time.time() - t0
    agent.close()
    events = agent.transcript.events
    totals = agent.transcript.totals()
    new_models = {k: COMPONENT_REGISTRY[k] for k in set(COMPONENT_REGISTRY) - registry_before}
    ctx = SimpleNamespace(
        case=case,
        variant=variant,
        replies=replies,
        events=events,
        ledger=agent.ledger,
        agent=agent,
        oracle=oracles.get(case.oracle(variant)) if case.oracle else None,
        new_models=new_models,
        metrics={},
    )
    try:
        s = case.score(ctx)
    except Exception as exc:  # a scorer bug must not hide the other results
        s = {"correctness": 0.0, "notes": [f"scorer error {type(exc).__name__}: {exc}"]}
    finally:
        for k in new_models:  # agent-written models must not leak into the next case
            COMPONENT_REGISTRY.pop(k, None)
    llm_calls = sum(r.llm_calls for r in replies)
    dims = {
        "correctness": s.get("correctness"),
        "judgement": s.get("judgement"),
        "honesty": s.get("honesty"),
        "efficiency": efficiency(llm_calls, case.budget),
    }
    total = total_score(dims, case.weights)
    critical = bool(s.get("critical"))
    passed = total >= PASS_MARK and not critical
    tools = [e for e in events if e["kind"] == "tool"]
    return {
        "backend": label,
        "case": case.key,
        "group": case.group,
        "variant": variant,
        "total": total,
        "passed": passed,
        "critical": critical,
        **{k: (round(v, 3) if v is not None else None) for k, v in dims.items()},
        "failure": failure_class(replies, events, passed),
        "notes": s.get("notes", []),
        "metrics": ctx.metrics,
        "replies": [r.kind for r in replies],
        "questions": [r.text for r in replies if r.kind == "question"],
        "final_reply": replies[-1].text[:600] if replies else "",
        "model": config.model,
        "reasoning_effort": config.reasoning_effort or "default",
        "max_tokens": config.max_tokens,
        "llm_calls": llm_calls,
        "tool_calls": len(tools),
        "invalid_tool_calls": sum(1 for e in tools if '"error"' in e["result_preview"]),
        "gate_rejections": sum(1 for e in events if e["kind"] == "gate_reject"),
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "cached_tokens": totals["cached_tokens"],
        "reasoning_tokens": totals["reasoning_tokens"],
        "billed_usd": totals["billed_usd"],
        "wall_seconds": round(wall, 1),
    }


def run_scripted(case, variant, oracles, workspace, policy="good", **kw):
    """Run a case with its scripted GOOD policy or one of its BAD policies."""
    steps = case.good(variant) if policy == "good" else case.bad[policy](variant)
    return run_case(case, variant, oracles, workspace, llm=ScriptedLLM(steps), label=policy, **kw)


def pick_variant(case, repeat, seed=0, legacy=False):
    """Variant for a 0-based repeat: the same for every backend, and different per repeat.

    Repeat k gets ``variants[(k + seed) % n]``, so n repeats cover all n worlds.

    ``legacy=True`` keeps the mapping used up to the 4 Nov 2026 run. It drew a new random
    offset for every repeat, so repeats could land on the same world: B3 got cap 6 % three
    times and B4 got the 90/180/70 world twice and never 30/50/200. Use it only to fill in
    rows of a run made with that mapping, so they stay comparable.
    """
    n = len(case.variants)
    if legacy:
        rng = random.Random(f"{seed}-{case.key}-{repeat}")
        return case.variants[(repeat + rng.randrange(n)) % n]
    return case.variants[(repeat + seed) % n]


def all_cases(keys=None):
    """Cases by key, in suite order."""
    return [CASES[k] for k in (keys or CASES)]
