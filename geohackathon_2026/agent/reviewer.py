"""Automatic reviewer that checks the agent's final answer before it is accepted.

It checks that the answer's numbers come from tool results, that the
recommended design was simulated, passed every check, was costed and meets the
geothermal-first rule, that depths on both sides of it were costed, and that no
cheaper design meeting the rule was overlooked.
"""

import re

RECOMMENDATION = re.compile(r"RECOMMENDATION:\s*doublets\s*=\s*(\d+)\s*,?\s*depth_m\s*=\s*([\d.]+)", re.I)
NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")
RELATIVE_TOLERANCE = 0.01
CHEAPER_MARGIN = 0.03
MIN_DEPTH_M = 1500.0
MAX_DEPTH_M = 4000.0


def numbers_in(value):
    """Return every number found in a nested tool result."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [number for item in value.values() for number in numbers_in(item)]
    if isinstance(value, list):
        return [number for item in value for number in numbers_in(item)]
    if isinstance(value, str):
        return [float(match.replace(",", "")) for match in NUMBER.findall(value)]
    return []


def ungrounded_numbers(answer, tool_results, question):
    """Return numbers in the answer that no tool result or the question contains."""
    known = numbers_in(tool_results) + numbers_in(question)
    missing = []
    for text in NUMBER.findall(answer):
        value = float(text.replace(",", ""))
        if abs(value) <= 3 or 2000 <= value <= 2100 and float(value).is_integer():
            continue  # counts and years
        if not any(abs(value - other) <= RELATIVE_TOLERANCE * max(abs(other), 1.0) for other in known):
            missing.append(text)
    return missing


def review(answer, question, year_runs, cost_runs, tool_results):
    """Return a list of problems with the final answer; empty means accepted.

    ``year_runs`` and ``cost_runs`` map (doublets, depth_m) to tool results.
    """
    problems = []
    match = RECOMMENDATION.search(answer)
    if not match:
        return [
            "End the answer with a line 'RECOMMENDATION: doublets=<n>, depth_m=<m>' "
            "for the design you recommend."
        ]
    chosen = (int(match.group(1)), float(match.group(2)))

    year = year_runs.get(chosen)
    if year is None:
        problems.append(f"The recommended design {chosen} was never simulated with simulate_year.")
    elif year.get("checks_failed"):
        problems.append(f"The recommended design {chosen} failed checks: {year['checks_failed']}.")
    if chosen not in cost_runs:
        problems.append(f"The recommended design {chosen} has no estimate_cost result.")
    elif not cost_runs[chosen].get("meets_geothermal_first"):
        problems.append(
            f"The recommended design {chosen} buys "
            f"{cost_runs[chosen].get('bought_energy_share_pct')}% of its energy, so it fails the "
            "geothermal-first rule. Recommend a design with meets_geothermal_first true."
        )

    depths = {depth for _, depth in year_runs}
    counts = {count for count, _ in year_runs}
    if len(depths) < 2:
        problems.append("Only one depth was simulated. Depth sets the brine temperature; compare at least two.")
    if len(counts) < 2:
        problems.append("Only one doublet count was simulated. Compare at least two.")
    costed_depths = sorted({depth for count, depth in cost_runs if count == chosen[0]})
    if chosen in cost_runs and len(costed_depths) >= 1:
        if chosen[1] == costed_depths[-1] and chosen[1] < MAX_DEPTH_M:
            problems.append(
                f"{chosen[1]:.0f} m is the deepest depth costed for {chosen[0]} doublets. "
                "Cost a deeper option too, to show this depth is the best."
            )
        if chosen[1] == costed_depths[0] and chosen[1] > MIN_DEPTH_M:
            problems.append(
                f"{chosen[1]:.0f} m is the shallowest depth costed for {chosen[0]} doublets. "
                "Cost a shallower option too, to show this depth is the best."
            )

    passing = {
        design: cost
        for design, cost in cost_runs.items()
        if not year_runs.get(design, {}).get("checks_failed", ["not simulated"])
        and cost.get("meets_geothermal_first")
    }
    if chosen in passing:
        own = passing[chosen]["levelised_cost_eur_per_mwh"]
        for design, cost in passing.items():
            other = cost["levelised_cost_eur_per_mwh"]
            if design != chosen and other < own * (1 - CHEAPER_MARGIN) and str(design[1]) not in answer:
                problems.append(
                    f"Design {design} costs {other} EUR/MWh, below the recommended {own} EUR/MWh, "
                    "and the answer does not explain why it was rejected."
                )

    simulated_inputs = [list(design) for design in year_runs]
    ungrounded = ungrounded_numbers(answer, [tool_results, simulated_inputs], question)
    if ungrounded:
        problems.append(
            f"These numbers do not appear in any tool result: {', '.join(ungrounded[:8])}. "
            "Use only numbers from tool results."
        )
    return problems
