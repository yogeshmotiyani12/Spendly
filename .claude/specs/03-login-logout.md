# Spec: Login and Logout

## Overview

Make the existing `/login` page actually sign people in, and turn the `/logout` stub into a real sign-out. Today `GET /login` only renders `login.html`; its form posts to a route that accepts no POST, and `/logout` returns a raw string. This step adds the POST handler: look up the user by email, verify the password against the stored werkzeug hash, and start a Flask session holding the user's id and name. `/logout` clears that session. It also makes the navbar session-aware (Sign in / Get started when signed out; the user's name and Sign out when signed in). This is the first use of sessions in Spendly and the prerequisite for every logged-in page that follows (profile in Step 4, expenses in Steps 7–9).

## Depends on

- Step 1 — Database setup (`users` table, `get_db()`, seeded demo user `demo@spendly.com` / `demo123`).
- Step 2 — Registration (real accounts to sign in with; `/login?registered=1` notice; email is stored lowercased).

## Routes

- `GET /login` — existing; renders the sign-in form. If the visitor is already signed in, redirect to `/` instead — public
- `POST /login` — new; validates the form, authenticates, starts the session and redirects to `/` on success, re-renders the form with an error on failure — public
- `GET /logout` — existing stub, now implemented; clears the session and redirects to `/` — public (harmless if not signed in)
- `GET /register` — existing; modified only so an already-signed-in visitor is redirected to `/` — public

`/login` becomes `methods=["GET", "POST"]` on the existing route function. No other routes are added or changed. The remaining stubs (`/profile`, `/expenses/*`) must stay untouched — in particular, **do not** add login-required protection to them and do not redirect to `/profile` after login (it is still a stub until Step 4).

## Database changes

No database changes. The existing `users` table has everything needed (`email`, `password_hash`, `name`).

One new function in `database/db.py`:

- `authenticate_user(email, password)` — looks the user up with a parameterized `SELECT id, name, password_hash FROM users WHERE email = ?`, verifies `password` with werkzeug's `check_password_hash`, and returns the matching `sqlite3.Row` on success or `None` if the email is unknown **or** the password is wrong (callers must not be able to tell which). Opens its connection with `get_db()` and always closes it, following the `try/finally` pattern already used in `create_user()`.

## Templates

- **Create:** none
- **Modify:**
  - `templates/login.html`
    - Re-populate the email input after a failed submit (`value="{{ email or '' }}"`). Never re-populate the password.
    - The existing `{% if error %}` and `{% if registered %}` blocks and the `url_for('login')` form action stay as they are.
  - `templates/base.html`
    - Make the navbar session-aware using Jinja's built-in `session`:
      - signed out (`session.get('user_id')` falsy): keep the current "Sign in" and "Get started" links
      - signed in: show the user's name (`{{ session['user_name'] }}`, auto-escaped) and a "Sign out" link to `{{ url_for('logout') }}`
    - The "Sign out" link must remain visible on small screens (the existing mobile rule hides every `.nav-links a` that is not `.nav-cta`).

## Files to change

- `app.py` — set `app.secret_key` and `SESSION_COOKIE_SAMESITE`; import `os`, `session`, `authenticate_user`; accept POST on `/login`; implement `logout()`; redirect signed-in visitors away from `/login` and `/register`
- `database/db.py` — add `authenticate_user()` (and import `check_password_hash`)
- `templates/login.html` — see above
- `templates/base.html` — see above
- `static/css/style.css` — add a small rule for the signed-in user name in the navbar (e.g. `.nav-user`), using only existing CSS variables; adjust the mobile `.nav-links` rule so "Sign out" stays visible
- `CLAUDE.md` — update the "Implemented vs stub routes" table: add `POST /login` as implemented and mark `GET /logout` as implemented

## Files to create

- `tests/test_login.py` — tests covering the behaviors in the Definition of done (login success/failure, session contents, logout, nav state, already-signed-in redirects)

## New dependencies

No new dependencies. Flask's built-in signed-cookie `session` and werkzeug's `check_password_hash` are already available.

## Session and secret key

- `app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")` — read from the environment so it can be overridden outside development; the fallback is for local development only and must be commented as such.
- On successful login: `session.clear()` first, then store exactly `session["user_id"]` (int) and `session["user_name"]` (str). Nothing else (never the email or hash).
- On logout: `session.clear()`.
- Set `SESSION_COOKIE_HTTPONLY = True` (Flask default — leave it) and `SESSION_COOKIE_SAMESITE = "Lax"`.

## Validation rules

Applied in this order; the first failure wins and its message is shown in the form's existing `.auth-error` banner:

| Check | Error message |
|---|---|
| `email` (after `.strip().lower()`) or `password` is empty | "Please enter your email and password." |
| `authenticate_user()` returns `None` (unknown email **or** wrong password) | "Invalid email or password." |

Failures re-render `login.html` with HTTP 200, the error text and the submitted email preserved. The unknown-email and wrong-password cases must produce the identical message so the form cannot be used to discover which emails have accounts. The email is normalized with `.strip().lower()` — the same normalization registration applies before storing. The password is never stripped.

There is deliberately **no** `next` redirect parameter (avoids an open-redirect surface); a successful login always redirects to `url_for("landing")`.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only — no f-strings or `%`/`.format()` in SQL
- Passwords hashed with werkzeug; verify with `check_password_hash`; never store, log, or echo a plaintext password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB logic lives in `database/db.py`; the route only reads the form, calls `authenticate_user()`, sets/clears the session and renders or redirects
- Use `url_for()` for every internal link and every redirect target — never hardcode URLs
- Do not add `flask-login`, `flask-session`, or any other package
- Do not use `flash()`; the existing `registered` query-param notice and the `error` template variable are the only messages
- Do not implement any other stub route (`/profile`, `/expenses/*`) and do not add login-required guards to them
- Do not change the port (5001) or the `init_db()`/`seed_db()` startup calls
- No JS needed; if any is added it must be vanilla

## Definition of done

- [ ] `GET /login` still renders the form (HTTP 200) when signed out, and the `?registered=1` notice still appears
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects (302) to `/`
- [ ] After login, the session contains `user_id` and `user_name` (`Demo User`) and nothing containing the password or hash
- [ ] After login, the navbar shows the user's name and a "Sign out" link, and no longer shows "Sign in" / "Get started"
- [ ] Email matching is case- and whitespace-insensitive (`  DEMO@Spendly.com ` signs in successfully)
- [ ] A user created through `/register` can immediately sign in with the same credentials
- [ ] A wrong password and an unknown email both re-render the form (HTTP 200) with exactly "Invalid email or password." and no session is set
- [ ] Submitting an empty email or password (bypassing the browser's `required`) shows "Please enter your email and password."
- [ ] After a failed submit, the email field keeps what was typed and the password field is empty
- [ ] `GET /logout` redirects (302) to `/`, the session is empty afterwards, and the navbar is back to "Sign in" / "Get started"
- [ ] `GET /logout` while signed out does not error
- [ ] `GET /login` and `GET /register` while signed in redirect (302) to `/`
- [ ] A user name containing HTML (e.g. `<b>x</b>`) is escaped in the navbar
- [ ] "Sign out" is visible at mobile width (narrow viewport) when signed in
- [ ] The new styles contain no hardcoded hex values; no hardcoded `/login` or `/logout` URLs appear in templates
- [ ] `pytest` passes (including the existing registration tests), and tests run against a temporary database — they never touch `expense_tracker.db`
- [ ] The app starts on port 5001 with no errors and `/profile` and `/expenses/*` behave exactly as before
