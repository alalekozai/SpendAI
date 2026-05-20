"""
tests/test_delete_expense.py

Pytest tests for the Spendly "Delete Expense" feature (Step 9).

All test logic is derived from the spec in .claude/specs/09-delete-expense.md.

Tests cover:
  - Auth guard: unauthenticated POST redirects to /login
  - HTTP method guard: GET returns 405 Method Not Allowed
  - Happy path: owned expense is deleted → 302 to /profile, row gone from DB
  - Flash message: "Expense deleted." appears in the profile page after deletion
  - 404: POST to non-existent expense ID
  - 403: POST to expense owned by a different user
  - 403 DB side effect: the expense row is NOT removed when a 403 is returned
  - Template: profile page transaction rows include a POST form targeting the
    delete route with a JavaScript confirm() call

Key design decisions:
  - The route calls get_db() (via database.db) on every helper invocation.
    To avoid "Cannot operate on a closed database" errors from a shared
    in-memory connection being closed by the first helper, we use a temp-file
    DB and patch get_db with a factory that opens a fresh connection to the
    same file on every call.
  - Both database.db.get_db and database.queries.get_db are patched together
    so the route helpers (get_expense_by_id, delete_expense) and query helpers
    (get_user_by_id, get_summary_stats, etc.) all read from our temp-file DB.
  - Session injection uses client.session_transaction() — no real login needed.
"""

import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
    CREATE TABLE users (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        email      TEXT    NOT NULL UNIQUE,
        password   TEXT    NOT NULL,
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE expenses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        title       TEXT    NOT NULL,
        amount      REAL    NOT NULL,
        category    TEXT    NOT NULL,
        date        TEXT    NOT NULL,
        description TEXT
    );
"""


# ---------------------------------------------------------------------------
# Temp-file DB helpers
# ---------------------------------------------------------------------------

def _open_conn(path):
    """Open a fresh connection to the temp-file DB with row_factory set."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _build_db_with_two_users():
    """
    Create a temp-file SQLite DB containing two users and one expense owned
    by user 1.

    Returns (path, user1_id, user2_id, expense_id).
    Caller must delete the file when done.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = _open_conn(path)
    conn.executescript(_SCHEMA)

    # User 1 — the expense owner
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        (
            "Alice Owner",
            "alice@example.com",
            generate_password_hash("alicepass", method="pbkdf2:sha256"),
            "2026-01-01 00:00:00",
        ),
    )
    user1_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # User 2 — a different user who does NOT own the expense
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        (
            "Bob Other",
            "bob@example.com",
            generate_password_hash("bobpass", method="pbkdf2:sha256"),
            "2026-01-02 00:00:00",
        ),
    )
    user2_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # One expense belonging to user 1
    conn.execute(
        "INSERT INTO expenses (user_id, title, amount, category, date, description)"
        " VALUES (?,?,?,?,?,?)",
        (user1_id, "Lunch", 150.00, "Food", "2026-04-10", "Office lunch"),
    )
    expense_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.commit()
    conn.close()
    return path, user1_id, user2_id, expense_id


# ---------------------------------------------------------------------------
# get_db factory — opens a fresh connection on every call
# ---------------------------------------------------------------------------

def _make_db_factory(db_path):
    """Return a callable that opens a fresh connection to db_path each time."""
    def factory():
        return _open_conn(db_path)
    return factory


# ---------------------------------------------------------------------------
# Request helper
# ---------------------------------------------------------------------------

def _post_delete(client, db_path, user_id, expense_id):
    """
    POST /expenses/<expense_id>/delete with session["user_id"] = user_id.
    Patches both database.db.get_db and database.queries.get_db so every
    helper (get_expense_by_id, delete_expense, get_user_by_id, etc.) reads
    from the temp-file DB.
    """
    factory = _make_db_factory(db_path)
    with patch("database.db.get_db", side_effect=factory), \
         patch("database.queries.get_db", side_effect=factory):
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        return client.post(f"/expenses/{expense_id}/delete")


def _get_profile_patched(client, db_path, user_id):
    """
    GET /profile with session["user_id"] set, patching both get_db modules.
    Used to verify template rendering after a successful delete.
    """
    factory = _make_db_factory(db_path)
    with patch("database.db.get_db", side_effect=factory), \
         patch("database.queries.get_db", side_effect=factory):
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        return client.get("/profile")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    return flask_app.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db():
    """
    Yields (db_path, user1_id, user2_id, expense_id).
    expense_id belongs to user1_id. user2_id has no expenses.
    """
    path, user1_id, user2_id, expense_id = _build_db_with_two_users()
    yield path, user1_id, user2_id, expense_id
    os.unlink(path)


# ---------------------------------------------------------------------------
# 1. Auth guard — unauthenticated POST
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_post_redirects_to_login(self, client, db):
        """POST /expenses/<id>/delete without a session must redirect to /login (302)."""
        db_path, user1_id, user2_id, expense_id = db
        factory = _make_db_factory(db_path)
        with patch("database.db.get_db", side_effect=factory), \
             patch("database.queries.get_db", side_effect=factory):
            resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302, (
            f"Expected 302 redirect for unauthenticated POST but got {resp.status_code}"
        )
        assert "/login" in resp.headers["Location"], (
            f"Expected redirect to /login but got {resp.headers['Location']}"
        )

    def test_unauthenticated_post_does_not_delete_expense(self, client, db):
        """An unauthenticated POST must not remove the expense from the DB."""
        db_path, user1_id, user2_id, expense_id = db
        factory = _make_db_factory(db_path)
        with patch("database.db.get_db", side_effect=factory), \
             patch("database.queries.get_db", side_effect=factory):
            client.post(f"/expenses/{expense_id}/delete")

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row is not None, (
            "Expense must NOT be deleted when the request is unauthenticated"
        )


# ---------------------------------------------------------------------------
# 2. HTTP method guard — GET returns 405
# ---------------------------------------------------------------------------

class TestHttpMethodGuard:
    def test_get_request_returns_405(self, client, db):
        """GET /expenses/<id>/delete must return 405 Method Not Allowed."""
        db_path, user1_id, user2_id, expense_id = db
        factory = _make_db_factory(db_path)
        with patch("database.db.get_db", side_effect=factory), \
             patch("database.queries.get_db", side_effect=factory):
            with client.session_transaction() as sess:
                sess["user_id"] = user1_id
            resp = client.get(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 405, (
            f"Expected 405 for GET on delete route but got {resp.status_code}"
        )

    def test_put_request_returns_405(self, client, db):
        """PUT /expenses/<id>/delete must also return 405 (only POST is allowed)."""
        db_path, user1_id, user2_id, expense_id = db
        factory = _make_db_factory(db_path)
        with patch("database.db.get_db", side_effect=factory), \
             patch("database.queries.get_db", side_effect=factory):
            with client.session_transaction() as sess:
                sess["user_id"] = user1_id
            resp = client.put(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 405, (
            f"Expected 405 for PUT on delete route but got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 3. 404 — non-existent expense ID
# ---------------------------------------------------------------------------

class TestNotFound:
    def test_post_nonexistent_id_returns_404(self, client, db):
        """POST to a delete URL with a non-existent ID must return 404."""
        db_path, user1_id, user2_id, expense_id = db
        nonexistent_id = 99999
        resp = _post_delete(client, db_path, user1_id, nonexistent_id)
        assert resp.status_code == 404, (
            f"Expected 404 for non-existent expense ID but got {resp.status_code}"
        )

    def test_post_zero_id_returns_404(self, client, db):
        """POST to /expenses/0/delete (ID that can never exist) must return 404."""
        db_path, user1_id, user2_id, expense_id = db
        resp = _post_delete(client, db_path, user1_id, 0)
        # Flask converts /expenses/0/delete fine as an int route; the DB lookup
        # will find nothing, so the route must abort(404).
        assert resp.status_code == 404, (
            f"Expected 404 for expense ID 0 but got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 4. 403 — expense owned by a different user
# ---------------------------------------------------------------------------

class TestForbidden:
    def test_post_by_other_user_returns_403(self, client, db):
        """POST by user2 to delete user1's expense must return 403."""
        db_path, user1_id, user2_id, expense_id = db
        resp = _post_delete(client, db_path, user2_id, expense_id)
        assert resp.status_code == 403, (
            f"Expected 403 when user2 tries to delete user1's expense but got {resp.status_code}"
        )

    def test_post_by_other_user_does_not_delete_expense(self, client, db):
        """When 403 is returned the expense row must still exist in the DB."""
        db_path, user1_id, user2_id, expense_id = db
        _post_delete(client, db_path, user2_id, expense_id)

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row is not None, (
            "Expense must NOT be deleted when a different user attempts to delete it"
        )


# ---------------------------------------------------------------------------
# 5. Happy path — successful deletion
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_owner_delete_redirects_to_profile(self, client, db):
        """Authenticated owner POST must redirect to /profile (302)."""
        db_path, user1_id, user2_id, expense_id = db
        resp = _post_delete(client, db_path, user1_id, expense_id)
        assert resp.status_code == 302, (
            f"Expected 302 redirect after successful delete but got {resp.status_code}"
        )
        assert "/profile" in resp.headers["Location"], (
            f"Expected redirect to /profile but got {resp.headers['Location']}"
        )

    def test_owner_delete_removes_row_from_db(self, client, db):
        """After a successful delete the expense row must be gone from the DB."""
        db_path, user1_id, user2_id, expense_id = db
        _post_delete(client, db_path, user1_id, expense_id)

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert row is None, (
            "Expected the expense row to be deleted from the DB after a successful POST"
        )

    def test_owner_delete_does_not_remove_other_rows(self, client, db):
        """Deleting one expense must not remove other rows in the expenses table."""
        db_path, user1_id, user2_id, expense_id = db

        # Insert a second expense for user1 that should survive the delete
        conn = _open_conn(db_path)
        conn.execute(
            "INSERT INTO expenses (user_id, title, amount, category, date, description)"
            " VALUES (?,?,?,?,?,?)",
            (user1_id, "Coffee", 80.00, "Food", "2026-04-11", "Morning coffee"),
        )
        conn.commit()
        second_expense_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        # Delete only the first expense
        _post_delete(client, db_path, user1_id, expense_id)

        conn = _open_conn(db_path)
        surviving = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (second_expense_id,)
        ).fetchone()
        conn.close()
        assert surviving is not None, (
            "The second expense must NOT be affected when a different expense is deleted"
        )

    def test_delete_twice_returns_404_on_second_attempt(self, client, db):
        """
        Posting to the same delete URL twice must return 404 on the second
        request because the expense no longer exists after the first deletion.
        """
        db_path, user1_id, user2_id, expense_id = db
        # First delete — should succeed
        first = _post_delete(client, db_path, user1_id, expense_id)
        assert first.status_code == 302, (
            f"Expected 302 on first delete but got {first.status_code}"
        )
        # Second delete — expense is gone, must return 404
        second = _post_delete(client, db_path, user1_id, expense_id)
        assert second.status_code == 404, (
            f"Expected 404 on second delete attempt (already deleted) but got {second.status_code}"
        )


# ---------------------------------------------------------------------------
# 6. Flash message — "Expense deleted." appears after redirect
# ---------------------------------------------------------------------------

class TestFlashMessage:
    def test_success_flash_message_present_after_redirect(self, client, db):
        """
        After a successful delete the user is redirected to /profile.
        Following the redirect must show the flash message "Expense deleted.".
        """
        db_path, user1_id, user2_id, expense_id = db
        factory = _make_db_factory(db_path)
        with patch("database.db.get_db", side_effect=factory), \
             patch("database.queries.get_db", side_effect=factory):
            with client.session_transaction() as sess:
                sess["user_id"] = user1_id
            # follow_redirects=True renders the /profile page the flash lands on
            resp = client.post(
                f"/expenses/{expense_id}/delete",
                follow_redirects=True,
            )
        assert b"Expense deleted." in resp.data, (
            "Expected flash message 'Expense deleted.' to appear on the profile page "
            "after a successful deletion"
        )

    def test_success_flash_message_exact_text(self, client, db):
        """
        The spec mandates the exact flash text 'Expense deleted.' (with period).
        """
        db_path, user1_id, user2_id, expense_id = db
        factory = _make_db_factory(db_path)
        with patch("database.db.get_db", side_effect=factory), \
             patch("database.queries.get_db", side_effect=factory):
            with client.session_transaction() as sess:
                sess["user_id"] = user1_id
            resp = client.post(
                f"/expenses/{expense_id}/delete",
                follow_redirects=True,
            )
        assert b"Expense deleted." in resp.data, (
            "Flash message must be exactly 'Expense deleted.' (capital E, period at end)"
        )


# ---------------------------------------------------------------------------
# 7. Template — delete form + confirm() on profile page
# ---------------------------------------------------------------------------

class TestProfileTemplate:
    def test_profile_transaction_row_has_delete_form_with_post_method(self, client, db):
        """
        The profile page must contain a <form method="POST"> targeting the
        delete URL for each transaction row. Using a plain <a> tag for a
        destructive action is forbidden by the spec.
        """
        db_path, user1_id, user2_id, expense_id = db
        resp = _get_profile_patched(client, db_path, user1_id)
        assert resp.status_code == 200, (
            f"Expected 200 loading profile but got {resp.status_code}"
        )
        body = resp.data.lower()
        # The form must use method="post" (case-insensitive check)
        assert b'method="post"' in body or b"method='post'" in body, (
            "Expected a <form method=\"POST\"> for the delete action in the "
            "transaction table — a plain <a> tag must not be used for deletion"
        )

    def test_profile_transaction_row_delete_form_action_contains_delete_url(self, client, db):
        """
        The delete form's action attribute must contain the /delete path for
        the expense's ID.
        """
        db_path, user1_id, user2_id, expense_id = db
        resp = _get_profile_patched(client, db_path, user1_id)
        delete_url_fragment = f"/expenses/{expense_id}/delete".encode()
        assert delete_url_fragment in resp.data, (
            f"Expected the profile page to contain a form action pointing to "
            f"'/expenses/{expense_id}/delete'"
        )

    def test_profile_transaction_row_has_confirm_dialog(self, client, db):
        """
        Each delete form or its submit button must include a JavaScript
        confirm() call (via onsubmit or onclick) so the user must confirm
        before the form is actually submitted.
        """
        db_path, user1_id, user2_id, expense_id = db
        resp = _get_profile_patched(client, db_path, user1_id)
        # The spec says: use confirm() in the form's onsubmit (or button's onclick)
        assert b"confirm(" in resp.data, (
            "Expected a JavaScript confirm() call on the delete form or button "
            "to prevent accidental deletion"
        )

    def test_profile_transaction_row_has_delete_button(self, client, db):
        """
        The transaction table must include a Delete button (or element with
        'Delete' text) alongside the Edit link for each expense row.
        """
        db_path, user1_id, user2_id, expense_id = db
        resp = _get_profile_patched(client, db_path, user1_id)
        assert b"Delete" in resp.data, (
            "Expected a 'Delete' button text in the profile transaction table"
        )

    def test_profile_transaction_row_has_edit_link(self, client, db):
        """
        The Edit link must still be present alongside the new Delete button —
        adding Delete must not remove the Edit link.
        """
        db_path, user1_id, user2_id, expense_id = db
        resp = _get_profile_patched(client, db_path, user1_id)
        assert b"Edit" in resp.data, (
            "Expected the Edit link to still be present in the transaction row "
            "alongside the new Delete button"
        )

    def test_profile_no_transactions_no_delete_form(self, client, db):
        """
        When a user has no expenses the profile page must render without any
        delete form (no expense rows to show).
        """
        _, _, user2_id, _ = db
        # Build a separate empty DB for user2 so there are no expenses
        fd, empty_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = _open_conn(empty_path)
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
                (
                    "Empty User",
                    "empty@example.com",
                    generate_password_hash("emptypass", method="pbkdf2:sha256"),
                    "2026-01-01 00:00:00",
                ),
            )
            conn.commit()
            empty_user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()

            resp = _get_profile_patched(client, empty_path, empty_user_id)
            assert resp.status_code == 200, (
                f"Expected 200 on profile for a user with no expenses but got {resp.status_code}"
            )
            # There are no transaction rows, so no delete form should point to any expense
            assert b"/delete" not in resp.data, (
                "Expected no delete form action URL when the user has no expenses"
            )
        finally:
            os.unlink(empty_path)


# ---------------------------------------------------------------------------
# 8. Ownership isolation — parametrized
# ---------------------------------------------------------------------------

class TestOwnershipIsolation:
    @pytest.mark.parametrize("attacker_offset", [1, 2, 5, 100])
    def test_any_other_user_id_is_rejected_with_403(self, client, db, attacker_offset):
        """
        Any session user_id that differs from expense["user_id"] must result
        in 403, regardless of how far apart the IDs are.
        """
        db_path, user1_id, user2_id, expense_id = db
        # Use user1_id + offset as the "attacker"; it may or may not exist in
        # the DB, but the ownership check runs before any user lookup.
        fake_user_id = user1_id + attacker_offset
        resp = _post_delete(client, db_path, fake_user_id, expense_id)
        assert resp.status_code == 403, (
            f"Expected 403 when user_id={fake_user_id} tries to delete expense "
            f"owned by user_id={user1_id} but got {resp.status_code}"
        )
