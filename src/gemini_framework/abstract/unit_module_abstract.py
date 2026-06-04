"""Abstract module interface for unit components.

Defines the contract for unit modules that link inputs/outputs to the
framework database and update model parameters over time windows.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


class UnitModuleAbstract(ABC):
    """Abstract base class for unit modules."""

    logger = logger
    unit = None
    loop = None
    tags = {
        "input": {"measured": {}, "filtered": {}, "calculated": {}},
        "output": {"measured": {}, "filtered": {}, "calculated": {}},
    }

    def __init__(self, unit):
        """Initialize unit module."""
        self.unit = unit

    def link(self):
        """Link module inputs and outputs."""
        self.logger.error(
            print("Module " + self.__class__.__name__ + " did not implement a link method")
        )

    def init(self, loop):
        """Initialize module with loop."""
        self.loop = loop

    def link_input(self, unit, category, tagname):
        """Link input tag to module."""
        reference = unit.tags[category][tagname]

        self.tags["input"][category][tagname] = {
            "external_name": reference,
            "internal_name": tagname + "." + category,
            "unit_name": unit.name,
        }

    def link_output(self, unit, category, tagname):
        """Link output tag to module."""
        reference = unit.tags[category][tagname]

        self.tags["output"][category][tagname] = {
            "external_name": reference,
            "internal_name": tagname + "." + category,
            "unit_name": unit.name,
        }

    def get_output_last_data_time(self, tagname):
        """Get last data time for output tag."""
        for category in list(self.tags["output"].keys()):
            if tagname in list(self.tags["output"][category].keys()):
                break

        time_str = self.unit.plant.database.get_internal_database_last_time_str(
            self.unit.plant.name,
            self.tags["output"][category][tagname]["unit_name"],
            self.tags["output"][category][tagname]["internal_name"],
        )

        return time_str

    def get_input_data(self, tagname):
        """Get input data for tag."""
        for category in list(self.tags["input"].keys()):
            if tagname in list(self.tags["input"][category].keys()):
                break

        result, time = self.unit.plant.database.read_internal_database(
            self.unit.plant.name,
            self.tags["input"][category][tagname]["unit_name"],
            self.tags["input"][category][tagname]["internal_name"],
            self.loop.start_time,
            self.loop.end_time,
            self.loop.timestep,
        )

        return time, result

    def write_output_data(self, tagname, time, result):
        """Write output data for tag."""
        for category in list(self.tags["output"].keys()):
            if tagname in list(self.tags["output"][category].keys()):
                break

        self.unit.plant.database.write_internal_database(
            self.unit.plant.name,
            self.tags["output"][category][tagname]["unit_name"],
            self.tags["output"][category][tagname]["internal_name"],
            time,
            result,
        )

    def get_parameter_index(self, unit, timestamps):
        """Get parameter index for given timestamp."""
        timestamps_unix = datetime.fromisoformat(timestamps).timestamp()

        timestamps_parameters_unix = []
        for timestamp_parameter in unit.parameters["timestamps"]:
            timestamps_parameters_unix.append(
                datetime.strptime(timestamp_parameter, "%Y-%m-%d %H:%M:%S").timestamp()
            )

        index = np.argwhere(np.array(timestamps_parameters_unix) <= timestamps_unix).max()

        return index

    @abstractmethod
    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        pass
