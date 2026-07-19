"""
Gemini Interface Package.

========================

This package serves as the module for the Gemini web user interface.
It initializes and organizes the various core components of the application.

Features:
- Blueprint system for modular web application routing
- Application configuration and setup procedures
- Integration with backend services such as database, Celery, and authentication
- Import points for submodules handling dashboard views, project management, plant settings

Typical usage involves importing and using the create_app factory and registering
the necessary blueprints to assemble the Gemini application.

The package contains a blueprint system for modular web application routing
with various application-specific modules for ESP analysis, well monitoring,
and other geothermal system components.

Note:
All actual application logic, routes, and data models are defined in submodules
within the blueprint package.

See individual submodules for documentation on route definitions and API interfaces.
"""

__version__ = "0.3.2"
