"""
Gemini App Entry Point.

======================

This script serves as the entry point for running the Gemini web user interface
as a standalone Flask application.

It loads the Flask app via the factory `create_app` and launches the server.

- The port can be set by the environment variable GEMINI_FRONTEND_PORT (default: 5100).
- The host is set to 0.0.0.0 to allow external connections.
- Debug mode is disabled for production usage.

The `create_app` factory handles all necessary configuration, blueprint
registration, and initialization required for Gemini's UI server.
"""

import os
import sys

sys.path.append(os.path.join(os.getcwd(), "src"))
from gemini_interface.create_app import create_app

if __name__ == "__main__":
    app = create_app()

    app.run(host="0.0.0.0", port=int(os.getenv("GEMINI_FRONTEND_PORT")), debug=False)
