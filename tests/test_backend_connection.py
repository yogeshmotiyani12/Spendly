import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest
from flask import url_for

from database.db import (
    create_user,
    get_category_breakdown,
    get_db,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
DEMO_ID = 1  # the user seed_db() creates, with 8 expenses totalling 327.64

EMPTY_STATS = {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


def _add_expense(user_id, amount, category, date, description=None):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
    finally:
        conn.close()


def _new_user(name="Priya Sharma", email="priya@example.com", password="password123"):
    return create_user(name, email, password)


def _current_month():
    # users.created_at defaults to SQLite's datetime('now'), which is UTC.
    return datetime.now(timezone.utc).strftime("%B %Y")


def _login(client, email=DEMO["email"], password=DEMO["password"]):
    return client.post(url_for("login"), data={"email": email, "password": password})


def _profile(client, **credentials):
    _login(client, **credentials)
    return client.get(url_for("profile"))


def _html(response):
    return response.get_data(as_text=True)


def _stat_values(html):
    return re.findall(r'<dd class="profile-stat-value">(.*?)</dd>', html, re.S)


def _table_rows(html):
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    return re.findall(r"<tr>(.*?)</tr>", body, re.S)


def _breakdown_percents(html):
    return [
        int(p) for p in re.findall(r'profile-breakdown-percent">(\d+)%</span>', html)
    ]


# ------------------------------------------------------------------ #
# get_user_by_id()                                                    #
# ------------------------------------------------------------------ #

def test_get_user_by_id_returns_name_email_and_member_since(app):
    user = get_user_by_id(DEMO_ID)

    assert user == {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "member_since": _current_month(),
    }


def test_get_user_by_id_formats_member_since_from_created_at(app):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE users SET created_at = '2026-01-15 09:30:00' WHERE id = ?",
            (DEMO_ID,),
        )
        conn.commit()
    finally:
        conn.close()

    assert get_user_by_id(DEMO_ID)["member_since"] == "January 2026"


def test_get_user_by_id_returns_none_for_unknown_id(app):
    assert get_user_by_id(9999) is None


# ------------------------------------------------------------------ #
# get_summary_stats()                                                 #
# ------------------------------------------------------------------ #

def test_get_summary_stats_for_seed_user(app):
    stats = get_summary_stats(DEMO_ID)

    assert stats["total_spent"] == pytest.approx(327.64)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_with_no_expenses_returns_zeros(app):
    assert get_summary_stats(_new_user()) == EMPTY_STATS


def test_get_summary_stats_for_unknown_user_returns_zeros(app):
    assert get_summary_stats(9999) == EMPTY_STATS


def test_get_summary_stats_breaks_category_ties_by_name(app):
    user_id = _new_user()
    _add_expense(user_id, 10.00, "Food", "2026-03-01")
    _add_expense(user_id, 10.00, "Bills", "2026-03-02")

    assert get_summary_stats(user_id)["top_category"] == "Bills"


def test_get_summary_stats_ignores_other_users(app):
    user_id = _new_user()
    _add_expense(user_id, 5.00, "Food", "2026-03-01")

    assert get_summary_stats(user_id) == {
        "total_spent": 5.0,
        "transaction_count": 1,
        "top_category": "Food",
    }
    assert get_summary_stats(DEMO_ID)["transaction_count"] == 8


def test_get_summary_stats_rounds_float_noise(app):
    user_id = _new_user()
    _add_expense(user_id, 0.1, "Food", "2026-03-01")
    _add_expense(user_id, 0.2, "Food", "2026-03-02")

    assert get_summary_stats(user_id)["total_spent"] == 0.3


# ------------------------------------------------------------------ #
# get_recent_transactions()                                           #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_for_seed_user(app):
    transactions = get_recent_transactions(DEMO_ID)

    assert len(transactions) == 8
    assert all(
        set(t) == {"date", "description", "category", "amount"} for t in transactions
    )
    dates = [t["date"] for t in transactions]
    assert dates == sorted(dates, reverse=True)

    newest, oldest = transactions[0], transactions[-1]
    assert (newest["category"], newest["amount"], newest["description"]) == (
        "Food",
        27.4,
        None,
    )
    assert (oldest["category"], oldest["amount"], oldest["description"]) == (
        "Food",
        12.5,
        "Lunch at cafe",
    )


def test_get_recent_transactions_returns_plain_dicts(app):
    assert all(type(t) is dict for t in get_recent_transactions(DEMO_ID))


def test_get_recent_transactions_with_no_expenses_returns_empty_list(app):
    assert get_recent_transactions(_new_user()) == []
    assert get_recent_transactions(9999) == []


def test_get_recent_transactions_honours_limit(app):
    newest_three = get_recent_transactions(DEMO_ID, limit=3)

    assert newest_three == get_recent_transactions(DEMO_ID)[:3]


def test_get_recent_transactions_defaults_to_ten_rows(app):
    for day in range(1, 5):  # 8 seeded + 4 older rows = 12
        _add_expense(DEMO_ID, 1.00, "Other", f"2020-01-0{day}")

    assert len(get_recent_transactions(DEMO_ID)) == 10


def test_get_recent_transactions_orders_same_date_by_newest_id(app):
    _add_expense(DEMO_ID, 1.00, "Other", "2099-12-31", "first")
    _add_expense(DEMO_ID, 2.00, "Other", "2099-12-31", "second")

    transactions = get_recent_transactions(DEMO_ID)

    assert [t["description"] for t in transactions[:2]] == ["second", "first"]


def test_get_recent_transactions_ignores_other_users(app):
    user_id = _new_user()
    _add_expense(user_id, 5.00, "Food", "2026-03-01", "Snack")

    assert [t["description"] for t in get_recent_transactions(user_id)] == ["Snack"]
    assert len(get_recent_transactions(DEMO_ID)) == 8


# ------------------------------------------------------------------ #
# get_category_breakdown()                                            #
# ------------------------------------------------------------------ #

def test_get_category_breakdown_for_seed_user(app):
    breakdown = get_category_breakdown(DEMO_ID)

    assert [c["name"] for c in breakdown] == [
        "Bills",
        "Shopping",
        "Transport",
        "Food",
        "Health",
        "Entertainment",
        "Other",
    ]
    assert [c["amount"] for c in breakdown] == [
        120.0,
        64.75,
        45.0,
        39.9,
        30.0,
        18.99,
        9.0,
    ]
    # Naive rounding gives 37/20/14/12/9/6/3 = 101; Bills absorbs the extra 1.
    assert [c["pct"] for c in breakdown] == [36, 20, 14, 12, 9, 6, 3]
    assert all(type(c["pct"]) is int for c in breakdown)
    assert sum(c["pct"] for c in breakdown) == 100


def test_get_category_breakdown_with_no_expenses_returns_empty_list(app):
    assert get_category_breakdown(_new_user()) == []
    assert get_category_breakdown(9999) == []


def test_get_category_breakdown_single_category_is_one_hundred_percent(app):
    user_id = _new_user()
    _add_expense(user_id, 10.00, "Food", "2026-03-01")

    assert get_category_breakdown(user_id) == [
        {"name": "Food", "amount": 10.0, "pct": 100}
    ]


def test_get_category_breakdown_gives_rounding_remainder_to_first_category(app):
    user_id = _new_user()
    for category in ("Health", "Bills", "Food"):
        _add_expense(user_id, 10.00, category, "2026-03-01")

    breakdown = get_category_breakdown(user_id)

    # Equal totals sort by name; 33.3 rounds to 33 each, so the first gets +1.
    assert [(c["name"], c["pct"]) for c in breakdown] == [
        ("Bills", 34),
        ("Food", 33),
        ("Health", 33),
    ]


def test_get_category_breakdown_ignores_other_users(app):
    user_id = _new_user()
    _add_expense(user_id, 10.00, "Food", "2026-03-01")

    assert [c["name"] for c in get_category_breakdown(user_id)] == ["Food"]
    assert len(get_category_breakdown(DEMO_ID)) == 7


# ------------------------------------------------------------------ #
# GET /profile                                                        #
# ------------------------------------------------------------------ #

def test_profile_redirects_to_login_when_signed_out(client):
    response = client.get(url_for("profile"))

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == url_for("login")


def test_profile_shows_seed_user_from_the_database(client):
    response = _profile(client)
    html = _html(response)

    assert response.status_code == 200
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert f"Member since {_current_month()}" in html
    assert "₹" in html


def test_profile_shows_seed_summary_stats(client):
    html = _html(_profile(client))

    assert _stat_values(html) == ["₹327.64", "8", "Bills"]


def test_profile_lists_seed_transactions_newest_first(client):
    html = _html(_profile(client))

    dates = re.findall(r'<time datetime="([\d-]+)">', html)

    assert len(_table_rows(html)) == 8
    assert dates == sorted(dates, reverse=True)


def test_profile_breakdown_shows_all_categories_summing_to_100(client):
    html = _html(_profile(client))

    assert html.count('class="profile-breakdown-row"') == 7
    percents = _breakdown_percents(html)
    assert percents == [36, 20, 14, 12, 9, 6, 3]
    assert sum(percents) == 100


def test_profile_uses_rupee_symbol_only(client):
    html = _html(_profile(client))

    assert not re.search(r"[$£]\s?\d", html)


def test_profile_shows_only_the_signed_in_users_own_data(client):
    user_id = _new_user()
    _add_expense(user_id, 100.00, "Food", "2026-03-01", "Dinner")
    _add_expense(user_id, 50.50, "Transport", "2026-03-02", "Cab")

    html = _html(_profile(client, email="priya@example.com", password="password123"))

    assert "Priya Sharma" in html
    assert "priya@example.com" in html
    assert "Dinner" in html and "Cab" in html
    assert "Demo User" not in html
    assert "demo@spendly.com" not in html
    assert "Electricity bill" not in html
    assert _stat_values(html) == ["₹150.50", "2", "Food"]
    assert len(_table_rows(html)) == 2


def test_profile_for_a_user_with_no_expenses_shows_zeros_and_empty_states(client):
    _new_user()

    response = _profile(client, email="priya@example.com", password="password123")
    html = _html(response)

    assert response.status_code == 200
    assert _stat_values(html) == ["₹0.00", "0", "—"]
    assert _table_rows(html) == []
    assert html.count('class="profile-breakdown-row"') == 0
    assert "No transactions yet." in html
    assert "No spending to show yet." in html


def test_profile_caps_the_table_at_ten_rows_but_counts_everything(client):
    for day in range(1, 6):  # 8 seeded + 5 more = 13
        _add_expense(DEMO_ID, 1.00, "Other", f"2020-01-0{day}")

    html = _html(_profile(client))

    assert len(_table_rows(html)) == 10
    assert _stat_values(html)[1] == "13"


def test_profile_clears_a_stale_session_and_redirects_to_login(client):
    _login(client)
    with client.session_transaction() as sess:
        sess["user_id"] = 9999  # an account that does not exist

    response = client.get(url_for("profile"))

    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == url_for("login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
