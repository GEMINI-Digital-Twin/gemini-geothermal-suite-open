"""Per-asset preprocessor validating measured time series."""

import math
from collections import deque
from datetime import datetime, timedelta, timezone

from gemini_framework.abstract.unit_module_abstract import UnitModuleAbstract


class DataFiltering(UnitModuleAbstract):
    """Apply per-tag rules from the owning asset's preprocessor list.

    A null min/max disables that bound. With no_missing=true, absent or null
    samples are invalid and corrected; false skips those time slots entirely.
    Window counts preceding filtered samples for moving_average only; it is
    kept on last_value rules to make switching correction methods simple.
    """

    def __init__(self, unit):
        """Attach a filtering preprocessor to one asset."""
        super().__init__(unit)
        self.rules = {}
        self.enabled = False

    def link(self):
        """Link each configured measured tag to its filtered output."""
        filtering = self.unit.parameters["filtering"]
        if not isinstance(filtering, dict):
            raise ValueError(f"Filtering configuration for {self.unit.name} must be an object")
        if "tags" in filtering or "enabled" in filtering:
            if set(filtering) - {"enabled", "tags"}:
                raise ValueError(f"Unknown filtering option for {self.unit.name}")
            enabled = filtering.get("enabled", True)
            rules = filtering.get("tags", {})
        else:
            enabled = True
            rules = filtering
        if not isinstance(enabled, bool):
            raise ValueError(f"Filtering enabled for {self.unit.name} must be a boolean")
        if not isinstance(rules, dict):
            raise ValueError(f"Filtering tags for {self.unit.name} must be an object")
        self.enabled = enabled and bool(rules)
        self.rules = rules if self.enabled else {}
        if not self.enabled:
            return
        for tag, rule in self.rules.items():
            if tag not in self.unit.tags["measured"] or tag not in self.unit.tags["filtered"]:
                raise ValueError(
                    f"Filtering tag {tag!r} is not measured and filtered on {self.unit.name}"
                )
            self._validate_rule(self.unit.name, tag, rule)
            self.link_input(self.unit, "measured", tag)
            self.link_output(self.unit, "filtered", tag)

        parameters = self.unit.plant.parameters["database"]
        self.interval = parameters["measured"]["interval"]
        if self.interval <= 0 or parameters["filtered"]["interval"] != self.interval:
            raise ValueError("Filtering requires matching positive measured and filtered intervals")

    def update_model_parameter(self, timestamp):
        """Leave model parameters unchanged."""
        pass

    @staticmethod
    def _bounds(rule):
        """Return inclusive configured bounds, ignoring unset limits."""
        minimum = rule.get("min")
        maximum = rule.get("max")
        return (
            -math.inf if minimum is None else minimum,
            math.inf if maximum is None else maximum,
        )

    @staticmethod
    def _validate_rule(unit_name, tag, rule):
        """Reject rules that cannot produce predictable numeric results."""
        label = f"{unit_name}.{tag}"
        if not isinstance(rule, dict):
            raise ValueError(f"Filtering rule for {label} must be an object")
        if set(rule) - {"min", "max", "no_missing", "correction", "window", "replacement"}:
            raise ValueError(f"Unknown filtering option for {label}")
        for bound in ("min", "max", "replacement"):
            if (
                bound in rule
                and rule[bound] is not None
                and (
                    isinstance(rule[bound], bool)
                    or not isinstance(rule[bound], (int, float))
                    or not math.isfinite(rule[bound])
                )
            ):
                raise ValueError(f"Filtering {bound} for {label} must be a finite number")
        if not isinstance(rule.get("no_missing", True), bool):
            raise ValueError(f"Filtering no_missing for {label} must be a boolean")
        minimum, maximum = DataFiltering._bounds(rule)
        if minimum > maximum:
            raise ValueError(f"Filtering min exceeds max for {label}")
        method = rule.get("correction")
        if method not in {"last_value", "moving_average", "replacement"}:
            raise ValueError(f"Filtering correction for {label} must be specified")
        if method == "replacement" and "replacement" not in rule:
            raise ValueError(f"Filtering replacement for {label} must be specified")
        if method == "replacement" and rule["replacement"] is None:
            raise ValueError(f"Filtering replacement for {label} must be a finite number")
        if method == "replacement" and not (minimum <= rule["replacement"] <= maximum):
            raise ValueError(f"Filtering replacement for {label} is outside the valid range")
        if (method == "moving_average" or "window" in rule) and (
            isinstance(rule.get("window"), bool)
            or not isinstance(rule.get("window"), int)
            or rule["window"] < 1
        ):
            raise ValueError(f"Filtering window for {label} must be a positive integer")

    def step(self, loop):
        """Process new samples, recording validity even when no correction is available."""
        if not self.enabled:
            return
        database = self.unit.plant.database
        driver = database.internal_db_driver
        plant_name = self.unit.plant.name
        asset = self.unit.name
        end = datetime.fromisoformat(loop.end_time)
        for tag, rule in self.rules.items():
            measured = self.tags["input"]["measured"][tag]["internal_name"]
            filtered = self.tags["output"]["filtered"][tag]["internal_name"]
            status = f"{tag}.filter_valid"
            _, last_times = driver.get_last_data(plant_name, asset, status)
            if last_times:
                start = datetime.fromisoformat(last_times[0]) + timedelta(seconds=self.interval)
            else:
                start = datetime.fromisoformat(
                    database.get_internal_database_last_time_str(plant_name, asset, status)
                )
            if start > end:
                continue

            minimum, maximum = self._bounds(rule)
            window = rule["window"] if rule["correction"] == "moving_average" else 1
            history = deque(maxlen=window)
            if rule["correction"] != "replacement":
                history.extend(
                    value
                    for value in driver.get_recent_data(
                        plant_name, asset, filtered, start.isoformat(), window
                    )
                    if math.isfinite(value) and minimum <= value <= maximum
                )
            raw_values, raw_times = driver.read_data(
                plant_name, asset, measured, start.isoformat(), end.isoformat()
            )
            samples = {datetime.fromisoformat(t): value for value, t in zip(raw_values, raw_times)}

            filtered_times, filtered_values, status_times, status_values = [], [], [], []
            uncorrectable = 0
            current = start
            while current <= end:
                time = current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                value = samples.get(current)
                if value is None and not rule.get("no_missing", True):
                    current += timedelta(seconds=self.interval)
                    continue
                valid = (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    and minimum <= value <= maximum
                )
                status_times.append(time)
                status_values.append(int(valid))
                if valid:
                    corrected = float(value)
                elif rule["correction"] == "replacement":
                    corrected = float(rule["replacement"])
                elif not history:
                    corrected = None
                    uncorrectable += 1
                elif rule["correction"] == "last_value":
                    corrected = history[-1]
                else:
                    corrected = sum(history) / len(history)

                if corrected is not None:
                    filtered_times.append(time)
                    filtered_values.append(corrected)
                    history.append(corrected)
                current += timedelta(seconds=self.interval)

            if filtered_times:
                driver.write_data(plant_name, asset, filtered, filtered_times, filtered_values)
            if status_times:
                driver.write_data(plant_name, asset, status, status_times, status_values)
            if uncorrectable:
                self.logger.warning(
                    "No correction history for %d samples of %s.%s",
                    uncorrectable,
                    asset,
                    tag,
                )
