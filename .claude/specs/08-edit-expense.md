# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user edit an existing expense through a pre-populated form at
`/expenses/<id>/edit`. The stub route already exists in `app.py`; this step upgrades
it to a full GET + POST handler. On GET, the form is populated with the expense's
current values. On POST, the submitted data is validated with the same rules as the
add-expense form, and the row is updated in the database via the existing
`update_expense` helper in `database/db.py`. The user is redirected back to the
profile page on success. Edit links are added to the transaction table on the profile
page so users can reach the form from their expense list.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` is set and checked)
- Step 5: Profile page routes exist and serve as the redirect target
- Step 7: Add Expense (establishes `VALID_CATEGORIES`, `insert_expense`, and `add_expense.html` as a reference for the form structure)

## Routes
- `GET /expenses/<int:id>/edit` — render pre-populated edit form — logged-in only
- `POST /expenses/<int:id>/edit` — validate and update the expense — logged-in only

## Database changes
No database changes. The `expenses` table and `update_expense` helper in
`database/db.py` already support all required operations.

## Templates
- **Create**: `templates/edit_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and `action="/expenses/<id>/edit"`
  - Fields (all pre-populated from the existing expense row):
    - `title` — text input, required, max 100 chars
    - `amount` — number input, step="0.01", min="0.01", required
    - `category` — `<select>` with the 7 fixed options: Food, Transport, Bills, Health, Entertainment, Shopping, Other; pre-selects the current category
    - `date` — `<input type="date">`, required, pre-populated with the existing date
    - `description` — text input, optional, max 200 chars, pre-populated
  - Submit button ("Save Changes") and a cancel link back to `/profile`
  - Display flash/error message when validation fails, re-populating previously submitted values
- **Modify**: `templates/profile.html`
  - Add an "Edit" link/button on each row in the transaction table pointing to `/expenses/<id>/edit`

## Files to change
- `app.py`
  - Replace the GET-only stub at `/expenses/<int:id>/edit` with a GET+POST handler:
    - GET: fetch the expense by ID; 404 if not found; 403 if `expense["user_id"] != session["user_id"]`; render `edit_expense.html` with expense data
    - POST: read form fields, validate, call `update_expense`, redirect to `/profile`
  - Import `get_expense_by_id` from `database.db` (already defined there)
  - Import `abort` from `flask`
- `templates/profile.html` — add Edit link on each transaction row

## Files to create
- `templates/edit_expense.html` — the edit-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Unauthenticated access to GET and POST must redirect to `/login`
- Ownership check: if the expense's `user_id` does not match `session["user_id"]`, return 403 (use `abort(403)`)
- If the expense ID does not exist, return 404 (use `abort(404)`)
- Validation rules for POST (same as add-expense):
  - `title`: required, strip whitespace, max 100 characters
  - `amount`: required, must be a positive number greater than 0
  - `category`: required, must be one of the 7 fixed categories
  - `date`: required, must be a valid `YYYY-MM-DD` date
  - `description`: optional; strip whitespace; store `None` if blank; max 200 chars if provided
  - On any validation error, re-render the form with the error message and the previously submitted values pre-filled
- After successful update, redirect to `url_for("profile")` — do NOT render the form again
- Use `get_expense_by_id` from `database.db` (already implemented) — do not duplicate the query
- Use `update_expense` from `database.db` (already implemented) — do not duplicate the query
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $
- `VALID_CATEGORIES` is already defined in `app.py` — reuse it, do not redefine

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for a non-existent ID returns 404
- [ ] Visiting `/expenses/<id>/edit` for an expense owned by another user returns 403
- [ ] Visiting `/expenses/<id>/edit` while logged in shows a pre-populated form with the expense's current values
- [ ] The category dropdown pre-selects the current category
- [ ] Submitting valid changes redirects to `/profile` and the updated values appear in the transaction list
- [ ] Submitting with a missing or zero amount re-renders the form with an error
- [ ] Submitting with an invalid category re-renders the form with an error
- [ ] Submitting with an invalid date re-renders the form with an error
- [ ] Each row in the profile transaction table has an Edit link pointing to `/expenses/<id>/edit`
