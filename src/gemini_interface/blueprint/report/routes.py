"""
Report Management Routes.

=========================

This module handles report generation and management functionality including document
upload/download, report listing, and MongoDB/GridFS integration.
"""

import os

import gridfs
from flask import Blueprint, current_app, jsonify, request, send_file
from pymongo import MongoClient

# Create the report blueprint
report = Blueprint("report", __name__)

# Allowed file extensions for report uploads
ALLOWED_EXTENSIONS = set(["pdf"])

# MongoDB client for report storage
dbclient = MongoClient(
    os.getenv("MONGODB_HOST"),
    int(os.getenv("MONGODB_PORT", 0)),
    username=os.getenv("MONGODB_USERNAME"),
    password=os.getenv("MONGODB_PASSWORD"),
)

mydb = dbclient["gemini_database"]
fs = gridfs.GridFS(mydb)


def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@report.route("/report/getreportlist", methods=["POST"])
def getreportlist():
    """Get list of reports for a specific project."""
    project_name = request.json["project_name"]

    mydbcol = mydb[project_name]
    report_names = []
    for x in mydbcol.find():
        report_names.append(x["name"])

    return jsonify(report_names)


@report.route("/report/upload_document", methods=["POST"])
def upload_document():
    """Upload document files to the project's report collection."""
    project_name = request.form["project_name"]
    document_search = request.form["document_search"]

    mydbcol = mydb[project_name]

    num_files = int(request.form["file_count"])

    if num_files == 0:
        return jsonify("ERROR : No file is selected! \n")
    return_text = ""
    for ii in range(0, num_files):
        file = request.files[f"file_{ii}"]
        if file and allowed_file(file.filename):
            file_name = file.filename

            if mydbcol.find_one({"name": file_name}):
                return_text += "ERROR : " + file_name + " exists \n"
                continue

            file_content = file.read()
            file_id = fs.put(file_content, filename=file_name)

            mydata = {"name": file_name, "file_id": file_id, "type": "report"}
            mydbcol.insert_one(mydata)

            if document_search:
                document_folder_path = os.path.join(
                    current_app.config["GEMINI_PROJECT_FOLDER"], project_name, "rag_data"
                )
                if not os.path.exists(document_folder_path):
                    os.mkdir(document_folder_path)

                full_file = os.path.join(document_folder_path, file_name)
                if not os.path.exists(full_file):
                    file.seek(0)
                    file.save(full_file)

            return_text += file_name + " is uploaded \n"
        else:
            return_text += "ERROR : Use pdf file extension! \n"
    return jsonify(return_text)


@report.route("/report/open_document", methods=["POST"])
def open_document():
    """Download and open a document from the project's report collection."""
    project_name = request.json["project_name"]
    file_name = request.json["file_name"]

    mydbcol = mydb[project_name]
    for mydata in mydbcol.find():
        if mydata["name"] == file_name:
            break
    file_content = fs.get(mydata["file_id"])

    return send_file(file_content, as_attachment=True, download_name=file_name)


@report.route("/report/delete_document", methods=["POST"])
def delete_document():
    """Delete a document from the project's report collection."""
    project_name = request.json["project_name"]
    file_name = request.json["file_name"]

    mydbcol = mydb[project_name]
    mydata = {"name": file_name}
    mydbcol.delete_one(mydata)

    document_folder_path = os.path.join(
        current_app.config["GEMINI_PROJECT_FOLDER"], project_name, "rag_data"
    )

    full_file = os.path.join(document_folder_path, file_name)
    if os.path.exists(full_file):
        os.remove(full_file)

    return jsonify(file_name + " is deleted")
