"""Boot and run a Gemini Framework plant.

Reads project path and plant name from environment or arguments, boots the
plant and executes one processing step.
"""

import os
import sys

sys.path.append(os.path.join(os.getcwd(), "src"))
from pathlib import Path

from gemini_framework.framework.boot_plant import setup
from gemini_framework.framework.mainmodule import MainModule

gemini_root_dir = Path(__file__).parents[2]


class App:
    """Runner that boots a plant and executes one step."""

    def __init__(self, project_path, plant_name):
        """Initialize application with project path and plant name."""
        self.project_path = project_path
        self.plant_name = plant_name

    def boot(self):
        """Initialize plant and main module from configuration."""
        self.plant = setup(self.project_path, self.plant_name)

        self.mainmodule = MainModule(self.plant)

    def step(self):
        """Execute one processing step across all modules."""
        self.mainmodule.step()

    def quit(self):
        """Disconnect from databases and cleanup."""
        # disconnect database
        self.plant.database.disconnect()


if __name__ == "__main__":

    projectpath = os.getenv(
        "GEMINI_PROJECT_FOLDER", os.path.join(gemini_root_dir, "gemini-project")
    )
    plantname = os.getenv("GEMINI_PLANT", "")

    if not plantname == "":
        app = App(projectpath, plantname)
        app.boot()
        app.step()
        app.quit()
    else:
        print("plant name is not defined")
