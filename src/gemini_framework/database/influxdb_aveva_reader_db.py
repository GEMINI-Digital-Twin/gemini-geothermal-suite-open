"""Reader to import data from AVEVA into the internal InfluxDB store."""

from gemini_framework.abstract.database_reader_abstract import DatabaseReaderAbstract
from gemini_framework.database.connector.avevadb_driver import AvevaDriver


class InfluxdbAvevaReaderDB(DatabaseReaderAbstract):
    """Synchronize AVEVA data into InfluxDB for a given category."""

    def __init__(self, category):
        """Initialize AVEVA database reader."""
        super().__init__()

        self.category = category
        self.external_db_driver = AvevaDriver()

    def set_external_db_parameters(self):
        """Set external AVEVA database parameters."""
        self.parameters["avevadb"]["interval"] = self.delta_t

        self.external_db_driver.update_parameters(self.parameters["avevadb"])
