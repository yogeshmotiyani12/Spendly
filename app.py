import os
import re
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for

from database.db import authenticate_user, create_user, init_db, seed_db

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


# Hardcoded placeholder data for the profile page until Step 5 reads it from the
# database. The card shows this user whoever is signed in. Rows have the shape
# of an `expenses` row and mirror the demo seed data.
_DEMO_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "member_since": "2026-01-15",
}

_DEMO_TRANSACTIONS = [  # newest first
    {"date": "2026-10-08", "description": None, "category": "Food", "amount": 27.40},
    {"date": "2026-10-07", "description": None, "category": "Other", "amount": 9.00},
    {"date": "2026-10-06", "description": "New shirt", "category": "Shopping", "amount": 64.75},
    {"date": "2026-10-05", "description": "Movie ticket", "category": "Entertainment", "amount": 18.99},
    {"date": "2026-10-04", "description": "Pharmacy", "category": "Health", "amount": 30.00},
    {"date": "2026-10-03", "description": "Electricity bill", "category": "Bills", "amount": 120.00},
    {"date": "2026-10-02", "description": "Monthly bus pass top-up", "category": "Transport", "amount": 45.00},
    {"date": "2026-10-01", "description": "Lunch at cafe", "category": "Food", "amount": 12.50},
]


def _demo_profile_context():
    """Build the profile template context from the hardcoded rows.

    Stats and the breakdown are derived so they cannot drift from the table.
    """
    total = round(sum(t["amount"] for t in _DEMO_TRANSACTIONS), 2)

    totals_by_category = {}
    for t in _DEMO_TRANSACTIONS:
        totals_by_category[t["category"]] = (
            totals_by_category.get(t["category"], 0) + t["amount"]
        )

    categories = [
        {"name": name, "total": round(amount, 2), "percent": round(amount / total * 100, 1)}
        for name, amount in sorted(
            totals_by_category.items(), key=lambda item: item[1], reverse=True
        )
    ]

    return {
        "user": _DEMO_USER,
        "stats": {
            "total": total,
            "count": len(_DEMO_TRANSACTIONS),
            "top_category": categories[0]["name"],
        },
        "transactions": _DEMO_TRANSACTIONS,
        "categories": categories,
    }


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("profile.html", **_demo_profile_context())


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
