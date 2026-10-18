# Spec: Registration

## Overview

Make the existing `/register` page actually create accounts. Today `GET /register` only renders `register.html`; the form posts to a route that accepts no POST, so no user can be created except the seeded demo user. This step adds the POST handler: validate the submitted name, email and password, hash the password with werkzeug, insert the user into the `users` table, and send the visitor to the login page. It is the first write path through the data layer built in Step 1 and the prerequisite for login (Step 3), since login needs real accounts to authenticate against. It deliberately does **not** log the user in — sessions do not exist until Step 3.

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`).

## Routes

- `GET /register` — existing; renders the empty registration form — public
- `POST /register` — new; validates the form, creates the user, redirects to `/login?registered=1` on success, re-renders the form with an error on failure — public
- `GET /login` — existing; modified only to show a one-line "account created" notice when `?registered=1` is present — public

`/register` becomes `methods=["GET", "POST"]` on the existing route function. No other routes are added or changed. Stub routes (`/logout`, `/profile`, `/expenses/*`) must stay untouched.

## Database changes

No database changes. The existing `users` table already has everything needed (`name`, `email UNIQUE NOT NULL`, `password_hash`, `created_at`).

One new function in `database/db.py`:

- `create_user(name, email, password)` — hashes `password` with `generate_password_hash(password, method="pbkdf2:sha256")` (same method as `seed_db()`), inserts the row with a parameterized query, and returns the new user's `id`. If the email is already taken (`sqlite3.IntegrityError` on the UNIQUE constraint) it returns `None`. Opens its connection with `get_db()` and always closes it, following the `try/finally` pattern already used in `init_db()` and `seed_db()`.

## Templates

- **Create:** none
- **Modify:**
  - `templates/register.html`
    - Replace hardcoded `action="/register"` with `action="{{ url_for('register') }}"`.
    - Re-populate the `name` and `email` inputs with the submitted values after a failed submit (`value="{{ name or '' }}"` / `value="{{ email or '' }}"`). Never re-populate the password.
    - The existing `{% if error %}` block already renders the error message; keep it.
  - `templates/login.html`
    - Replace hardcoded `action="/login"` with `action="{{ url_for('login') }}"`.
    - When `registered` is truthy, show a success notice above the form: "Account created. Please sign in."

## Files to change

- `app.py` — accept POST on `/register`; add a small `_validate_registration(name, email, password)` helper that returns an error string or `None`; pass `registered` into the `/login` template; import `create_user`, `request`, `redirect`, `url_for`
- `database/db.py` — add `create_user()`
- `templates/register.html` — see above
- `templates/login.html` — see above
- `static/css/style.css` — add an `.auth-success` rule next to the existing `.auth-error` rule, using only CSS variables (`--accent-light`, `--accent`, `--radius-sm`)
- `CLAUDE.md` — update the "Implemented vs stub routes" table to note `POST /register` is implemented

## Files to create

- `tests/conftest.py` — `app` fixture (required by pytest-flask) that points `database.db.DB_PATH` at a temporary file via `monkeypatch`, runs `init_db()`, and a `client` fixture
- `tests/test_registration.py` — tests covering the behaviors in the Definition of done

## New dependencies

No new dependencies. `pytest` and `pytest-flask` are already in `requirements.txt`.

## Validation rules

Applied in this order; the first failure wins and its message is shown in the form's error banner:

| Check | Error message |
|---|---|
| `name` is empty after `.strip()` | "Please enter your name." |
| `email` (after `.strip().lower()`) is not shaped like `local@domain.tld` — exactly one `@`, non-empty local part, domain containing a `.`, no whitespace | "Please enter a valid email address." |
| `password` is shorter than 8 characters (not stripped) | "Password must be at least 8 characters." |
| `create_user()` returns `None` (duplicate email) | "An account with that email already exists." |

The email is normalized to lowercase before it is stored, because SQLite's UNIQUE constraint is case-sensitive and `Demo@Spendly.com` must not be able to shadow `demo@spendly.com`. Validation failures re-render `register.html` with HTTP 200 and the error text. Email validation uses plain string/`re` checks from the standard library only.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — no f-strings or `%`/`.format()` in SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store, log, or echo a plaintext password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB logic lives in `database/db.py`; the route only validates, calls `create_user()`, and renders or redirects
- Use `url_for()` for every internal link and for the redirect target — never hardcode URLs
- Do not add sessions, `app.secret_key`, or `flash()` — those belong to Step 3
- Do not implement any stub route
- Do not change the port (5001) or the `init_db()`/`seed_db()` startup calls
- No JS needed; if any is added it must be vanilla

## Definition of done

- [ ] `GET /register` still renders the form (HTTP 200)
- [ ] Submitting valid name, email and an 8+ character password redirects (302) to `/login?registered=1` and the login page shows "Account created. Please sign in."
- [ ] The new row exists in `users` with the submitted name, a lowercased email, and a `password_hash` that is not the plaintext and passes `check_password_hash`
- [ ] Registering the same email a second time (including with different letter case, e.g. `DEMO@spendly.com`) re-renders the form with "An account with that email already exists." and creates no second row
- [ ] Registering as `demo@spendly.com` is rejected the same way
- [ ] An empty or whitespace-only name shows "Please enter your name."
- [ ] An invalid email (`foo`, `foo@bar`, `a b@c.com`) shows "Please enter a valid email address."
- [ ] A password shorter than 8 characters shows "Password must be at least 8 characters."
- [ ] After any failed submit, the name and email fields keep what was typed and the password field is empty
- [ ] Both forms' `action` attributes come from `url_for()`; no hardcoded `/register` or `/login` remains in those two templates
- [ ] The new styles contain no hardcoded hex values
- [ ] `pytest` passes, and the tests run against a temporary database — they never touch `expense_tracker.db`
- [ ] The app starts on port 5001 with no errors and the other routes behave as before
