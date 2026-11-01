import os
import sqlite3
from datetime import date, datetime

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)

# Checked against when a login email is unknown, so that path costs the same
# as a wrong-password one.
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password", method="pbkdf2:sha256")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (
                "Demo User",
                "demo@spendly.com",
                generate_password_hash("demo123", method="pbkdf2:sha256"),
            ),
        )
        user_id = cursor.lastrowid

        today = date.today()
        expenses = [
            (1, 12.50, "Food", "Lunch at cafe"),
            (2, 45.00, "Transport", "Monthly bus pass top-up"),
            (3, 120.00, "Bills", "Electricity bill"),
            (4, 30.00, "Health", "Pharmacy"),
            (5, 18.99, "Entertainment", "Movie ticket"),
            (6, 64.75, "Shopping", "New shirt"),
            (7, 9.00, "Other", None),
            (8, 27.40, "Food", None),
        ]
        rows = [
            (user_id, amount, category, today.replace(day=day).isoformat(), description)
            for day, amount, category, description in expenses
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def create_user(name, email, password):
    """Insert a new user and return its id, or None if the email is taken."""
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def authenticate_user(email, password):
    """Return the user row (id, name, password_hash) for valid credentials, else None.

    Unknown email and wrong password both return None. `email` must already be
    normalized (stripped, lowercased) by the caller.
    """
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()

    password_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
    if check_password_hash(password_hash, password) and user is not None:
        return user
    return None


def get_user_by_id(user_id):
    """Return {"name", "email", "member_since"} for a user, or None if not found.

    `member_since` comes from users.created_at, formatted "Month YYYY".
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    created_at = row["created_at"]
    member_since = (
        datetime.fromisoformat(created_at).strftime("%B %Y") if created_at else "—"
    )
    return {"name": row["name"], "email": row["email"], "member_since": member_since}


def get_recent_transactions(user_id, limit=10):
    """Return up to `limit` of the user's expenses, newest first.

    Each item is {"date", "description", "category", "amount"}; description may
    be None. A user with no expenses gets an empty list.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_summary_stats(user_id):
    """Return {"total_spent", "transaction_count", "top_category"} for all of a
    user's expenses.

    top_category is the category with the highest total (ties: name ascending).
    A user with no expenses gets zeros and "—" rather than an error.
    """
    conn = get_db()
    try:
        count, total = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY ROUND(SUM(amount), 2) DESC, category ASC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if count == 0:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    return {
        "total_spent": round(total, 2),
        "transaction_count": count,
        "top_category": top["category"],
    }


def get_category_breakdown(user_id):
    """Return [{"name", "amount", "pct"}] for a user, largest category first.

    `pct` is a whole number and the values always sum to exactly 100: the
    largest category absorbs any rounding remainder. No expenses -> [].
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, ROUND(SUM(amount), 2) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category "
            "ORDER BY ROUND(SUM(amount), 2) DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    grand_total = sum(row["total"] for row in rows)
    if grand_total <= 0:
        return []

    breakdown = [
        {
            "name": row["category"],
            "amount": row["total"],
            "pct": round(row["total"] / grand_total * 100),
        }
        for row in rows
    ]
    breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
    return breakdown
