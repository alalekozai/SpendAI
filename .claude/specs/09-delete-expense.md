# Spec: Delete Expense

## Overview
Step 9 lets a logged-in user delete one of their own expenses directly from the
profile page transaction table. A POST-only route at `/expenses/<id>/delete` handles
the deletion. Because deleting is irreversible, the UI presents a confirmation
step — a small inline confirmation dialog or a JavaScript `confirm()` prompt —
before the form is submitted. The existing `delete_expense` helper in
`database/db.py` is reused. After a successful delete the user is redirected back
to the profile page with a flash confirmation message.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` is set and checked)
- Step 5: Profile page routes exist and serve as the redirect target
- Step 8: Edit Expense (establishes Edit links on transaction rows; Delete link goes alongside them)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense and redirect to `/profile` — logged-in only

## Database changes
No database changes. `delete_expense(expense_id)` in `database/db.py` already handles the DELETE query.

## Templates
- **Create:** None
- **Modify:** `templates/profile.html`
  - Add a **Delete** button/link next to the existing Edit link in the Actions column of the transaction table
  - The Delete button must submit a small `<form method="POST">` to `/expenses/<id>/delete` (no GET — browsers must not trigger deletion via link)
  - Add a JavaScript `confirm()` call (via `onclick`) so the user must confirm before the form submits

## Files to change
- `app.py`
  - Replace the GET stub at `/expenses/<int:id>/delete` with a POST-only handler:
    - Redirect to `/login` if not authenticated
    - Fetch expense by ID; `abort(404)` if not found
    - `abort(403)` if `expense["user_id"] != session["user_id"]`
    - Call `delete_expense(id)`, flash "Expense deleted.", redirect to `url_for("profile")`
  - Add `delete_expense` to the `database.db` import (alongside the existing `get_expense_by_id`, `update_expense`)
- `templates/profile.html` — add Delete form+button in the Actions column next to the Edit link

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- The delete route must accept **POST only** — decorate with `methods=["POST"]`; a GET to this URL should return 405
- Unauthenticated access must redirect to `/login`
- Ownership check: if the expense's `user_id` does not match `session["user_id"]`, return 403 (`abort(403)`)
- If the expense ID does not exist, return 404 (`abort(404)`)
- The Delete button in the template must be wrapped in a `<form method="POST">` — never use a plain `<a>` tag for a destructive action
- Use a JavaScript `confirm()` in the form's `onsubmit` (or button's `onclick`) to require user confirmation before submitting
- Use `delete_expense` from `database/db.py` — do not reimplement the query
- Use CSS variables — never hardcode hex values
- No inline styles
- All templates extend `base.html`
- Currency must always display as ₹ — never £ or $

## Definition of done
- [ ] Visiting `POST /expenses/<id>/delete` while logged out redirects to `/login`
- [ ] A GET request to `/expenses/<id>/delete` returns 405
- [ ] `POST /expenses/<id>/delete` for a non-existent ID returns 404
- [ ] `POST /expenses/<id>/delete` for an expense owned by another user returns 403
- [ ] Each row in the profile transaction table has a Delete button next to the Edit link
- [ ] Clicking Delete triggers a browser confirmation dialog before submitting
- [ ] Cancelling the confirmation leaves the expense untouched
- [ ] Confirming the deletion removes the expense and redirects to `/profile` with a success flash message
- [ ] The deleted expense no longer appears in the transaction list after deletion
