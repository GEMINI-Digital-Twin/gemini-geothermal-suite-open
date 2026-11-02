"""Run a stateful module over rows as the compiled scan and as one ``Module.step`` per row."""

import numpy as np

import gemini as gm
from gemini.compiler.cache import GraphCache
from gemini.compiler.executor import GraphExecutor
from gemini.engine.rowwise import applied
from gemini.streams.flows import STREAM_FIELDS, Stream


def flat(result, prefix=""):
    """Return every number of a result tree by name: outputs, outlet fields and children's."""
    values = {f"{prefix}out.{name}": value for name, value in result.outputs.items()}
    for port in result.outlets:
        value = result.outlets[port]
        if isinstance(value, Stream):
            values |= {f"{prefix}{port}.{field}": getattr(value, field) for field in STREAM_FIELDS}
        elif not isinstance(value, list):
            values[f"{prefix}{port}"] = value
    for name, child in result.children.items():
        values |= flat(child, f"{prefix}{name}.")
    return values


def stepped(module, fluids, columns, inputs, state, steps):
    """Return one ``("ok", flat result)`` or ``("error", exception)`` per row, and the last state.

    ``columns`` maps each inlet to its ``m_dot``, ``T`` and ``p`` columns, ``inputs`` the controls
    and boundaries (a column or one value) and ``steps`` the seconds of each row. A row that
    raises leaves the state as it was, as the compiled scan does.
    """
    rows = []
    for row, dt in enumerate(steps):
        streams = {
            port: Stream._si(
                **{field: float(np.asarray(values[field])[row]) for field in STREAM_FIELDS},
                fluid=fluids[port],
            )
            for port, values in columns.items()
        }
        given = {name: _row(value, row) for name, value in inputs.items()}
        try:
            with applied(module, given):
                state, result = module.step(state, float(dt), streams)
        except Exception as error:
            rows.append(("error", error))
        else:
            rows.append(("ok", flat(result)))
    return rows, state


def scanned(module, fluids, columns, inputs, state, steps, backend="numpy", cache=None):
    """Return the ``GraphResult`` of the compiled scan of the same rows."""
    executor = GraphExecutor(cache or GraphCache())
    streams = {
        port: Stream._si(
            **{field: np.asarray(values[field], dtype=float) for field in STREAM_FIELDS},
            fluid=fluids[port],
        )
        for port, values in columns.items()
    }
    with gm.runtime.settings(backend=backend):
        prepared = executor.prepare(module, streams, inputs, True)
        return executor.run(
            prepared, len(steps), {"dt": np.asarray(steps, dtype=float), "states": state}
        )


def _row(value, row):
    return float(np.asarray(value)[row]) if np.ndim(value) else value


def same_rows(evaluation, rows, tolerance=1e-9):
    """Assert that the scan has the values of ``rows`` and the failures of the rows that raised."""
    for row, (kind, found) in enumerate(rows):
        assert bool(evaluation.failed[row]) == (kind == "error")
        if kind == "error":
            assert type(evaluation.error(row)) is type(found)
            assert str(evaluation.error(row)).split("\n")[0] == str(found).split("\n")[0]
            continue
        got = flat(evaluation.result.row(row))
        assert got.keys() == found.keys()
        for name, value in found.items():
            _close(got[name], value, f"row {row} {name}", tolerance)


def _close(got, expected, label, tolerance):
    if isinstance(expected, list):
        assert len(got) == len(expected), label
        for item, other in zip(got, expected):
            _close(item, other, label, tolerance)
        return
    got = np.nan if got is None else got
    expected = np.nan if expected is None else expected
    assert got == expected or abs(got - expected) <= tolerance * max(1.0, abs(expected)), label
