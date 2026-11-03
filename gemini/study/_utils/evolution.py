"""What ``gm.study.evolve`` reports besides its designs: hypervolume, structures and a summary.

The hypervolume measures a front of objectives (minimised) as the area it dominates up to a
reference point, after each objective is scaled to [0, 1] between the best and the worst value of
the final front; the reference point is 1.1 on every axis, so the ends of the front count too.
"""

import numpy as np

REFERENCE = 1.1
"""The reference point of the hypervolume on each scaled axis: a little beyond the worst value."""


def non_dominated(points):
    """Return the indices of the rows of ``points`` (minimised) that no other row dominates."""
    points = np.asarray(points, dtype=float)
    kept = []
    for index, point in enumerate(points):
        others = np.delete(points, index, axis=0)
        beaten = np.any(np.all(others <= point, axis=1) & np.any(others < point, axis=1))
        if not beaten:
            kept.append(index)
    return kept


def scale(points, ideal, nadir):
    """Return ``points`` scaled to [0, 1] between ``ideal`` and ``nadir`` per objective.

    An objective whose ideal equals its nadir is scaled to 0.
    """
    points = np.asarray(points, dtype=float)
    span = np.where(nadir > ideal, nadir - ideal, 1.0)
    return np.where(nadir > ideal, (points - ideal) / span, 0.0)


def hypervolume(points):
    """Return the hypervolume of scaled ``points`` up to ``REFERENCE``; ``None`` above two axes.

    One objective gives the length from the best point to the reference, two the dominated area.
    Points beyond the reference add nothing.
    """
    points = np.asarray(points, dtype=float)
    if len(points) == 0:
        return 0.0
    if points.shape[1] == 1:
        return float(max(0.0, REFERENCE - points[:, 0].min()))
    if points.shape[1] != 2:
        return None
    inside = points[np.all(points < REFERENCE, axis=1)]
    if len(inside) == 0:
        return 0.0
    ordered = inside[np.argsort(inside[:, 0], kind="stable")]
    area, ceiling = 0.0, REFERENCE
    for first, second in ordered:
        if second < ceiling:
            area += (REFERENCE - first) * (ceiling - second)
            ceiling = second
    return float(area)


def bounds(points):
    """Return ``(ideal, nadir)`` of the non-dominated rows of ``points``."""
    points = np.asarray(points, dtype=float)
    front = points[non_dominated(points)]
    return front.min(axis=0), front.max(axis=0)


def label(structure):
    """Return a structure as one line of text: ``heat_pump=on, cooling=absorption``."""
    if not structure:
        return "(no structure choice)"
    shown = {True: "on", False: "off"}
    return ", ".join(f"{name}={shown.get(value, value)}" for name, value in structure.items())


def explained(result):
    """Return the plain text summary of the dict ``to_dict`` gives: what was searched and found."""
    budget = result["budget"]
    lines = [
        f"Objectives: {', '.join(result['objectives'])}.",
        f"Simulations: {budget['evaluations']} (genetic search {budget['search']}, polish "
        f"{budget['polish']}), {budget['generations']} generations, stopped: {budget['stopped']}.",
        f"Structures: {len(result['structures'])} valid, {len(result['rejected'])} refused before "
        f"any simulation; candidates refused: {budget['invalid']}.",
        "Front:" if result["front"] else "Front: no design.",
    ]
    for design in result["front"]:
        lines.append(f"  {label(design['structure'])}: {_metrics(design)}")
    lines.append(f"Best on {result['objectives'][0]}: {label(result['best']['structure'])}")
    lines.append("By structure (best design of each):")
    for item in result["structures"]:
        lines.append(f"  {label(item['structure'])}: {_structure_line(item)}")
    for item in result["rejected"]:
        lines.append(f"  refused {label(item['structure'])}: {item['reasons'][0]}")
    return "\n".join(lines)


def _metrics(design):
    """Return the metrics of a design as text, with why it fails when it does."""
    shown = ", ".join(
        f"{name} {value['value']:.4g} {value['unit']}" if value["value"] is not None else name
        for name, value in design["metrics"].items()
    )
    return shown + ("" if design["feasible"] else f" (infeasible: {reason_text(design['reason'])})")


def reason_text(reason):
    """Return the text of a reason: the message of a verdict reason, else the text itself."""
    if isinstance(reason, dict):
        return str(reason.get("message", reason))
    return str(reason)


def _structure_line(item):
    """Return the line of one structure in the summary."""
    if item["best"] is None:
        return "not simulated"
    found = f"{item['evaluations']} simulated, {item['feasible']} feasible; best "
    return found + _metrics(item["best"])
