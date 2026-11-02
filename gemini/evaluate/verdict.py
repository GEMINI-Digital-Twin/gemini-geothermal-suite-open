"""The one answer to whether a run is feasible, with the reasons when it is not."""

from gemini._utils.jsonable import to_plain
from gemini.evaluate._utils.operating import breaches
from gemini.evaluate._utils.tally import tally
from gemini.evaluate.bounds import bounds
from gemini.evaluate.energy_balance import energy_balance
from gemini.evaluate.mass_balance import mass_balance
from gemini.evaluate.plant_balance import plant_balance
from gemini.evaluate.requirements import requirements
from gemini.evaluate.totals import totals
from gemini.run._utils.apply import apply_case
from gemini.types.shapes import measure

SERVICES = {"heating": "heat_delivered", "cooling": "cold_delivered"}
"""The figure that shows a service of the case being delivered."""

NOT_CONVERGED = "loop_not_converged"
"""The code of a failed row that is a numerical failure: an iteration that did not converge."""


class Verdict(dict):
    """The verdict of a run: ``feasible`` and the ``reasons`` it is not, with ``to_dict``."""

    def to_dict(self):
        """Return ``{feasible, reasons}`` as plain JSON, every ``Quantity`` as ``{value, unit}``."""
        return to_plain(dict(self))


def verdict(plant, case, results):
    """Return whether a finished run is feasible, and why not.

    The one place that decides feasibility; ``report``, ``compare`` and the study use it. A run is
    feasible when it has no reason. A reason has a ``kind``:

    - ``requirement``: a requirement of the case, or a supply temperature of a service, that
      failed (``requirements``); no requirement could be checked; a service of the case that the
      run does not deliver.
    - ``failed_step``: rows of the run that failed or were skipped.
    - ``numerical``: a mass or energy residual above the tolerances of ``mass_balance``,
      ``energy_balance`` and ``plant_balance``, or a loop that did not converge.
    - ``bound``: a recorded output outside the limits its module declares (``bounds``), or an
      output past an operating limit of a module (``Module.operating_limits``) in the steps in
      which the module carried flow.

    The case is applied to the plant once; the plant of the user never changes.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    case : Case
        The case of the run.
    results : Results
        A finished run.

    Returns
    -------
    Verdict
        A dict ``{feasible, reasons}`` (``to_dict()`` gives plain JSON). A reason is ``{kind,
        name, message}`` and, when it has them, ``path`` (the module or the output), ``value``,
        ``limit`` (values) and ``worst_step`` (ISO 8601). A ``requirement`` reason of a check also
        has its ``role`` and ``quantity``.
    """
    sited = apply_case(plant, case)
    checks = requirements(sited, case, results)
    return judged(sited, case, results, checks, totals(sited, case, results))


def judged(plant, case, results, checks, edge):
    """Return the ``Verdict`` of a run whose ``checks`` and ``edge`` totals are already read.

    ``plant`` carries the case (``apply_case``); ``report`` calls this with what it read, so that
    no figure is computed twice.
    """
    rows = results.errors()
    found = [
        *_requirement_reasons(case, checks, edge),
        *_failed_rows(rows),
        *_balances(plant, case, results, rows),
        *_bounds(plant, case, results),
    ]
    return Verdict(feasible=not found, reasons=found)


def reason(kind, name, message, **parts):
    """Return one reason: ``kind``, ``name`` and ``message``, then the parts that are given."""
    return {"kind": kind, "name": name, "message": message} | {
        key: item for key, item in parts.items() if item is not None
    }


def _text(item):
    """Return a value as text for a message: its number and unit."""
    if item.value is None:
        return "no value"
    return f"{item.value:.6g} {item.unit}"


def _requirement_reasons(case, checks, edge):
    """Return the requirement reasons: failed checks, none checked, a service not delivered."""
    found = [_failed(item) for item in checks if item["passed"] is False]
    if checks and tally([item["passed"] for item in checks]) is None:
        found.append(reason("requirement", "requirements", "no requirement could be checked"))
    for service, key in SERVICES.items():
        if _asked(case, service) and edge[key].value is None:
            found.append(reason("requirement", key, f"the run gives no {key} for the {service}"))
    return found


def _asked(case, service):
    """Return whether the demand of the case asks for ``service``."""
    return case.demand is not None and getattr(case.demand, service) is not None


def _failed(item):
    """Return the reason of a requirement check that failed."""
    message = f"{item['name']}: {_text(item['value'])} against the limit {_text(item['limit'])}"
    return reason(
        "requirement",
        item["name"],
        message,
        path=item["unit_path"] or None,
        value=item["value"],
        limit=item["limit"],
        worst_step=item["worst_step"],
        role=item["role"],
        quantity=item["quantity"],
    )


def _failed_rows(rows):
    """Return the reason of the rows that failed or were skipped, apart from the loops."""
    count = sum(row["code"] != NOT_CONVERGED for row in rows)
    if not count:
        return []
    message = f"{count} steps failed"
    return [reason("failed_step", "failed_steps", message, value=measure(count, "-"))]


def _balances(plant, case, results, rows):
    """Return the numerical reasons: balances out of their tolerance, loops not converged."""
    loops = sum(row["code"] == NOT_CONVERGED for row in rows)
    found = []
    if loops:
        message = f"{loops} steps did not converge"
        found.append(reason("numerical", NOT_CONVERGED, message, value=measure(loops, "-")))
    checks = [
        mass_balance(plant, case, results),
        energy_balance(plant, case, results),
        *plant_balance(plant, case, results),
    ]
    for item in checks:
        if item["passed"] is False:
            message = f"{item['name']}: {_text(item['value'])} above {_text(item['limit'])}"
            found.append(
                reason("numerical", item["name"], message, value=item["value"], limit=item["limit"])
            )
    return found


def _bounds(plant, case, results):
    """Return the bound reasons: declared limits of the outputs and operating limits of modules."""
    found = []
    declared = bounds(plant, case, results)
    if declared["passed"] is False:
        count = int(declared["value"].value)
        message = f"{count} recorded values are outside the limits their module declares"
        found.append(reason("bound", "bounds", message, value=declared["value"]))
    for breach in breaches(plant, results.to_frame()):
        found.append(_breach(breach))
    return found


def _breach(breach):
    """Return the bound reason of an operating limit that a run breaches."""
    word = "below" if breach["sense"] == "min" else "above"
    step = breach["step"].isoformat()
    message = (
        f"{breach['path']}.{breach['output']}: {_text(breach['worst'])} {word} the limit "
        f"{_text(breach['limit'])} at {step}"
    )
    return reason(
        "bound",
        breach["output"],
        message,
        path=breach["path"],
        value=breach["worst"],
        limit=breach["limit"],
        worst_step=step,
    )
