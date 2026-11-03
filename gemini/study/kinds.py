"""The kinds of study in plain words, and the settings each one takes, for a form."""

from gemini.evaluate._utils.display import OBJECTIVES
from gemini.evaluate.summary import KPI_NAMES
from gemini.study._utils.trial import ECONOMICS
from gemini.study.study import METHODS, OWN, PREPARE, REQUIRED, SETTING_KEYS, Study

KINDS = {
    "run": (
        "Run the design",
        "Simulates the plant on the case over the whole period and reports what it delivers, "
        "what it costs, what it emits and whether the requirements are met. Nothing is "
        "changed or searched.",
    ),
    "minimize": (
        "Find the best design",
        "Searches the ranges and choices that the plant file leaves open for the design with "
        "the lowest value of one figure, such as the cost of heat. A design that fails a "
        "requirement always ranks after every design that meets them.",
    ),
    "evolve": (
        "Find the best structure",
        "Searches which optional equipment to include, which alternative to pick and the values "
        "the plant file leaves open, with a genetic algorithm. With several figures, such as the "
        "cost of heat and the emissions, it gives the designs where no figure can improve without "
        "another getting worse. A design that fails a requirement always ranks after every "
        "design that meets them.",
    ),
    "sample": (
        "Test the uncertainty",
        "Draws random values for the inputs that the case gives an uncertainty, runs the plant "
        "once for each draw and reports the average of each chosen figure and the range in "
        "which most draws fall.",
    ),
    "sensitivity": (
        "Rank what matters most",
        "Moves each uncertain input of the case to its low and to its high value, one at a "
        "time, and ranks the inputs by how much each one changes the chosen figures.",
    ),
    "size": (
        "Size the equipment",
        "Sets the capacity of the equipment from the demand of the case, so that a study starts "
        "from a sensible design. It runs before another study and is not a study by itself.",
    ),
}
"""The ``(title, description)`` of each kind: the methods of a study and the action before it."""

SETTINGS = {
    "objective": (
        "Figure to minimise",
        "The figure the search makes as small as possible.",
    ),
    "metrics": (
        "Figures to report",
        "The figures that are read from every run.",
    ),
    "evaluations": (
        "Number of designs to try",
        "How many designs the search runs at most; more designs search better and take longer.",
    ),
    "samples": (
        "Number of draws",
        "How many random draws are run; more draws give steadier figures and take longer.",
    ),
    "objectives": (
        "Figures to minimise",
        "One figure, or several that the search weighs against each other.",
    ),
    "population": (
        "Designs per generation",
        "How many designs each generation of the search holds; more search wider.",
    ),
    "polish": (
        "Designs to refine",
        "How many of the best designs are refined afterwards by a search of their values; 0 for "
        "none.",
    ),
    "seed": (
        "Random seed",
        "A whole number that fixes the random choices: the same seed gives the same study.",
    ),
}
"""The ``(title, description)`` of each setting that a method reads."""


def _setting(key):
    """Return the schema of one setting: its JSON Schema from ``Study``, with words for a form."""
    found = dict(Study.schema()["properties"][key])
    title, description = SETTINGS[key]
    found["title"], found["description"] = title, description
    if key == "objective":
        found["enum"] = list(OBJECTIVES)
    if key == "metrics":
        found["items"] = {**found["items"], "enum": [*KPI_NAMES, *ECONOMICS]}
    if key == "objectives":
        found["anyOf"] = [{"type": "string", "enum": list(OBJECTIVES)}, {**found["anyOf"][1]}]
        found["anyOf"][1]["items"] = {"type": "string", "enum": list(OBJECTIVES)}
    return found


def _settings(method):
    """Return the JSON Schema of the keys a method reads beyond ``cases`` and ``plants``."""
    keys = [
        key for key in SETTING_KEYS if key in REQUIRED.get(method, ()) or method in OWN.get(key, ())
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(REQUIRED.get(method, ())),
        "properties": {key: _setting(key) for key in keys},
    }


def kinds():
    """Return the kinds of study, each with a title, a description and its settings.

    Returns
    -------
    list of dict
        ``{kind, use, title, description, settings}`` in a fixed order: the methods of
        ``gm.Study`` (``run``, ``minimize``, ``sample``, ``sensitivity``, ``evolve``, ``use``
        ``"method"``, the value of the ``method`` key of ``study.json``) and ``size`` (``use``
        ``"prepare"``, an entry of its ``prepare`` list). ``title`` and ``description`` are plain
        words for a user. ``settings`` is the JSON Schema (draft 2020-12) of the keys the kind
        reads besides ``cases`` and ``plants``: ``objective``, ``evaluations`` and ``seed`` for
        ``minimize``, ``metrics``, ``samples`` and ``seed`` for ``sample``, ``metrics`` for
        ``sensitivity``, ``objectives``, ``evaluations``, ``population``, ``seed`` and ``polish``
        for ``evolve``,
        none for the others. ``required`` lists those the kind cannot do without; ``objective``
        lists the metrics worth minimising (``gm.evaluate.metrics()``) and ``metrics`` those that a
        study reads. Plain JSON, a new list on each call.
    """
    methods = [(method, "method") for method in METHODS]
    prepared = [(action, "prepare") for action in PREPARE]
    return [
        {
            "kind": kind,
            "use": use,
            "title": KINDS[kind][0],
            "description": KINDS[kind][1],
            "settings": _settings(kind),
        }
        for kind, use in methods + prepared
    ]
