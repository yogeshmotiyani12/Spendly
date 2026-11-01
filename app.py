import os
import re
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for

from database.db import (
    authenticate_user,
    create_user,
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
# The fallback key is for local development only. Set SECRET_KEY in the
# environment for anything else, and enable SESSION_COOKIE_SECURE once the app
# is served over https.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@app.template_filter("rupees")
def rupees(amount):
    return f"₹{amount:,.2f}"


@app.template_filter("format_date")
def format_date(value, fmt="%d %b %Y"):
    return datetime.fromisoformat(value).strftime(fmt)


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
    if session.get("user_id"):
        return redirect(url_for("profile"))

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


def _validate_login(email, password):
    """Return an error message if either field is empty, or None."""
    if not email or not password:
        return "Please enter your email and password."
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template(
            "login.html", registered=request.args.get("registered") == "1"
        )

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = _validate_login(email, password)
    if error is None:
        user = authenticate_user(email, password)
        if user is not None:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("profile"))
        error = "Invalid email or password."

    return render_template("login.html", error=error, email=email)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:  # stale session: the account no longer exists
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=user,
        stats=get_summary_stats(user_id),
        transactions=get_recent_transactions(user_id),
        categories=get_category_breakdown(user_id),
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

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
