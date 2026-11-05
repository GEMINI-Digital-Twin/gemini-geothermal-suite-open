"""Optional decision router: one calibrated multiple-choice call before the agent (Jev/SemIf \
pattern).

Method and sources:
  * option probabilities read from next-token logits instead of generated text -- the SemIf
    (formerly OpenJev) method, github.com/TheoLeeCJ/SemIf-OpenJev (MIT); the same log-likelihood
    multiple-choice scoring as EleutherAI's lm-evaluation-harness;
  * temperature scaling for calibration -- Guo et al., "On Calibration of Modern Neural Networks",
    ICML 2017 (SemIf likewise leaves calibration to the user's own labelled data);
  * act only above a confidence threshold, else defer -- selective prediction, Geifman & El-Yaniv,
    "Selective Classification for Deep Neural Networks", NeurIPS 2017;
  * Choice-question idea after TypeSafe's Jev "System One" (proprietary).
SemIf, Kev and NeoHorse-Jev-4B (Apache-2.0) were evaluated as drop-in tools; all expect GPU/BF16
weights and a second model. On a CPU-only VM we implement SemIf's method on Ollama's logprobs API
with the model that already serves the agent: no extra model, memory or dependency.

The open-weight model already serving the agent answers one question -- "what kind of turn is
this?" -- with a single letter. The option probabilities are read from the token log-probabilities
(no text is generated), softened by a temperature fitted on labelled prompts
(``python -m gemini_agent.router_eval``), and the router acts only when it is confident:

  off-topic  -> fixed scope reply, no agent call
  incomplete -> the standard clarifying question (interactive mode, before any design exists)
  anything else, or confidence below the threshold -> the full agent, unchanged

Switch: ``GEODESIGN_ROUTER=1``, ``--router`` on the CLI, or the cockpit checkbox. Off by default.
To remove it: delete this file, router_eval.py, data/router_*, and the ``router`` lines in
runner.py,
cli.py and ui/app.py.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CALIBRATION = DATA / "router_calibration.json"

LABELS = {"A": "design", "B": "follow_up", "C": "off_topic", "D": "incomplete", "E": "infeasible"}

SYSTEM = """You route messages for GeoDesign, an assistant that designs a geothermal district \
heating and cooling system (wells, heat pumps, chillers, boilers, costs, CO2) for a given \
2027 demand.
Classify the user's message. Answer with ONE letter only.
A: a design request that states its goal (cost, CO2 or a balance) or a concrete design to evaluate
B: a follow-up, what-if or question about the current design or its results
C: off-topic: not about designing or analysing this energy system
D: incomplete: a design request that does not say what matters (cost or CO2) or is too vague to
act on
E: infeasible: asks for something that breaks a hard limit (flow 50-300 m3/h per doublet, 1-3
doublets)

Examples:
"Design a geothermal heating and cooling system for the supplied demand. Balance cost and CO2." -> A
"Evaluate 2 doublets at 3100 m with a 10 MW electric chiller." -> A
"What if one doublet fails in January?" (design exists) -> B
"Why not shallower wells with a heat pump?" (design exists) -> B
"Who won the football match yesterday?" -> C
"Write me a poem about rain." -> C
"Make us something for our district." -> D
"Use 4 doublets of 400 m3/h each." -> E"""

OFF_TOPIC_REPLY = (
    "That is outside what I can help with: I design and analyse the geothermal district heating "
    "and cooling system for the supplied 2027 demand (wells, heat upgrade, cooling, backup, "
    "cost and CO2). Ask me about that and I will run the analysis."
)
CLARIFY_QUESTION = (
    "Before I design: what matters most -- lowest cost (LCOE), lowest CO2, or a balance of both? "
    "If you know it, also give the district-heating return temperature (otherwise I assume 50 C)."
)


def _softmax(logprobs: dict[str, float], temperature: float) -> dict[str, float]:
    m = max(logprobs.values())
    w = {k: math.exp((v - m) / temperature) for k, v in logprobs.items()}
    z = sum(w.values())
    return {k: w[k] / z for k in LABELS}


def letter_logprobs(top: list[dict]) -> dict[str, float]:
    """Log-probabilities of the option letters among the first token's top candidates ('C', ' "
    "C', '(C')."""
    out: dict[str, float] = {}
    for t in top:
        k = t["token"].strip(" .:()*_\"'").upper()
        if k in LABELS:
            out[k] = max(out.get(k, -1e9), t["logprob"])  # the best spelling of each letter
    floor = (
        min(out.values(), default=0.0) - 5.0
    )  # a letter missing from the top-k is less likely than all shown
    return {k: out.get(k, floor) for k in LABELS}


class Router:
    """One-letter classification with calibrated confidence through Ollama's /api/chat."""

    def __init__(self, model: str, host: str | None = None, calibration: Path = CALIBRATION):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        cal = json.loads(calibration.read_text()) if calibration.exists() else {}
        self.temperature = float(cal.get("temperature", 1.0))
        self.threshold = float(cal.get("threshold", 0.9))
        self.calibrated = bool(cal)

    def classify(self, message: str, design_exists: bool, previous: str | None = None) -> dict:
        """Label, calibrated probabilities, confidence, token counts and latency for one message."""
        ctx = f"Design already evaluated in this conversation: {'yes' if design_exists else 'no'}."
        if previous:
            ctx += f"\nPrevious user message: {previous[:300]}"
        body = {
            "model": self.model,
            "stream": False,
            "logprobs": True,
            "top_logprobs": 20,
            "keep_alive": "30m",
            "options": {"temperature": 0, "num_predict": 1},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"{ctx}\nMessage: {message}"},
            ],
        }
        t0 = time.time()
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        raw = letter_logprobs((d.get("logprobs") or [{}])[0].get("top_logprobs", []))
        probs = _softmax(raw, self.temperature)
        best = max(probs, key=probs.get)
        return {
            "label": LABELS[best],
            "confidence": round(probs[best], 4),
            "probabilities": {LABELS[k]: round(v, 4) for k, v in probs.items()},
            "raw_logprobs": {LABELS[k]: round(v, 3) for k, v in raw.items()},
            "prompt_tokens": d.get("prompt_eval_count", 0),
            "completion_tokens": d.get("eval_count", 0),
            "latency_s": round(time.time() - t0, 2),
        }

    def reply(self, decision: dict, mode: str, design_exists: bool, answering: bool) -> str | None:
        """The router's own answer, or None to hand the turn to the full agent."""
        if decision["confidence"] < self.threshold:
            return None
        if decision["label"] == "off_topic":
            return OFF_TOPIC_REPLY
        if (
            decision["label"] == "incomplete"
            and mode != "auto"
            and not design_exists
            and not answering
        ):
            return CLARIFY_QUESTION
        return None


def from_env(model: str | None, enabled: bool | None = None) -> Router | None:
    """Router if enabled (argument, else GEODESIGN_ROUTER=1) and the provider is Ollama."""
    on = enabled if enabled is not None else os.environ.get("GEODESIGN_ROUTER", "0") == "1"
    if not on or os.environ.get("GEODESIGN_PROVIDER", "ollama") != "ollama":
        return None
    from gemini_agent.agents import DEFAULT_MODEL

    return Router(model or os.environ.get("GEODESIGN_MODEL", DEFAULT_MODEL))
