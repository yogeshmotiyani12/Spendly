import re

from flask import Flask, redirect, render_template, request, url_for

from database.db import create_user, init_db, seed_db

app = Flask(__name__)

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


def _validate_registration(name, email, password):
    """Return the first validation error message, or None if the input is valid."""
    if not name:
        return "Please enter your name."
    if not _EMAIL_RE.fullmatch(email):
        return "Please enter a valid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    return None


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = _validate_registration(name, email, password)
    if error is None:
        if create_user(name, email, password) is not None:
            return redirect(url_for("login", registered=1))
        error = "An account with that email already exists."

    return render_template("register.html", error=error, name=name, email=email)


@app.route("/login")
def login():
    return render_template(
        "login.html", registered=request.args.get("registered") == "1"
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
