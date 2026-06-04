"""
Authentication Routes.

=====================

This module handles user authentication, login, logout, password management, and user registration.
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from gemini_interface.blueprint.dbmodels import User
from gemini_interface.create_app import db

auth = Blueprint("auth", __name__)


@auth.route("/login")
def login():
    """Display the login page."""
    return render_template("login.html")


@auth.route("/login", methods=["POST"])
def login_post():
    """Process user login form submission."""
    email = request.form.get("email")
    password = request.form.get("password")

    if email == "":
        flash("Please fill in your email address.")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to
    # the hashed password in the database
    if not user or not check_password_hash(user.password, password):
        flash("Please check your login details and try again.")
        return redirect(
            url_for("auth.login")
        )  # if the user doesn't exist or password is wrong, reload the page

    # if the above check passes, then we know the user has the right credentials
    login_user(user)
    return redirect(url_for("main.index"))


@auth.route("/password")
@login_required
def password():
    """Display password change page."""
    return render_template("password.html")


@auth.route("/password", methods=["POST"])
def password_post():
    """Process password change form submission."""
    old_password = request.form.get("old_password")
    new_password = request.form.get("new_password")

    if not check_password_hash(current_user.password, old_password):
        flash("old password does not match.")
        return redirect(url_for("auth.password"))

    current_user.password = generate_password_hash(new_password, method="scrypt")
    db.session.commit()

    return redirect(url_for("main.index"))


@auth.route("/signup")
@login_required
def signup():
    """Display user registration page (admin only)."""
    if not current_user.role == "admin":
        return redirect(url_for("main.index"))

    return render_template("signup.html")


@auth.route("/signup", methods=["POST"])
@login_required
def signup_post():
    """Process user registration form submission."""
    # code to validate and add user to database goes here
    email = request.form.get("email")
    name = request.form.get("name")
    password = request.form.get("password")

    if email == "":
        flash("Please fill in your email address.")
        return redirect(url_for("auth.signup"))

    user = User.query.filter_by(
        email=email
    ).first()  # if this returns a user, then the email already exists in database

    if user:  # if a user is found, we want to redirect back to signup page so user can try again
        flash("Email address already exists.")
        return redirect(url_for("auth.signup"))

    if name == "":
        flash("Please fill in your name.")
        return redirect(url_for("auth.signup"))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = User(
        email=email,
        name=name,
        password=generate_password_hash(password, method="scrypt"),
        group="none",
    )

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    return redirect(url_for("main.index"))


@auth.route("/logout")
@login_required
def logout():
    """Log out the current user and clear session data."""
    logout_user()

    session["projectname"] = ""
    session["system_assets"] = []

    return redirect(url_for("auth.login"))
