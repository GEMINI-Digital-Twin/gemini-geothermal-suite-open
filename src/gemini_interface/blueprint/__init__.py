"""
Gemini Blueprint Package.

========================

This package contains Flask blueprints for the Gemini application, organizing
the web interface into modular components for different functional areas.

The blueprint system provides:
- Main application routes and navigation
- Authentication and authorization
- Project management
- Application-specific modules (ESP, well monitoring, etc.)
- Background task processing
- Database models

Modules:
- routes: Main application routes
- dbmodels: Database models for users and projects
- celerytasks: Background task definitions
- auth: Authentication and authorization
- project: Project management
- dashboard: Dashboard and analytics
- setting_plant: Plant configuration
- app_*: Application-specific blueprints
"""
