"""The demand of a case: what the consumers take and the conditions at which they take it."""

from functools import cached_property

import pandas as pd

from gemini.case._utils.node import Field, Node
from gemini.case.site import FRACTION, POSITIVE
from gemini.errors.base import Issue

NAMES = {"heating": "heating_demand", "cooling": "cooling_demand"}
"""The services, each with the column of the demand frame it fills."""


class Service(Node):
    """A heating service: the ``power`` demanded [W] and the conditions of the consumer.

    ``power`` is a series (or a constant) on the steps of ``time``. ``supply_temperature`` is what
    the consumer asks to be supplied at, ``return_temperature`` what it returns at, the
    ``minimum_return_temperature`` and ``maximum_return_temperature`` its limits [K], and
    ``return_pressure`` the pressure it returns at [Pa].
    """

    where = "demand.heating"
    description = "The heating service: the power demanded and the conditions of the consumer."
    old = {
        "column": '"power": {"file": "data/demand.csv", "column": "...", "unit": "MW"}',
        "unit": '"power": {"file": "data/demand.csv", "column": "...", "unit": "MW"}',
    }
    fields = {
        "power": Field(
            "power",
            series=True,
            bounds=POSITIVE,
            required=True,
            description=(
                "The power the consumers demand, a constant or a series on the steps of time."
            ),
        ),
        "supply_temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description="The temperature the consumer asks the water to be supplied at.",
        ),
        "return_temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description="The temperature the water returns from the consumer at.",
        ),
        "minimum_return_temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description="The lowest temperature the consumer can return the water at (cool it to).",
        ),
        "maximum_return_temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description=(
                "The highest temperature the consumer can return the water at (warm it to)."
            ),
        ),
        "return_pressure": Field(
            "pressure",
            bounds=POSITIVE,
            description="The pressure of the water leaving the consumer.",
        ),
    }


class CoolingService(Service):
    """A cooling service: a ``Service`` with the state of the building.

    ``indoor_temperature`` [K], ``indoor_relative_humidity`` [-] and the ``dew_point_margin`` [K]
    the chilled water must keep above the dew point of the room.
    """

    where = "demand.cooling"
    description = (
        "The cooling service: the power demanded, the conditions of the consumer and the state of "
        "the building."
    )
    fields = {
        **Service.fields,
        "indoor_temperature": Field(
            "temperature",
            bounds=POSITIVE,
            description="The indoor air temperature of the building.",
        ),
        "indoor_relative_humidity": Field(
            bounds=FRACTION, description="The relative humidity of the indoor air, between 0 and 1."
        ),
        "dew_point_margin": Field(
            "temperature_difference",
            bounds=POSITIVE,
            description=(
                "The margin the chilled water keeps above the dew point of the room; below it a "
                "latent load is taken."
            ),
        ),
    }


class Demand(Node):
    """The heating and the cooling service; at least one.

    Attributes
    ----------
    frame : DataFrame
        The demand in W on the UTC ``time`` index of the case, the columns ``heating_demand`` and
        ``cooling_demand`` for the services given, with ``attrs["units"]`` and
        ``attrs["quantities"]``.
    """

    where = "demand"
    description = "What the consumers take: the heating and the cooling service, at least one."
    old = {
        "file": 'a "power" series in "heating" and "cooling"',
        "time_column": 'a first column named "time" in the CSV file',
    }
    sections = {"heating": Service, "cooling": CoolingService}

    @classmethod
    def read(cls, data, path, ctx, header=()):
        """Return the demand with the index of the case, or ``None`` with issues."""
        found = super().read(data, path, ctx, header)
        if found is not None:
            found._set(_index=ctx.index)
        return found

    def _verify(self, path, ctx):
        """Refuse a demand without a service."""
        if self.heating is None and self.cooling is None:
            ctx.issues.append(
                Issue(path, "missing", f"{path}: heating and cooling are absent; expected one")
            )

    @cached_property
    def frame(self):
        """The demand in W on the steps of ``time``, as a DataFrame."""
        columns = {}
        for name, column in NAMES.items():
            service = getattr(self, name)
            if service is not None:
                columns[column] = service.power
        frame = pd.DataFrame(columns, index=self._index)
        frame.attrs = {
            "units": dict.fromkeys(frame, "W"),
            "quantities": dict.fromkeys(frame, "power"),
        }
        return frame
