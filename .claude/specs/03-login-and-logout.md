# Spec: Login and Logout

## Overview
This step implements session-based login and logout for Spendly. Registered users can sign in
with their email and password via a form at `/login`. The server verifies the credentials using
`get_user_by_email()` and `werkzeug.security.check_password_hash`, stores the user's `id` in
the Flask session on success, and redirects to the dashboard. A `/logout` route clears the
session and redirects to the landing page. This is a prerequisite for every authenticated
feature that follows (dashboard, profile, expenses).

## Depends on
- Step 01 — Database Setup (`users` table, `get_user_by_email()`)
- Step 02 — Registration (session pattern, `app.secret_key`, `base.html` layout)

## Routes
- `GET  /login`  — render the login form — public
- `POST /login`  — validate credentials, set session, redirect to dashboard — public
- `GET  /logout` — clear session, redirect to landing page — public

## Database changes
No database changes. The `users` table and `get_user_by_email()` already exist in `database/db.py`.

## Templates
- **Modify:** `templates/login.html` — add a working HTML form with fields: `email`, `password`;
  display flash error messages; submit via POST to `/login`; link to `/register` for new users

## Files to change
- `app.py` — convert `GET /login` stub into a full GET+POST route with credential validation;
  implement the `/logout` route to clear the session and redirect

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` is already available via the
existing `werkzeug` install.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (enforced through existing `db.py` helpers)
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `flask.session` to store `user_id` after successful login
- Validate server-side: both fields required; if credentials are invalid flash a single generic
  message ("Invalid email or password") — do not reveal which field was wrong
- On successful login redirect to `/dashboard`
- `/logout` must call `session.clear()` then redirect to `url_for('landing')`

## Definition of done
- [ ] `GET /login` renders the login form without errors
- [ ] Submitting valid credentials sets `session['user_id']` and redirects to `/dashboard`
- [ ] Submitting an unrecognised email shows "Invalid email or password" and re-renders the form
- [ ] Submitting a wrong password shows "Invalid email or password" and re-renders the form
- [ ] Submitting with any empty field shows a flash error and re-renders the form
- [ ] `GET /logout` clears the session and redirects to the landing page
- [ ] After logout, navigating to `/dashboard` does not expose user data (placeholder is acceptable)
- [ ] The login form email field retains its value after a failed submission
