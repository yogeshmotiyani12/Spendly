import re
from pathlib import Path

import pytest
from flask import url_for
from werkzeug.security import check_password_hash

import database.db as db
from database.db import get_db

ROOT = Path(__file__).resolve().parent.parent

VALID = {
    "name": "Alice Example",
    "email": "alice@example.com",
    "password": "correct-horse",
}

DUPLICATE_MESSAGE = "An account with that email already exists."


def _post(client, **overrides):
    return client.post(url_for("register"), data={**VALID, **overrides})


def _get_user(email):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()


def _count_users():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# GET /register                                                       #
# ------------------------------------------------------------------ #

def test_get_register_renders_form(client):
    response = client.get(url_for("register"))
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<form" in html
    for field in ("name", "email", "password"):
        assert f'name="{field}"' in html


# ------------------------------------------------------------------ #
# Successful registration                                             #
# ------------------------------------------------------------------ #

def test_valid_registration_redirects(client):
    response = _post(client, email="a.b+c@d.e.fr")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login?registered=1")


def test_login_shows_notice_after_registration(client):
    response = _post(client)
    assert response.status_code == 302

    response = client.get(response.headers["Location"])
    assert response.status_code == 200
    assert "Account created. Please sign in." in response.get_data(as_text=True)


def test_login_notice_only_with_param(client):
    notice = "Account created. Please sign in."

    assert notice not in client.get(url_for("login")).get_data(as_text=True)
    assert notice not in client.get("/login?registered=0").get_data(as_text=True)
    assert notice in client.get("/login?registered=1").get_data(as_text=True)


def test_user_row_stored(client):
    password = "correct-horse"
    response = _post(client, name="  Alice  ", email="Alice@Example.COM")
    assert response.status_code == 302

    user = _get_user("alice@example.com")
    assert user is not None
    assert user["name"] == "Alice"
    assert _get_user("Alice@Example.COM") is None
    assert user["password_hash"] != password
    assert user["password_hash"].startswith("pbkdf2:sha256")
    assert check_password_hash(user["password_hash"], password)


# ------------------------------------------------------------------ #
# Duplicate emails                                                    #
# ------------------------------------------------------------------ #

def test_duplicate_email_rejected(client):
    assert _post(client).status_code == 302
    assert _count_users() == 2  # demo user + Alice

    response = _post(client, email="ALICE@EXAMPLE.COM")

    assert response.status_code == 200
    assert DUPLICATE_MESSAGE in response.get_data(as_text=True)
    assert _count_users() == 2


@pytest.mark.parametrize("email", ["demo@spendly.com", "DEMO@spendly.com"])
def test_demo_email_rejected(client, email):
    response = _post(client, email=email)

    assert response.status_code == 200
    assert DUPLICATE_MESSAGE in response.get_data(as_text=True)
    assert _count_users() == 1


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("name", ["", "   "])
def test_name_required(client, name):
    response = _post(client, name=name)

    assert response.status_code == 200
    assert "Please enter your name." in response.get_data(as_text=True)
    assert _count_users() == 1


def test_missing_fields_do_not_400(client):
    response = client.post(url_for("register"), data={})

    assert response.status_code == 200
    assert "Please enter your name." in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "email", ["foo", "foo@bar", "a b@c.com", "@c.com", "a@b@c.com", ""]
)
def test_invalid_email(client, email):
    response = _post(client, email=email)

    assert response.status_code == 200
    assert "Please enter a valid email address." in response.get_data(as_text=True)
    assert _count_users() == 1


def test_short_password(client):
    response = _post(client, password="1234567")

    assert response.status_code == 200
    assert "Password must be at least 8 characters." in response.get_data(
        as_text=True
    )
    assert _count_users() == 1


def test_password_boundary_ok(client):
    assert _post(client, password="12345678").status_code == 302


def test_validation_order(client):
    # Name, email and password are all bad: the name error wins.
    html = _post(client, name="", email="bad", password="x").get_data(as_text=True)
    assert "Please enter your name." in html

    # Name is fine: the email error wins over the password error.
    html = _post(client, name="Al", email="bad", password="x").get_data(as_text=True)
    assert "Please enter a valid email address." in html
    assert "Password must be at least 8 characters." not in html


# ------------------------------------------------------------------ #
# Form re-population                                                  #
# ------------------------------------------------------------------ #

def test_failed_submit_repopulates(client):
    response = _post(
        client, name="Bob", email="bob@example.com", password="zx9-pw"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="Bob"' in html
    assert 'value="bob@example.com"' in html
    assert "zx9-pw" not in html

    password_input = re.search(r'<input[^>]*name="password"[^>]*>', html).group(0)
    assert "value=" not in password_input


def test_repopulated_values_are_escaped(client):
    html = _post(client, name="<b>x</b>", email="foo").get_data(as_text=True)

    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html


# ------------------------------------------------------------------ #
# Templates, CSS and test isolation                                   #
# ------------------------------------------------------------------ #

def test_templates_have_no_hardcoded_form_actions():
    # Source-level check: the rendered output of url_for() is identical to a
    # hardcoded path, so only the template source can tell them apart.
    register_src = (ROOT / "templates" / "register.html").read_text()
    login_src = (ROOT / "templates" / "login.html").read_text()

    assert 'action="/register"' not in register_src
    assert 'action="/login"' not in login_src
    assert "url_for('register')" in register_src
    assert "url_for('login')" in login_src


def test_auth_success_css_has_no_hex():
    css = (ROOT / "static" / "css" / "style.css").read_text()
    block = re.search(r"\.auth-success\s*\{([^}]*)\}", css)

    assert block is not None
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block.group(1))


def test_db_path_is_temporary(app, tmp_path):
    assert Path(db.DB_PATH).parent == tmp_path
    assert Path(db.DB_PATH) != ROOT / "expense_tracker.db"


# ------------------------------------------------------------------ #
# Other routes are unchanged                                          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("path", ["/", "/login", "/terms", "/privacy"])
def test_page_routes_still_render(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "path, text",
    [
        ("/logout", "coming in Step 3"),
        ("/profile", "coming in Step 4"),
        ("/expenses/add", "coming in Step 7"),
        ("/expenses/1/edit", "coming in Step 8"),
        ("/expenses/1/delete", "coming in Step 9"),
    ],
)
def test_stub_routes_unchanged(client, path, text):
    response = client.get(path)

    assert response.status_code == 200
    assert text in response.get_data(as_text=True)
