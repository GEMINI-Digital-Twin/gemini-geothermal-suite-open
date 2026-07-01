"""
Create Flask Application.

====================================

This module defines the factory function `create_app` for creating and configuring
the Gemini web application. It handles:
- Configuration of Flask application
- Database setup with SQLAlchemy
- Authentication management with Flask-Login
- Session management with Flask-Session
- Admin interface for managing users and projects
"""

import os
from pathlib import Path

from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

db = SQLAlchemy()

gemini_root_dir = Path(__file__).parents[2]

if not os.path.exists(os.path.join(gemini_root_dir, "gemini-project")):
    os.mkdir(os.path.join(gemini_root_dir, "gemini-project"))


def create_app():
    """Create and configure the Gemini web application using Flask and importing the blueprints."""
    app = Flask(__name__)

    app.config["SECRET_KEY"] = b"0\xbf\xb6\x04q\xf2\x12,\xfa\xfa\xf8T"
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mysql+pymysql://root:root@{os.getenv('GEMINI_MYSQLDB_URL')}:3306/"
        f"{os.getenv('MYSQL_DATABASE')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_TYPE"] = "filesystem"

    app.config["GEMINI_PROJECT_FOLDER"] = os.getenv(
        "GEMINI_PROJECT_FOLDER", os.path.join(gemini_root_dir, "gemini-project")
    )
    app.config["GEMINI_DOCUMENTATION_FOLDER"] = os.getenv(
        "GEMINI_DOCUMENTATION_FOLDER", os.path.join(gemini_root_dir, "src/gemini_documentation")
    )

    app.config["MAX_CONTENT_LENGTH"] = 500 * 1000 * 1000 * 2

    Session(app)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    from gemini_interface.blueprint.dbmodels import Project, User

    @login_manager.user_loader
    def load_user(user_id):
        """Load user from database by ID."""
        return User.query.get(int(user_id))

    # for admin manager
    app.config["FLASK_ADMIN_SWATCH"] = "slate"

    class UserModelView(ModelView):
        can_create = False
        column_exclude_list = ["password"]

        def is_accessible(self):
            return current_user.is_authenticated and current_user.role == "admin"

    class ProjectModelView(ModelView):
        def is_accessible(self):
            return current_user.is_authenticated and current_user.role == "admin"

    admin = Admin(app, name="Admin Manager", template_mode="bootstrap4")
    admin.add_view(UserModelView(User, db.session))
    admin.add_view(ProjectModelView(Project, db.session))

    # for migration database
    Migrate(app, db)

    # blueprint for auth routes in our app
    from gemini_interface.blueprint.auth.routes import auth as auth_blueprint

    app.register_blueprint(auth_blueprint)

    # blueprint for project routes in our app
    from gemini_interface.blueprint.project.routes import projectmanager as projectmanager_blueprint

    app.register_blueprint(projectmanager_blueprint)

    # blueprint for pages route
    from gemini_interface.blueprint.routes import main as main_blueprint

    app.register_blueprint(main_blueprint)

    # blueprint for builder routes in our app
    from gemini_interface.blueprint.app_builder.routes import app_builder as app_builder_blueprint

    app.register_blueprint(app_builder_blueprint)

    # blueprint for esp routes in our app
    from gemini_interface.blueprint.app_esp.routes import app_esp as app_esp_blueprint

    app.register_blueprint(app_esp_blueprint)

    # blueprint for report routes in our app
    from gemini_interface.blueprint.report.routes import report as report_blueprint

    app.register_blueprint(report_blueprint)

    # blueprint for setting plant routes in our app
    from gemini_interface.blueprint.setting_plant.routes import (
        setting_plant as setting_plant_blueprint,
    )

    app.register_blueprint(setting_plant_blueprint)

    # blueprint for app tagbrowser routes in our app
    from gemini_interface.blueprint.app_tagbrowser.routes import (
        app_tagbrowser as app_tagbrowser_blueprint,
    )

    app.register_blueprint(app_tagbrowser_blueprint)

    # blueprint for app productionwellperformance routes in our app
    from gemini_interface.blueprint.app_productionwellperformance.routes import (
        app_productionwellperformance as app_productionwellperformance_blueprint,
    )

    app.register_blueprint(app_productionwellperformance_blueprint)

    # blueprint for app injectionwellmonitoring routes in our app
    from gemini_interface.blueprint.app_injectionwellmonitoring.routes import (
        app_injectionwellmonitoring as app_injectionwellmonitoring_blueprint,
    )

    app.register_blueprint(app_injectionwellmonitoring_blueprint)

    # blueprint for app well_schematics routes in our app
    from gemini_interface.blueprint.app_well_schematics.routes import (
        app_well_schematics as app_well_schematics_blueprint,
    )

    app.register_blueprint(app_well_schematics_blueprint)

    # blueprint for app parameters_overview routes in our app
    from gemini_interface.blueprint.app_parameters_overview.routes import (
        app_parameters_overview as app_parameters_overview_blueprint,
    )

    app.register_blueprint(app_parameters_overview_blueprint)

    # blueprint for app reportgenerator routes in our app
    from gemini_interface.blueprint.app_reportgenerator.routes import (
        app_reportgenerator as app_reportgenerator_blueprint,
    )

    app.register_blueprint(app_reportgenerator_blueprint)

    # blueprint for app dashboard routes in our app
    from gemini_interface.blueprint.dashboard.routes import dashboard as dashboard_blueprint

    app.register_blueprint(dashboard_blueprint)

    # blueprint for app wellintegrity_monitoring routes in our app
    from gemini_interface.blueprint.app_wellintegrity_monitoring.routes import (
        app_wellintegrity_monitoring as app_wellintegrity_monitoring_blueprint,
    )

    app.register_blueprint(app_wellintegrity_monitoring_blueprint)

    # blueprint for app chatpopup in our app
    from gemini_interface.blueprint.app_chatpopup.routes import app_chatpopup as app_chatpopup

    app.register_blueprint(app_chatpopup)

    with app.app_context():
        db.create_all()
        user = User.query.filter_by(email="admin@localhost").first()
        if not user:
            new_user = User(
                email=os.getenv("GEMINI_ADMIN_EMAIL"),
                name=os.getenv("GEMINI_ADMIN_NAME"),
                password=generate_password_hash(
                    os.getenv("GEMINI_ADMIN_PASSWORD"), method="scrypt"
                ),
                role="admin",
            )
            db.session.add(new_user)
            db.session.commit()
        template_project = Project.query.filter_by(name="geothermal_example").first()
        if not template_project:
            new_project = Project(name="geothermal_example", user="admin")
            db.session.add(new_project)
            db.session.commit()

    return app
