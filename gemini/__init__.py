"""GEMINI: a general geothermal heating and cooling package."""

from gemini import (
    analysis,
    case,
    compiler,
    errors,
    evaluate,
    modules,
    ops,
    physics,
    plants,
    runtime,
    streams,
    study,
    units,
)
from gemini._utils.version import package_version
from gemini.case import Case
from gemini.case.dataset import Dataset
from gemini.engine.check import check
from gemini.engine.engine import Engine
from gemini.engine.results import Results
from gemini.engine.schedule.schedule import schedule
from gemini.engine.simulate import live, replay, resume, simulate
from gemini.modules import Inlet, Module, Outlet, Output, Parameter
from gemini.modules.call import evaluate as call
from gemini.plants import Plant
from gemini.streams import BRINE, WATER, Fluid, Stream
from gemini.study import Study

__version__ = package_version()
__all__ = [
    "Module",
    "Plant",
    "Parameter",
    "Inlet",
    "Outlet",
    "Output",
    "Stream",
    "Fluid",
    "BRINE",
    "WATER",
    "Case",
    "Study",
    "check",
    "schedule",
    "simulate",
    "replay",
    "live",
    "resume",
    "call",
    "Results",
    "Dataset",
    "Engine",
    "modules",
    "plants",
    "case",
    "physics",
    "ops",
    "runtime",
    "units",
    "streams",
    "errors",
    "study",
    "evaluate",
    "analysis",
    "compiler",
]


def __dir__():
    """Expose only the documented API in interactive completion."""
    return sorted(__all__)
