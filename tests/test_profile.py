import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest
from flask import url_for

ROOT = Path(__file__).resolve().parent.parent

DEMO = {"email": "demo@spendly.com", "password": "demo123"}

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
AMOUNT_RE = re.compile(r"₹([\d,]+\.\d{2})")

CATEGORY_SLUGS = [
    ("Food", "food"),
    ("Transport", "transport"),
    ("Bills", "bills"),
    ("Health", "health"),
    ("Entertainment", "entertainment"),
    ("Shopping", "shopping"),
    ("Other", "other"),
]


def _login(client):
    return client.post(url_for("login"), data=DEMO)


def _profile(client):
    _login(client)
    return client.get(url_for("profile"))


def _html(response):
    return response.get_data(as_text=True)


def _nav(response):
    return re.search(r'<nav class="navbar">.*?</nav>', _html(response), re.S).group(0)


def _location_path(response):
    return urlparse(response.headers["Location"]).path


def _table_rows(response):
    body = re.search(r"<tbody>(.*?)</tbody>", _html(response), re.S).group(1)
    return re.findall(r"<tr>(.*?)</tr>", body, re.S)


def _breakdown(response):
    return re.search(
        r'<ul class="profile-breakdown">(.*?)</ul>', _html(response), re.S
    ).group(1)


def _amount(text):
    return float(text.replace(",", ""))


# ------------------------------------------------------------------ #
# Access control                                                      #
# ------------------------------------------------------------------ #

def test_profile_redirects_to_login_when_signed_out(client):
    response = client.get(url_for("profile"))

    assert response.status_code == 302
    assert _location_path(response) == url_for("login")
    assert "?" not in response.headers["Location"]


def test_profile_signed_out_body_leaks_no_profile_data(client):
    response = client.get(url_for("profile"))

    assert DEMO["email"] not in _html(response)


def test_profile_returns_200_when_signed_in(client):
    response = _profile(client)

    assert response.status_code == 200
    assert response.mimetype == "text/html"


def test_profile_redirects_again_after_logout(client):
    _login(client)
    client.get(url_for("logout"))

    response = client.get(url_for("profile"))

    assert response.status_code == 302
    assert _location_path(response) == url_for("login")


def test_profile_rejects_post(client):
    _login(client)

    assert client.post(url_for("profile")).status_code == 405


# ------------------------------------------------------------------ #
# Navbar                                                              #
# ------------------------------------------------------------------ #

def test_profile_navbar_shows_name_and_sign_out(client):
    nav = _nav(_profile(client))

    assert "Demo User" in nav
    assert "Sign out" in nav
    assert f'href="{url_for("logout")}"' in nav
    assert "Sign in" not in nav


# ------------------------------------------------------------------ #
# User card                                                           #
# ------------------------------------------------------------------ #

def test_profile_shows_user_info_card(client):
    html = _html(_profile(client))

    avatar = re.search(r'<div class="profile-avatar"[^>]*>(.*?)</div>', html, re.S)
    heading = re.search(r'<h1 class="profile-name"[^>]*>(.*?)</h1>', html, re.S)

    assert avatar.group(1).strip() == "DU"
    assert heading.group(1).strip() == "Demo User"
    assert 'class="profile-email">demo@spendly.com<' in html
    # users.created_at defaults to SQLite's datetime('now'), which is UTC.
    assert f"Member since {datetime.now(timezone.utc).strftime('%B %Y')}" in html


# ------------------------------------------------------------------ #
# Summary stats                                                       #
# ------------------------------------------------------------------ #

def test_profile_shows_three_summary_stats(client):
    html = _html(_profile(client))

    values = re.findall(r'<dd class="profile-stat-value">(.*?)</dd>', html, re.S)

    assert values == ["₹327.64", "8", "Bills"]


def test_profile_stats_match_transaction_rows(client):
    response = _profile(client)
    html = _html(response)

    rows = _table_rows(response)
    row_amounts = [
        _amount(AMOUNT_RE.search(re.findall(r"<td[^>]*>.*?</td>", row, re.S)[-1]).group(1))
        for row in rows
    ]
    stats = re.findall(r'<dd class="profile-stat-value">(.*?)</dd>', html, re.S)

    assert sum(row_amounts) == pytest.approx(_amount(stats[0].lstrip("₹")))
    assert len(rows) == int(stats[1])


# ------------------------------------------------------------------ #
# Transactions table                                                  #
# ------------------------------------------------------------------ #

def test_profile_table_has_expected_headers_and_rows(client):
    response = _profile(client)
    html = _html(response)

    headers = re.findall(r'<th scope="col"[^>]*>(.*?)</th>', html, re.S)

    assert headers == ["Date", "Description", "Category", "Amount"]
    assert len(_table_rows(response)) == 8


def test_profile_table_formats_amounts_and_missing_descriptions(client):
    response = _profile(client)
    html = _html(response)
    rows = _table_rows(response)

    assert "₹120.00" in html
    assert "Electricity bill" in html
    # The newest row (Food, 27.40) has no description.
    assert "<td>—</td>" in rows[0]
    assert "None" not in "".join(rows)


def test_profile_rows_are_newest_first(client):
    html = _html(_profile(client))

    dates = re.findall(r'<time datetime="([\d-]+)">', html)

    assert len(dates) == 8
    assert dates == sorted(dates, reverse=True)


@pytest.mark.parametrize("name, slug", CATEGORY_SLUGS)
def test_profile_category_badges_use_css_classes(client, name, slug):
    html = _html(_profile(client))

    assert f'class="category-badge category-badge-{slug}">{name}</span>' in html


def test_profile_has_no_inline_styles(client):
    html = _html(_profile(client))

    assert not re.search(r"\sstyle\s*=", html)


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def test_profile_breakdown_lists_every_category_sorted(client):
    breakdown = _breakdown(_profile(client))

    names = re.findall(r'category-badge category-badge-[\w-]+">(.*?)</span>', breakdown)
    totals = [
        _amount(m)
        for m in re.findall(r'profile-breakdown-amount">\s*₹([\d,]+\.\d{2})', breakdown)
    ]

    assert names[0] == "Bills"
    assert sorted(names) == sorted(name for name, _ in CATEGORY_SLUGS)
    assert totals == sorted(totals, reverse=True)


def test_profile_breakdown_values_are_consistent(client):
    breakdown = _breakdown(_profile(client))

    meters = re.findall(
        r'<progress class="profile-meter" value="(\d+)" max="100" aria-label="([^"]+)"',
        breakdown,
    )
    totals = [
        _amount(m)
        for m in re.findall(r'profile-breakdown-amount">\s*₹([\d,]+\.\d{2})', breakdown)
    ]
    percents = [int(value) for value, _ in meters]

    assert len(meters) == len(CATEGORY_SLUGS)
    # Whole-number percentages; Bills absorbs the rounding remainder (101 -> 100).
    assert percents == [36, 20, 14, 12, 9, 6, 3]
    assert sum(percents) == 100
    assert sum(totals) == pytest.approx(327.64)


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "amount, expected",
    [(0, "₹0.00"), (12.5, "₹12.50"), (1234567.891, "₹1,234,567.89")],
)
def test_rupees_filter(app, amount, expected):
    assert app.jinja_env.filters["rupees"](amount) == expected


def test_format_date_filter(app):
    format_date = app.jinja_env.filters["format_date"]

    assert format_date("2026-10-08") == "08 Oct 2026"
    assert format_date("2026-01-15 09:30:00", "%B %Y") == "January 2026"


# ------------------------------------------------------------------ #
# Source-level checks                                                 #
# ------------------------------------------------------------------ #

def test_profile_template_extends_base_and_uses_url_for():
    source = (ROOT / "templates" / "profile.html").read_text(encoding="utf-8")

    assert source.lstrip().startswith('{% extends "base.html" %}')
    assert "url_for('static', filename='css/profile.css')" in source
    assert 'href="/' not in source


def test_profile_template_has_no_hex_or_inline_styles():
    source = (ROOT / "templates" / "profile.html").read_text(encoding="utf-8")

    assert not HEX_RE.search(source)
    assert not re.search(r"\sstyle\s*=", source)
    assert "<style" not in source


def test_profile_css_is_hex_free_and_served(client):
    css = (ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")

    assert not HEX_RE.search(css)
    assert not re.search(r"\b(?:rgb|rgba|hsl|hsla)\(", css)
    assert client.get(url_for("static", filename="css/profile.css")).status_code == 200
    assert "css/profile.css" in _html(_profile(client))


def test_profile_css_has_responsive_breakpoints_and_badge_rules():
    css = (ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")

    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 600px)" in css
    assert ".category-badge {" in css
    for _, slug in CATEGORY_SLUGS:
        if slug in {"food", "shopping", "transport", "health", "bills"}:
            assert f".category-badge-{slug}" in css


def test_profile_css_progress_pseudo_elements_are_separate_rules():
    css = (ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")
    selectors = re.findall(r"([^{}]+)\{", css)

    assert any("::-webkit-progress-value" in s for s in selectors)
    assert any("::-moz-progress-bar" in s for s in selectors)
    for selector in selectors:
        assert not ("-webkit-progress" in selector and "-moz-progress" in selector)
