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

from reviewer import RECOMMENDATION, chosen_design, review
from tools import DEFAULT_LAYOUT, TOOL_SCHEMAS, call_tool

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"
MAX_ROUNDS = 20
MAX_REVIEWS = 3
MAX_NUDGES = 2  # answers without a recommendation line that only announce the next step
PEAK_CHECK_FLOW_M3H = 250.0
CONTEXT_TOKENS = 24576


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


REQUESTED_LIMITS = [
    (re.compile(r"(\d+)\s*doublets?", re.I), 3.0, "1-3 doublets"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*m3/h", re.I), 300.0, "50-300 m3/h per doublet"),
]


def requested_limit_breaks(question):
    """Return (value, limit text) for each requested value above a challenge limit."""
    breaks = []
    for pattern, maximum, limit in REQUESTED_LIMITS:
        for text in pattern.findall(question):
            if float(text) > maximum:
                breaks.append((text, limit))
    return breaks


def mentions(answer, value):
    """Return True if the answer contains this number as a whole number, not inside another."""
    return re.search(rf"(?<![\d.]){re.escape(str(value))}(?![\d])", answer) is not None


def chosen_numbers_missing(answer, cost_runs, year_runs, chosen):
    """Return the chosen design's cost and CO2 if the answer leaves either out, else None."""
    design = chosen_design(chosen)
    cost, year = cost_runs.get(design), year_runs.get(design)
    if cost is None or year is None:
        return None
    expected = (cost["levelised_cost_eur_per_mwh"], year["co2_kt"])
    if all(mentions(answer, value) for value in expected):
        return None
    return expected


def for_model(name, result):
    """Return the tool result as the LLM sees it.

    compare_designs rows are kept in full for the reviewer, but the LLM gets one
    short line per design, which cuts the tokens this result costs on every call.
    """
    if name != "compare_designs" or "designs" not in result:
        return result
    lines = []
    for row in result["designs"]:
        label = f"{row['doublets']} x {row['depth_m']:.0f} m {row['layout']}"
        if "error" in row:
            lines.append(f"{label}: {row['error']}")
        elif "same_as" in row:
            lines.append(f"{label}: same as {row['same_as']}, heat pump never runs")
        else:
            status = "eligible" if row["meets_geothermal_first"] else "not eligible"
            failed = f", failed {','.join(row['checks_failed'])}" if row["checks_failed"] else ""
            lines.append(
                f"{label}: {row['levelised_cost_eur_per_mwh']} EUR/MWh, {row['co2_kt']} kt CO2, "
                f"{row['bought_energy_share_pct']}% bought, {status}{failed}"
            )
    return {**result, "designs": lines}


RETURN_IN_ANSWER = re.compile(r"Return temperature[^\n]*?(\d+(?:\.\d+)?)\s*°?\s*C", re.I)


def wrong_return_temperature(answer, best_return_c):
    """Return the return temperature the answer states if it differs from the tools' choice."""
    match = RETURN_IN_ANSWER.search(answer)
    if best_return_c is None or not match or abs(float(match.group(1)) - best_return_c) < 0.01:
        return None
    return float(match.group(1))


def cheapest_ineligible_missing(answer, comparisons):
    """Return the cheapest ineligible design's cost if the answer leaves it out, else None."""
    if not comparisons or not comparisons[-1].get("lowest_cost_ineligible"):
        return None
    cost = comparisons[-1]["lowest_cost_ineligible"]["levelised_cost_eur_per_mwh"]
    return None if mentions(answer, cost) else comparisons[-1]["trade_off"]


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
5. The design choices are the number of doublets (1-3), the reservoir depth and the layout. \
Depth sets the brine temperature. The layout sets how water reaches 100 C (gas boiler or heat \
pump, or a CHP that turns the produced gas into electricity and heat) and how cooling is made \
(absorption or electric chillers).
6. Selection rule, geothermal first: only designs with meets_geothermal_first true are \
eligible (energy bought to make heat or cooling at most 10% of energy delivered). Among \
those, recommend the lowest levelised_cost_eur_per_mwh. Report the cheapest ineligible \
design too, with its cost and CO2, so the trade-off is visible.
7. For a design request, call the tools in this order before your first answer:
   a. get_requirements.
   b. compare_designs with doublet_options [1, 2, 3] and depths_m [2000, 2500, 3000], leaving \
out layouts so all four are compared, then pick lowest_cost_eligible.
   c. simulate_doublet at the chosen depth with design_flow_m3h 300. While passed is false, \
run it again with the input given in next_step. Never report a failed run as passing.
   d. verify_design for the chosen design and layout, passing alternative_for_verify_design \
from compare_designs.
8. Answer only after step d. Write short sentences under these headings: Design (doublets, \
depth, layout, levelised cost, CO2), Why, Return temperature, Unplanned failure, \
Uncertainty (P10-P90 cost, how often the rule is met, how often it beats the alternative), \
GEMINI check, Assumptions. Under Why, copy the whole trade_off text from \
compare_designs. If the user asked for something outside \
the limits, start the answer by saying which limit it breaks. If the user asked about a \
specific option, start the answer by answering it with that option's numbers from the tools. Under GEMINI check, give each failed run, the input you \
changed, the final flow and brine cooling, and the GEMINI year days run and failing. End with exactly one line: \
RECOMMENDATION: doublets=<n>, depth_m=<m>, layout=<layout>
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
            "options": {"temperature": 0, "num_ctx": CONTEXT_TOKENS},
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
    reviews = nudges = 0
    year_runs, cost_runs, tool_results, doublet_runs = {}, {}, [], []
    return_runs, outage_runs, uncertainty_runs, year_checks = set(), set(), set(), set()
    comparisons = []
    best_returns = {}

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
            if tool_results and not RECOMMENDATION.search(answer) and nudges < MAX_NUDGES:
                nudges += 1
                nudge = "Continue the workflow: call the next tool now instead of describing it."
                print(f"NUDGE: {nudge}\n")
                log({"event": "nudge", "number": nudges})
                messages.append({"role": "user", "content": nudge})
                continue
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
            if chosen:
                passing = [
                    run for run in doublet_runs
                    if run[0] == float(chosen.group(2)) and not run[2] and run[1] >= PEAK_CHECK_FLOW_M3H
                ]
                if passing and f"{passing[-1][1]}" not in answer:
                    problems.append(
                        f"Under GEMINI check, give the final passing flow ({passing[-1][1]} m3/h) and "
                        "brine cooling, and the inputs you changed to get there."
                    )
                design = chosen_design(chosen)
                verified = all(
                    design in runs for runs in (return_runs, outage_runs, uncertainty_runs, year_checks)
                )
                if not verified:
                    problems.append(
                        f"Call verify_design for {design[0]} doublets at {design[1]:.0f} m with layout "
                        f"{design[2]} and report its return temperature, unplanned failure, uncertainty "
                        "and GEMINI year results."
                    )
            if chosen:
                best = best_returns.get(chosen_design(chosen))
                stated = wrong_return_temperature(answer, best)
                if stated is not None:
                    problems.append(
                        f"Under Return temperature you give {stated:.0f} C, but the tools recommend "
                        f"best_return_c = {best:.0f} C: the highest return with the lowest cost, which "
                        "keeps the most margin for the network. Use it."
                    )
            trade_off = chosen and cheapest_ineligible_missing(answer, comparisons)
            if trade_off:
                problems.append(f"Under Why, copy the whole trade_off sentence from compare_designs: {trade_off}")
            for value, limit in requested_limit_breaks(question):
                if not mentions(answer, value):
                    problems.append(
                        f"The user asked for {value}, which breaks the limit of {limit}. Say so at the "
                        "start of the answer and explain what you used instead."
                    )
            missing_scenario = unsimulated_demand(question, year_runs)
            if missing_scenario:
                problems.append(
                    f"The question gives a demand of {missing_scenario} MW, but no simulation used it. "
                    "Pass it as heating_peak_mw or cooling_peak_mw, or say clearly that the design "
                    "uses the supplied profiles instead."
                )
            expected = chosen and chosen_numbers_missing(answer, cost_runs, year_runs, chosen)
            if expected:
                problems.append(
                    f"For the recommended design and this demand, the tools give a levelised cost of "
                    f"{expected[0]} EUR/MWh and CO2 of {expected[1]} kt. Use these numbers, not numbers "
                    "from a run with a different demand."
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
                comparisons.append(result)
                for row in result["designs"]:
                    if "error" not in row:
                        design = (row["doublets"], row["depth_m"], row["layout"])
                        scenario = {
                            key: arguments[key]
                            for key in ("return_c", "heating_peak_mw", "cooling_peak_mw")
                            if key in arguments
                        }
                        run_arguments = {
                            "doublets": design[0], "depth_m": design[1], "layout": design[2], **scenario
                        }
                        year_runs[design] = call_tool("simulate_year", run_arguments)
                        cost_runs[design] = call_tool("estimate_cost", run_arguments)
            runs_by_tool = {
                "compare_return_temperatures": return_runs,
                "check_unplanned_outage": outage_runs,
                "assess_uncertainty": uncertainty_runs,
                "validate_year_in_gemini": year_checks,
            }
            if name in runs_by_tool and "error" not in result:
                design = (int(arguments["doublets"]), float(arguments["depth_m"]), result["layout"])
                runs_by_tool[name].add(design)
                if name == "compare_return_temperatures" and result.get("best_return_c") is not None:
                    best_returns[design] = result["best_return_c"]
            if name == "verify_design" and "error" not in result:
                design = (int(arguments["doublets"]), float(arguments["depth_m"]), result["layout"])
                screened = comparisons[-1]["designs"][0] if comparisons else {}
                screened_peak = year_runs.get(
                    (screened.get("doublets"), screened.get("depth_m"), screened.get("layout")), {}
                ).get("heating_peak_mw_used")
                if screened_peak is None or abs(screened_peak - result["heating_peak_mw_used"]) < 0.01:
                    best_returns[design] = result["return_temperature"].get("best_return_c")
                    for runs in runs_by_tool.values():
                        runs.add(design)
                else:
                    result = {
                        **result,
                        "warning": (
                            f"verify_design used a {result['heating_peak_mw_used']} MW heating peak, but "
                            f"compare_designs used {screened_peak} MW. Run verify_design again with "
                            f"heating_peak_mw={screened_peak}."
                        ),
                    }
            if name in ("simulate_year", "estimate_cost") and "error" not in result:
                design = (
                    int(arguments["doublets"]), float(arguments["depth_m"]), arguments.get("layout", DEFAULT_LAYOUT)
                )
                if name == "simulate_year":
                    year_runs[design] = result
                else:
                    cost_runs[design] = result
                    year_runs.setdefault(design, call_tool("simulate_year", arguments))
            print(f"TOOL {name}({json.dumps(arguments)})\n  -> {json.dumps(result)[:600]}\n")
            log({"event": "tool", "name": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(for_model(name, result))})
    else:
        print("Stopped: reached the round limit.\n")
        log({"event": "stopped", "reason": "round limit"})

    summary = {"event": "tokens", "tokens_in": tokens_in, "tokens_out": tokens_out, "rounds": round_number}
    log(summary)
    print(f"TOKENS: {tokens_in} in, {tokens_out} out, {round_number} LLM calls. Log: {log_path.name}")


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]) or "Design the heating and cooling system for the district.")
