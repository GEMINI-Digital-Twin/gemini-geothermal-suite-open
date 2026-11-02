"""Context-local numerical and display settings: ``gm.runtime.settings`` and ``gm.runtime.state``.

Settings live in a ``contextvars.ContextVar``: a change applies to the current context only.
New threads start from the defaults; code that hands work to threads passes ``state()`` along
or runs it in ``contextvars.copy_context()``.
"""

from contextvars import ContextVar

from gemini._utils.context import ContextSetting, ContextSettings
from gemini._utils.strings import did_you_mean, join_names
from gemini.errors import ValidationError
from gemini.ops.backend import settings as backend_setting

_DEFAULTS = {"precision": "float64", "display_units": "si", "processes": 1}
_CHOICES = {"precision": ("float64", "float32"), "display_units": ("si", "field")}

KEEP = object()
"""The ``backend`` of ``settings`` that leaves the selected backend as it is."""

_state = ContextVar("gemini_runtime_state", default=_DEFAULTS)

__all__ = ["settings", "state"]


def _check_names(names):
    """Reject unknown setting names."""
    for name in names:
        if name not in _DEFAULTS:
            raise ValidationError(
                f"runtime: setting {name!r} is unknown; expected one of "
                f"{join_names(_DEFAULTS)}{did_you_mean(name, _DEFAULTS)}",
                code="unknown_name",
            )


def _validated(values):
    """Return complete settings; reject values outside the choices."""
    for name, choices in _CHOICES.items():
        if values[name] not in choices:
            raise ValidationError(
                f"runtime: {name} = {values[name]!r}; expected one of {join_names(choices)}",
                code="unknown_name",
            )
    processes = values["processes"]
    if isinstance(processes, bool) or not isinstance(processes, int) or processes < 1:
        raise ValidationError(
            f"runtime: processes = {processes!r}; expected a whole number of at least 1",
            code="invalid_value",
        )
    return values


def state():
    """Return a copy of the current runtime settings."""
    return _state.get().copy()


def get_precision():
    """Return the configured numerical precision name."""
    return _state.get()["precision"]


def get_display_units():
    """Return the display-unit system."""
    return _state.get()["display_units"]


def get_processes():
    """Return the number of worker processes a study runs its independent trials in."""
    return _state.get()["processes"]


def settings(backend=KEEP, **changes):
    """Apply settings inside a ``with`` block or a decorated function, then restore them.

    The names are ``backend``, ``precision``, ``display_units`` and ``processes``.
    ``backend`` selects the kernels of the ops by name, and ``None`` restores the automatic choice
    from the values; ``processes`` is the number of worker processes the trials of a study run
    in, 1 for a serial run; the others are merged into the settings current at entry. Unknown
    names are rejected at once and values are validated.
    """
    _check_names(changes)
    setting = ContextSetting(_state, lambda current: _validated(current | changes))
    return setting if backend is KEEP else ContextSettings(backend_setting(backend), setting)
