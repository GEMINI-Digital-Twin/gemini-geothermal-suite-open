"""
Project Management Routes.

=========================

This module handles project lifecycle management including creation, deletion,
import/export, and Git repository integration.
"""

import os
import shutil
import tempfile

from flask import Blueprint, current_app, jsonify, request, send_file, session
from flask_login import current_user
from git import Repo

from gemini_interface.blueprint.dbmodels import Project
from gemini_interface.create_app import db

projectmanager = Blueprint("projectmanager", __name__)


@projectmanager.route("/closeproject", methods=["POST"])
def closeproject():
    """Close the current project session."""
    project_name = request.json["project_name"]

    session["project_name"] = ""

    return project_name + " is closed."


@projectmanager.route("/loadproject", methods=["POST"])
def loadproject():
    """Load a project into the current session."""
    project_name = request.json["project_name"]

    session["project_name"] = project_name

    return project_name + " is loaded."


@projectmanager.route("/createproject", methods=["POST"])
def createproject():
    """Create a new project with template initialization."""
    project_name = request.json["project_name"]

    if project_name == "":
        return "ERROR: Please fill in your project name."

    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    if os.path.isdir(project_folder_path):
        return project_name + " already exists."
    else:
        os.mkdir(project_folder_path)

    template_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], "_template")
    shutil.copy(
        os.path.join(template_folder_path, "template_plant.conf"),
        os.path.join(project_folder_path, "plant.conf"),
    )

    session["project_name"] = project_name

    new_project = Project(name=project_name, user=current_user.name)

    db.session.add(new_project)
    db.session.commit()

    repo = Repo.init(project_folder_path)
    repo.config_writer().set_value("user", "name", current_user.name).release()

    repo.index.add(os.path.join(project_folder_path, "plant.conf"))
    repo.index.commit("First commit project creation")

    return project_name + " is created."


@projectmanager.route("/getprojectlist", methods=["GET"])
def getprojectlist():
    """Get list of projects accessible to the current user."""
    project_names = []

    if current_user.role == "admin":
        projects = Project.query.all()
        for project in projects:
            project_names.append(project.name)
    else:
        projects = Project.query.filter_by(user=current_user.name).all()
        for project in projects:
            if project.name not in project_names:
                project_names.append(project.name)

        projects = Project.query.filter_by(group=current_user.group).all()
        for project in projects:
            if project.name not in project_names:
                project_names.append(project.name)

    return jsonify(project_names)


@projectmanager.route("/deleteproject", methods=["POST"])
def deleteproject():
    """Delete a project and its associated files."""
    projectname = request.json["project_name"]

    project = Project.query.filter_by(name=projectname).first()

    # delete the project
    if project:
        db.session.delete(project)
        db.session.commit()

        session["project_name"] = ""

        project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], projectname)

        if os.path.isdir(project_folder_path):
            shutil.rmtree(project_folder_path)

    else:
        session["project_name"] = ""
        return projectname + " does not exist."

    return projectname + " is deleted."


@projectmanager.route("/exportproject", methods=["POST"])
def exportproject():
    """Export a project as a ZIP archive."""
    project_name = request.json["project_name"]

    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    archived = shutil.make_archive(project_name, "zip", project_folder_path)

    file_name = project_name + ".zip"

    return send_file(archived, as_attachment=True, download_name=file_name)


@projectmanager.route("/importproject", methods=["POST"])
def importproject():
    """Import a project from a ZIP archive."""
    file = request.files["file"]
    project_name = file.filename[:-4]
    project_folder_path = os.path.join(current_app.config["GEMINI_PROJECT_FOLDER"], project_name)

    print(project_folder_path)
    if os.path.isdir(project_folder_path):
        return project_name + " already exists."

    temp_dir = tempfile.mkdtemp()
    file.save(os.path.join(temp_dir, file.filename))
    shutil.unpack_archive(os.path.join(temp_dir, file.filename), project_folder_path, "zip")
    shutil.rmtree(temp_dir)

    session["project_name"] = project_name

    new_project = Project(name=project_name, user=current_user.name)

    db.session.add(new_project)
    db.session.commit()

    return jsonify(project_name + " is uploaded")
