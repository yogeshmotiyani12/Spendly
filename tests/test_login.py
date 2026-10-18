import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from flask import url_for

from database.db import authenticate_user, get_db

ROOT = Path(__file__).resolve().parent.parent

DEMO = {"email": "demo@spendly.com", "password": "demo123"}

INVALID_MESSAGE = "Invalid email or password."
EMPTY_MESSAGE = "Please enter your email and password."


def _login(client, **overrides):
    return client.post(url_for("login"), data={**DEMO, **overrides})


def _register(client, name, email, password):
    return client.post(
        url_for("register"),
        data={"name": name, "email": email, "password": password},
    )


def _session(client):
    # pytest-flask keeps its own request context open, so flask.session in a
    # test body is not the test client's session — read it through the client.
    with client.session_transaction() as sess:
        return dict(sess)


def _nav(response):
    html = response.get_data(as_text=True)
    return re.search(r'<nav class="navbar">.*?</nav>', html, re.S).group(0)


def _error_banner(response):
    html = response.get_data(as_text=True)
    match = re.search(r'<div class="auth-error">(.*?)</div>', html, re.S)
    return match.group(1).strip() if match else None


def _location_path(response):
    return urlparse(response.headers["Location"]).path


def _count_users():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# authenticate_user()                                                 #
# ------------------------------------------------------------------ #

def test_authenticate_user_returns_row_for_valid_credentials(app):
    user = authenticate_user(DEMO["email"], DEMO["password"])

    assert user is not None
    assert user["name"] == "Demo User"
    assert isinstance(user["id"], int)


def test_authenticate_user_rejects_wrong_password(app):
    assert authenticate_user(DEMO["email"], "wrong-password") is None


def test_authenticate_user_rejects_unknown_email(app):
    assert authenticate_user("nobody@example.com", DEMO["password"]) is None


# ------------------------------------------------------------------ #
# GET /login                                                          #
# ------------------------------------------------------------------ #

def test_login_page_renders_when_signed_out(client):
    response = client.get(url_for("login"))

    assert response.status_code == 200
    assert 'name="email"' in response.get_data(as_text=True)


def test_login_page_still_shows_registered_notice(client):
    response = client.get(url_for("login", registered=1))

    assert response.status_code == 200
    assert "Account created. Please sign in." in response.get_data(as_text=True)


# ------------------------------------------------------------------ #
# POST /login — success                                               #
# ------------------------------------------------------------------ #

def test_login_redirects_to_landing(client):
    response = _login(client)

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")


def test_login_stores_only_id_and_name_in_session(client):
    _login(client)
    sess = _session(client)

    assert set(sess) == {"user_id", "user_name"}
    assert isinstance(sess["user_id"], int)
    assert sess["user_name"] == "Demo User"
    assert not any(
        "demo123" in str(value) or "pbkdf2" in str(value) for value in sess.values()
    )


def test_login_sets_httponly_samesite_cookie(client):
    response = _login(client)
    cookie = " ".join(response.headers.getlist("Set-Cookie"))

    assert "session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_app_has_a_secret_key(app):
    assert app.secret_key


def test_login_navbar_shows_name_and_sign_out(client):
    _login(client)
    nav = _nav(client.get(url_for("landing")))

    assert "Demo User" in nav
    assert "Sign out" in nav
    assert url_for("logout") in nav
    assert "Sign in" not in nav
    assert "Get started" not in nav


def test_login_email_is_case_and_whitespace_insensitive(client):
    response = _login(client, email="  DEMO@Spendly.com ")

    assert response.status_code == 302
    assert _session(client)["user_name"] == "Demo User"


def test_registered_user_can_sign_in_immediately(client):
    _register(client, "Alice Example", "alice@example.com", "correct-horse")
    response = _login(client, email="alice@example.com", password="correct-horse")

    assert response.status_code == 302
    assert _session(client)["user_name"] == "Alice Example"


def test_login_discards_prior_session_state(client):
    with client.session_transaction() as sess:
        sess["junk"] = "stale"

    _login(client)

    assert "junk" not in _session(client)


def test_login_ignores_next_parameter(client):
    response = client.post(
        url_for("login") + "?next=http://evil.example", data=DEMO
    )

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")
    assert "evil" not in response.headers["Location"]


# ------------------------------------------------------------------ #
# POST /login — failure                                               #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "wrong-password"},
        {"email": "nobody@example.com"},
    ],
    ids=["wrong-password", "unknown-email"],
)
def test_bad_credentials_show_generic_error(client, overrides):
    response = _login(client, **overrides)

    assert response.status_code == 200
    assert _error_banner(response) == INVALID_MESSAGE
    assert _session(client) == {}


def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    wrong_password = _login(client, password="wrong-password")
    unknown_email = _login(client, email="nobody@example.com")

    assert _error_banner(wrong_password) == _error_banner(unknown_email)


@pytest.mark.parametrize(
    "email, password",
    [
        ("", "demo123"),
        ("   ", "demo123"),
        ("demo@spendly.com", ""),
        ("", ""),
    ],
    ids=["empty-email", "blank-email", "empty-password", "both-empty"],
)
def test_empty_fields_show_required_error(client, email, password):
    response = _login(client, email=email, password=password)

    assert response.status_code == 200
    assert _error_banner(response) == EMPTY_MESSAGE
    assert _session(client) == {}


def test_whitespace_only_password_is_not_stripped(client):
    response = _login(client, password="   ")

    assert response.status_code == 200
    assert _error_banner(response) == INVALID_MESSAGE


def test_failed_login_keeps_email_and_never_echoes_password(client):
    response = _login(client, email="nobody@example.com", password="wrong-password-xyz")
    html = response.get_data(as_text=True)
    password_input = re.search(r'<input type="password"[^>]*>', html, re.S).group(0)

    assert 'value="nobody@example.com"' in html
    assert "wrong-password-xyz" not in html
    assert "value=" not in password_input


def test_failed_login_escapes_submitted_email(client):
    response = _login(client, email='x"><script>alert(1)</script>')
    html = response.get_data(as_text=True)

    assert "<script>alert(1)</script>" not in html


def test_sql_injection_attempt_is_rejected(client):
    response = _login(client, email="' or '1'='1", password="' or '1'='1")

    assert response.status_code == 200
    assert _error_banner(response) == INVALID_MESSAGE
    assert _session(client) == {}


# ------------------------------------------------------------------ #
# GET /logout                                                         #
# ------------------------------------------------------------------ #

def test_logout_clears_session_and_redirects(client):
    _login(client)
    response = client.get(url_for("logout"))

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")
    assert _session(client) == {}


def test_navbar_is_signed_out_after_logout(client):
    _login(client)
    client.get(url_for("logout"))

    assert client.get(url_for("login")).status_code == 200
    nav = _nav(client.get(url_for("landing")))
    assert "Sign in" in nav
    assert "Get started" in nav
    assert "Sign out" not in nav


def test_logout_without_session_does_not_error(client):
    response = client.get(url_for("logout"))

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")


def test_logout_rejects_post(client):
    assert client.post(url_for("logout")).status_code == 405


def test_signed_out_navbar_shows_sign_in_links(client):
    nav = _nav(client.get(url_for("landing")))

    assert "Sign in" in nav
    assert "Get started" in nav
    assert "Sign out" not in nav


# ------------------------------------------------------------------ #
# Signed-in visitors are redirected away from the auth pages          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "endpoint, values",
    [
        ("login", {}),
        ("login", {"registered": 1}),
        ("register", {}),
    ],
    ids=["login", "login-registered", "register"],
)
def test_signed_in_get_redirects_to_landing(client, endpoint, values):
    _login(client)
    response = client.get(url_for(endpoint, **values))

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")


def test_signed_in_post_login_is_redirected_and_session_unchanged(client):
    _login(client)
    before = _session(client)

    response = _login(client, email="nobody@example.com", password="wrong-password")

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")
    assert _session(client) == before


def test_signed_in_post_register_creates_no_user(client):
    _login(client)
    before = _count_users()

    response = _register(client, "Bob Example", "bob@example.com", "correct-horse")

    assert response.status_code == 302
    assert _location_path(response) == url_for("landing")
    assert _count_users() == before


# ------------------------------------------------------------------ #
# Escaping                                                            #
# ------------------------------------------------------------------ #

def test_user_name_is_escaped_in_navbar(client):
    _register(client, "<b>x</b>", "html@example.com", "correct-horse")
    _login(client, email="html@example.com", password="correct-horse")
    nav = _nav(client.get(url_for("landing")))

    assert "&lt;b&gt;x&lt;/b&gt;" in nav
    assert "<b>x</b>" not in nav


# ------------------------------------------------------------------ #
# Source-level checks                                                 #
# ------------------------------------------------------------------ #

def test_base_template_has_no_hardcoded_auth_urls():
    base_src = (ROOT / "templates" / "base.html").read_text()

    assert 'href="/login"' not in base_src
    assert 'href="/logout"' not in base_src
    assert "url_for('logout')" in base_src
    assert 'class="nav-signout"' in base_src


def test_nav_css_has_no_hex_and_keeps_sign_out_visible_on_mobile():
    css = (ROOT / "static" / "css" / "style.css").read_text()

    new_rules = re.findall(r"\.nav-(?:user|signout)\s*\{([^}]*)\}", css)
    assert new_rules
    assert not any(re.search(r"#[0-9a-fA-F]{3,8}\b", rule) for rule in new_rules)

    mobile_blocks = re.findall(
        r"@media \(max-width: 600px\) \{(.*?)\n\}", css, re.S
    )
    nav_block = next(block for block in mobile_blocks if ".nav-links" in block)
    assert ".nav-links a:not(.nav-cta):not(.nav-signout)" in nav_block
