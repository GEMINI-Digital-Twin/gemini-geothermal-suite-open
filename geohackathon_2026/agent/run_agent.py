"""Geothermal design agent using a local open-weight LLM through Ollama.

The LLM plans, picks tools and explains. Tools compute every number and check
every limit. Each session is logged with token counts in logs/.

Run from the project folder:
    PYTHONPATH=../src:cases:agent python agent/run_agent.py "your question"
"""

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from reviewer import RECOMMENDATION, review
from tools import TOOL_SCHEMAS, call_tool

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"
MAX_ROUNDS = 20
MAX_REVIEWS = 3
PEAK_CHECK_FLOW_M3H = 250.0


DEMAND_IN_QUESTION = re.compile(r"(\d+(?:\.\d+)?)\s*MW", re.I)


def unsimulated_demand(question, year_runs):
    """Return a MW value from the question that no yearly run used, if any."""
    used = set()
    for result in year_runs.values():
        used.add(result.get("heating_peak_mw_used"))
        used.add(result.get("cooling_peak_mw_used"))
    for text in DEMAND_IN_QUESTION.findall(question):
        if not any(value is not None and abs(value - float(text)) < 0.01 for value in used):
            return text
    return None


def chosen_numbers_missing(answer, cost_runs, chosen):
    """Return True if the answer leaves out the chosen design's cost and CO2."""
    design = (int(chosen.group(1)), float(chosen.group(2)))
    cost = cost_runs.get(design)
    if cost is None:
        return False
    return f"{cost['levelised_cost_eur_per_mwh']}" not in answer
LOG_DIR = Path(__file__).parent.parent / "logs"

SYSTEM_PROMPT = """You are an engineering agent for the SPE GeoHackathon 2026. You design a deep \
geothermal heating and cooling system for one district, using the tools provided.

Rules:
1. Only help with this geothermal design task. If a request is unrelated, say so in one \
sentence and do not call tools.
2. Never invent or calculate engineering numbers yourself. Every number you report must come \
from a tool result in this conversation.
3. Call get_requirements first, including for questions about inputs. If the request leaves \
out something the design depends on, name it. If the missing input is a design choice, such as \
the heating return temperature, compare options with the tools instead of asking the user. \
State every assumption you used. If the user gives a demand different from \
get_requirements, pass it to the tools as heating_peak_mw or cooling_peak_mw; never claim a \
demand you did not simulate.
4. A tool result with checks_failed or error is a violation. Do not accept it. Explain the \
cause from the result, change one input, and run again.
5. The design choices are the number of doublets (1-3) and the reservoir depth. Depth sets \
the brine temperature. Screen combinations with compare_designs, then refine the depth around \
the best one. Before recommending, run simulate_doublet at the chosen depth near the peak \
flow of 300 m3/h and fix any failed check. GEMINI solves its own flow, so if it exceeds \
300 m3/h lower design_flow_m3h; if brine cooling exceeds 40 C lower secondary_flow_m3h.
6. Selection rule, geothermal first: only designs with meets_geothermal_first true are \
eligible (bought gas heat plus electric cooling at most 10% of energy delivered). Among \
those, recommend the lowest levelised_cost_eur_per_mwh. Report the cheapest ineligible \
design too, with its cost and CO2, so the trade-off is visible.
7. Keep answers short: the design, the key numbers, failed checks fixed, assumptions.
8. When you recommend a design, end with exactly one line: \
RECOMMENDATION: doublets=<n>, depth_m=<m>
9. A message starting with REVIEWER comes from an automatic checker. Fix every point it raises."""


def chat(messages):
    """Send one request to Ollama and return the response and its duration."""
    body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_ctx": 16384},
        }
    ).encode()
    request = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.load(response), time.time() - start


def run(question):
    """Run the agent on one question, logging every step."""
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"session_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    tokens_in = tokens_out = 0
    reviews = 0
    year_runs, cost_runs, tool_results, doublet_runs = {}, {}, [], []

    def log(entry):
        with open(log_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")

    log({"event": "question", "model": MODEL, "text": question})
    print(f"QUESTION: {question}\n")
    for round_number in range(1, MAX_ROUNDS + 1):
        response, seconds = chat(messages)
        message = response["message"]
        used_in = response.get("prompt_eval_count", 0)
        used_out = response.get("eval_count", 0)
        tokens_in += used_in
        tokens_out += used_out
        log(
            {
                "event": "llm",
                "round": round_number,
                "seconds": round(seconds, 1),
                "tokens_in": used_in,
                "tokens_out": used_out,
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls"),
            }
        )
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            answer = message.get("content", "").strip()
            print(f"ANSWER:\n{answer}\n")
            asks_user = answer.rstrip().endswith("?") and not year_runs
            designing = bool(tool_results) or bool(RECOMMENDATION.search(answer))
            if asks_user or not designing:
                break
            problems = review(answer, question, year_runs, cost_runs, tool_results)
            chosen = RECOMMENDATION.search(answer)
            if chosen and not any(
                depth == float(chosen.group(2)) and not failed and flow >= PEAK_CHECK_FLOW_M3H
                for depth, flow, failed in doublet_runs
            ):
                problems.append(
                    f"No simulate_doublet run at {float(chosen.group(2)):.0f} m with a GEMINI flow of "
                    f"at least {PEAK_CHECK_FLOW_M3H:.0f} m3/h passed every check. The yearly model runs "
                    "doublets at up to 300 m3/h, so check the peak operating point in GEMINI."
                )
            missing_scenario = unsimulated_demand(question, year_runs)
            if missing_scenario:
                problems.append(
                    f"The question gives a demand of {missing_scenario} MW, but no simulation used it. "
                    "Pass it as heating_peak_mw or cooling_peak_mw, or say clearly that the design "
                    "uses the supplied profiles instead."
                )
            if chosen and chosen_numbers_missing(answer, cost_runs, chosen):
                problems.append(
                    "State the recommended design's levelised cost and CO2, and the cost and CO2 "
                    "of the cheapest ineligible design, using the tool numbers."
                )
            log({"event": "review", "number": reviews + 1, "problems": problems})
            if not problems:
                print("REVIEWER: accepted.\n")
                log({"event": "accepted"})
                break
            reviews += 1
            if reviews > MAX_REVIEWS:
                print("REVIEWER: NOT ACCEPTED. Remaining problems:\n- " + "\n- ".join(problems) + "\n")
                log({"event": "not_accepted", "problems": problems})
                break
            feedback = "REVIEWER: fix these problems, then answer again.\n- " + "\n- ".join(problems)
            print(f"{feedback}\n")
            messages.append({"role": "user", "content": feedback})
            continue
        for call in calls:
            name = call["function"]["name"]
            arguments = call["function"].get("arguments") or {}
            result = call_tool(name, arguments)
            tool_results.append({"arguments": arguments, "result": result})
            if name == "simulate_doublet" and "error" not in result:
                doublet_runs.append(
                    (float(arguments["depth_m"]), result["flow_m3h"], result["checks_failed"])
                )
            if name == "compare_designs" and "error" not in result:
                for row in result["designs"]:
                    if "error" not in row:
                        design = (row["doublets"], row["depth_m"])
                        scenario = {
                            key: arguments[key]
                            for key in ("return_c", "heating_peak_mw", "cooling_peak_mw")
                            if key in arguments
                        }
                        run_arguments = {"doublets": design[0], "depth_m": design[1], **scenario}
                        year_runs[design] = call_tool("simulate_year", run_arguments)
                        cost_runs[design] = call_tool("estimate_cost", run_arguments)
            if name in ("simulate_year", "estimate_cost") and "error" not in result:
                design = (int(arguments["doublets"]), float(arguments["depth_m"]))
                if name == "simulate_year":
                    year_runs[design] = result
                else:
                    cost_runs[design] = result
                    year_runs.setdefault(design, call_tool("simulate_year", arguments))
            print(f"TOOL {name}({json.dumps(arguments)})\n  -> {json.dumps(result)[:600]}\n")
            log({"event": "tool", "name": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result)})
    else:
        print("Stopped: reached the round limit.\n")
        log({"event": "stopped", "reason": "round limit"})

    summary = {"event": "tokens", "tokens_in": tokens_in, "tokens_out": tokens_out, "rounds": round_number}
    log(summary)
    print(f"TOKENS: {tokens_in} in, {tokens_out} out, {round_number} LLM calls. Log: {log_path.name}")


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]) or "Design the heating and cooling system for the district.")
