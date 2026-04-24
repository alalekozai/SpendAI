# Spec: Registration

## Overview
This step implements user registration for Spendly. Visitors can create a new account by
submitting their name, email, and password via a form. The form validates input server-side,
checks for duplicate emails, hashes the password with werkzeug, inserts the new user via
`create_user()`, stores the user's `id` in the Flask session, and redirects to the dashboard.
This is the entry point for new users and must be working before login or any authenticated
feature can be built.

## Depends on
- Step 01 — Database Setup (`users` table, `create_user()`, `get_user_by_email()`)

## Routes
- `GET  /register` — render the registration form — public
- `POST /register` — handle form submission, create user, redirect — public

## Database changes
No database changes. The `users` table and `create_user()` / `get_user_by_email()` functions
already exist in `database/db.py`.

## Templates
- **Modify:** `templates/register.html` — add a working HTML form with fields: `name`, `email`,
  `password`, `confirm_password`; display flash error messages; submit via POST to `/register`

## Files to change
- `app.py` — convert `GET /register` stub into a full GET+POST route with validation logic
- `templates/register.html` — add the form and flash message block

## Files to create
No new files.

## New dependencies
No new dependencies. `flask` (session, redirect, url_for, flash, request) and `werkzeug`
are already available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (enforced through existing `db.py` helpers)
- Passwords hashed with `werkzeug.security.generate_password_hash` (already done in `create_user()`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `flask.session` to store `user_id` after successful registration
- Set `app.secret_key` in `app.py` (use `os.urandom(24)` or a fixed dev key)
- Validate server-side: all fields required, email format check, passwords must match,
  minimum password length of 8 characters
- If email already exists, flash an error and re-render the form (do not redirect)
- On success, redirect to `/dashboard` (placeholder route is acceptable at this stage)

## Definition of done
- [ ] `GET /register` renders the registration form without errors
- [ ] Submitting the form with all valid fields creates a new row in the `users` table
- [ ] Password stored in DB is hashed (not plaintext)
- [ ] `session['user_id']` is set after successful registration
- [ ] User is redirected after successful registration
- [ ] Submitting with a duplicate email shows a flash error and re-renders the form
- [ ] Submitting with mismatched passwords shows a flash error and re-renders the form
- [ ] Submitting with any empty field shows a flash error and re-renders the form
- [ ] All form inputs retain their values after a failed submission
