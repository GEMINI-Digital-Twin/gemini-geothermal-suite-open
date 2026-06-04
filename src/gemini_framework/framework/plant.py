"""Plant container that holds units, database, and project configuration."""


class Plant:
    """Includes units (assets), connects them, and manages database access."""

    def __init__(self):
        """Initialize plant."""
        self.project_path = None
        self.name = None
        self.parameters = dict()
        self.units = []
        self.database = None
        self.diagram = None

    def update_parameters(self, parameters):
        """Update plant parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

    def add_unit(self, unit):
        """Add asset instance to the plant."""
        self.units.append(unit)

    def remove_unit(self, unit_id):
        """Remove asset instance based on unit id.

        :param str unit_id: the unique identifier of an asset.
        """
        for ii in range(0, len(self.units)):
            if self.units[ii].id == unit_id:
                del self.units[ii]

    def get_unit(self, unit_id):
        """Get asset instance based on unit id.

        :param str unit_id: the unique identifier of an asset.
        """
        unit = None
        for ii in range(0, len(self.units)):
            if self.units[ii].id == unit_id:
                unit = self.units[ii]
                break
        return unit

    def connect_unit(self):
        """Connect all units."""
        for cell in self.diagram["cells"]:
            if cell["type"] == "devs.Link":
                source_unit = self.get_unit(cell["source"]["id"])
                target_unit = self.get_unit(cell["target"]["id"])
                if not (source_unit is None) and not (target_unit is None):
                    source_unit.to_units.append(target_unit)
                    target_unit.from_units.append(source_unit)

    def link_unit(self):
        """Link all unit modules."""
        for unit in self.units:
            unit.link()

    def add_database(self, database):
        """Add database to plant."""
        self.database = database
        self.database.update_parameters(self.parameters["database"])

    def connect_database(self):
        """Connect to database."""
        self.database.connect()

    def register_tags(self):
        """Register tags with database."""
        self.database.register_tags(self.units)

    def find_modules(self, category):
        """Find modules of specified category."""
        modules = []
        for unit in self.units:
            modules += unit.modules[category]

        return modules
