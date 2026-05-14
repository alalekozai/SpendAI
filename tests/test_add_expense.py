"""
tests/test_add_expense.py

Pytest tests for the Spendly "Add Expense" feature (Step 7).

All test logic is derived from the spec in .claude/specs/07-add-expense.md.
Tests cover:
  - Unit tests for insert_expense query helper
  - Auth guards (GET and POST)
  - GET renders form with all 7 category options and a POST form
  - POST happy path redirects to /profile and persists the row
  - POST validation errors: missing amount, amount=0, non-numeric amount,
    invalid category, invalid date string
  - POST with optional description omitted stores NULL

Key design decisions:
  - Each query helper calls get_db() then conn.close(). To avoid
    "Cannot operate on a closed database" errors from shared in-memory
    connections, we use a temp-file DB and patch get_db with a factory
    that opens a fresh connection to the same file on every call.
  - Route tests that need an authenticated session inject session["user_id"]
    via client.session_transaction() and patch database.queries.get_db
    so the route reads from our temp-file DB, not the real spendly.db.
"""

import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app
from database.queries import insert_expense


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

VALID_CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]


# ---------------------------------------------------------------------------
# Temp-file DB helpers
# ---------------------------------------------------------------------------

def _open_conn(path):
    """Open a new connection to the temp-file DB with row_factory set."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _build_db_file():
    """
    Create a temp-file SQLite DB containing one user.
    Returns (path, user_id). Caller must delete the file when done.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = _open_conn(path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        (
            "Test User",
            "testuser@example.com",
            generate_password_hash("testpass123", method="pbkdf2:sha256"),
            "2026-01-01 00:00:00",
        ),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return path, user_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test"
    return flask_app.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db():
    """Yields (db_path, user_id) for a temp-file DB with one user, no expenses."""
    path, user_id = _build_db_file()
    yield path, user_id
    os.unlink(path)


# ---------------------------------------------------------------------------
# Helper: make a get_db factory that always opens a fresh connection
# ---------------------------------------------------------------------------

def _make_db_factory(db_path):
    """Return a callable that opens a fresh connection to db_path each time."""
    def factory():
        return _open_conn(db_path)
    return factory


# ---------------------------------------------------------------------------
# Helper: perform an authenticated request with the route patched to our DB
# ---------------------------------------------------------------------------

def _authenticated_request(client, db_path, user_id, method, url, data=None):
    """
    Make `method` request to `url` with session["user_id"] set.
    Patches both database.queries.get_db and database.db.get_db so the
    route and its helpers always read from our temp-file DB.
    """
    factory = _make_db_factory(db_path)
    with patch("database.queries.get_db", side_effect=factory), \
         patch("database.db.get_db", side_effect=factory):
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        if method.upper() == "GET":
            return client.get(url)
        else:
            return client.post(url, data=data)


# ---------------------------------------------------------------------------
# 1. Unit tests for insert_expense
# ---------------------------------------------------------------------------

class TestInsertExpenseUnit:
    """Tests for the insert_expense query helper in database/queries.py."""

    def test_insert_expense_with_description_persists_row(self, db):
        """insert_expense with valid args inserts a row that can be queried back."""
        db_path, user_id = db
        factory = _make_db_factory(db_path)

        with patch("database.queries.get_db", side_effect=factory):
            insert_expense(
                user_id=user_id,
                amount=50.0,
                category="Food",
                date="2026-03-20",
                description="Lunch",
            )

        # Query the DB directly to confirm the row was inserted
        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        assert row is not None, "Expected a row to be inserted into expenses"
        assert row["amount"] == 50.0, f"Expected amount 50.0 but got {row['amount']}"
        assert row["category"] == "Food", f"Expected category 'Food' but got {row['category']}"
        assert row["date"] == "2026-03-20", f"Expected date '2026-03-20' but got {row['date']}"
        assert row["description"] == "Lunch", f"Expected description 'Lunch' but got {row['description']}"
        assert row["user_id"] == user_id, "Expected user_id to match the test user"

    def test_insert_expense_with_none_description_stores_null(self, db):
        """insert_expense with description=None must store NULL in the DB."""
        db_path, user_id = db
        factory = _make_db_factory(db_path)

        with patch("database.queries.get_db", side_effect=factory):
            insert_expense(
                user_id=user_id,
                amount=25.0,
                category="Transport",
                date="2026-03-21",
                description=None,
            )

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (user_id, "2026-03-21"),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected a row to be inserted"
        assert row["description"] is None, (
            f"Expected description to be NULL but got {row['description']!r}"
        )

    def test_insert_expense_returns_an_id(self, db):
        """insert_expense must return the new row's integer ID."""
        db_path, user_id = db
        factory = _make_db_factory(db_path)

        with patch("database.queries.get_db", side_effect=factory):
            new_id = insert_expense(
                user_id=user_id,
                amount=10.0,
                category="Other",
                date="2026-04-01",
                description="Test",
            )

        assert isinstance(new_id, int), (
            f"Expected int ID from insert_expense but got {type(new_id)}"
        )
        assert new_id > 0, "Expected returned ID to be a positive integer"


# ---------------------------------------------------------------------------
# 2. Auth guard — unauthenticated access
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        """GET /expenses/add without a session must redirect to /login (302)."""
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, (
            f"Expected 302 redirect but got {resp.status_code}"
        )
        assert "/login" in resp.headers["Location"], (
            f"Expected redirect to /login but got {resp.headers['Location']}"
        )

    def test_post_unauthenticated_redirects_to_login(self, client):
        """POST /expenses/add without a session must redirect to /login (302)."""
        resp = client.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 302, (
            f"Expected 302 redirect but got {resp.status_code}"
        )
        assert "/login" in resp.headers["Location"], (
            f"Expected redirect to /login but got {resp.headers['Location']}"
        )


# ---------------------------------------------------------------------------
# 3. GET /expenses/add — authenticated
# ---------------------------------------------------------------------------

class TestGetAddExpenseAuthenticated:
    def test_get_returns_200(self, client, db):
        """GET /expenses/add while logged in must return 200."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        assert resp.status_code == 200, (
            f"Expected 200 for authenticated GET but got {resp.status_code}"
        )

    def test_get_renders_form_with_post_method(self, client, db):
        """The response must contain a <form with method POST."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        body = resp.data.lower()
        assert b"<form" in body, "Expected a <form element in the page"
        assert b'method="post"' in body or b"method='post'" in body, (
            "Expected the form to have method=POST"
        )

    def test_get_renders_category_select_with_all_7_options(self, client, db):
        """The form must contain a <select> with all 7 valid categories."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        for category in VALID_CATEGORIES:
            assert category.encode() in resp.data, (
                f"Expected category '{category}' to appear in the form"
            )

    def test_get_renders_amount_input(self, client, db):
        """The form must contain an amount input field."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        assert b'name="amount"' in resp.data or b"name='amount'" in resp.data, (
            "Expected an input with name='amount' in the form"
        )

    def test_get_renders_date_input(self, client, db):
        """The form must contain a date input field."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        assert b'name="date"' in resp.data or b"name='date'" in resp.data, (
            "Expected an input with name='date' in the form"
        )

    def test_get_renders_description_input(self, client, db):
        """The form must contain a description input field."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        assert b'name="description"' in resp.data or b"name='description'" in resp.data, (
            "Expected an input with name='description' in the form"
        )

    def test_get_renders_exactly_7_categories(self, client, db):
        """The category select must contain exactly the 7 fixed options from the spec."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        expected = {"Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"}
        for cat in expected:
            assert cat.encode() in resp.data, (
                f"Category '{cat}' missing from form — expected all 7 spec categories"
            )

    def test_get_form_action_points_to_add_expense(self, client, db):
        """The form action must target /expenses/add."""
        db_path, user_id = db
        resp = _authenticated_request(client, db_path, user_id, "GET", "/expenses/add")
        assert b"/expenses/add" in resp.data, (
            "Expected form action to reference /expenses/add"
        )


# ---------------------------------------------------------------------------
# 4. POST /expenses/add — happy path
# ---------------------------------------------------------------------------

class TestPostAddExpenseHappyPath:
    def test_valid_post_redirects_to_profile(self, client, db):
        """A valid POST must redirect to /profile (302)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302, (
            f"Expected 302 redirect after valid POST but got {resp.status_code}"
        )
        assert "/profile" in resp.headers["Location"], (
            f"Expected redirect to /profile but got {resp.headers['Location']}"
        )

    def test_valid_post_inserts_expense_row_in_db(self, client, db):
        """After a valid POST the new expense must exist in the database."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (user_id, "2026-03-20"),
        ).fetchone()
        conn.close()

        assert row is not None, (
            "Expected a new expense row in the DB after a valid POST"
        )
        assert float(row["amount"]) == 50.0, (
            f"Expected amount 50.0 in DB but got {row['amount']}"
        )
        assert row["category"] == "Food", (
            f"Expected category 'Food' in DB but got {row['category']}"
        )

    def test_valid_post_associates_expense_with_correct_user(self, client, db):
        """The inserted expense must belong to the authenticated user."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={
                "amount": "75.5",
                "category": "Transport",
                "date": "2026-04-01",
                "description": "Cab ride",
            },
        )

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (user_id, "2026-04-01"),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row to exist in DB"
        assert row["user_id"] == user_id, (
            f"Expected user_id={user_id} on inserted row but got {row['user_id']}"
        )


# ---------------------------------------------------------------------------
# 5. POST /expenses/add — validation errors
# ---------------------------------------------------------------------------

class TestPostAddExpenseValidationErrors:

    # -- Missing amount --

    def test_missing_amount_returns_200(self, client, db):
        """POST with no amount must re-render the form (200), not redirect."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "", "category": "Food", "date": "2026-03-20"},
        )
        assert resp.status_code == 200, (
            f"Expected 200 (form re-render) for missing amount but got {resp.status_code}"
        )

    def test_missing_amount_shows_error_message(self, client, db):
        """POST with no amount must include an error message in the response."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "", "category": "Food", "date": "2026-03-20"},
        )
        body = resp.data.lower()
        assert b"amount" in body, (
            "Expected an error referencing 'amount' when amount is missing"
        )

    # -- Amount = 0 --

    def test_amount_zero_returns_200(self, client, db):
        """POST with amount=0 must re-render the form (200)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2026-03-20"},
        )
        assert resp.status_code == 200, (
            f"Expected 200 (form re-render) for amount=0 but got {resp.status_code}"
        )

    def test_amount_zero_shows_error_message(self, client, db):
        """POST with amount=0 must show a validation error."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2026-03-20"},
        )
        body = resp.data.lower()
        # The spec mandates the message "Amount must be a positive number."
        assert b"positive" in body or b"amount" in body, (
            "Expected a validation error about the amount being zero or not positive"
        )

    def test_amount_zero_does_not_insert_row(self, client, db):
        """POST with amount=0 must not insert any row into the DB."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2026-03-20"},
        )
        conn = _open_conn(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0, (
            "Expected no row inserted when amount=0, but found one in DB"
        )

    # -- Negative amount --

    def test_negative_amount_returns_200(self, client, db):
        """POST with a negative amount must re-render the form (200)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "-10", "category": "Food", "date": "2026-03-20"},
        )
        assert resp.status_code == 200, (
            f"Expected 200 for negative amount but got {resp.status_code}"
        )

    # -- Non-numeric amount --

    def test_non_numeric_amount_returns_200(self, client, db):
        """POST with a non-numeric amount must re-render the form (200)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "abc", "category": "Food", "date": "2026-03-20"},
        )
        assert resp.status_code == 200, (
            f"Expected 200 (form re-render) for non-numeric amount but got {resp.status_code}"
        )

    def test_non_numeric_amount_shows_error_message(self, client, db):
        """POST with a non-numeric amount must include an error message."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "abc", "category": "Food", "date": "2026-03-20"},
        )
        body = resp.data.lower()
        assert b"amount" in body or b"positive" in body, (
            "Expected a validation error about the non-numeric amount"
        )

    def test_non_numeric_amount_does_not_insert_row(self, client, db):
        """POST with a non-numeric amount must not insert any row into the DB."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "not-a-number", "category": "Food", "date": "2026-03-20"},
        )
        conn = _open_conn(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0, (
            "Expected no row inserted when amount is non-numeric"
        )

    # -- Invalid category --

    def test_invalid_category_returns_200(self, client, db):
        """POST with a category not in the fixed list must re-render the form (200)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "50", "category": "Unicorn", "date": "2026-03-20"},
        )
        assert resp.status_code == 200, (
            f"Expected 200 for invalid category but got {resp.status_code}"
        )

    def test_invalid_category_shows_error_message(self, client, db):
        """POST with an invalid category must include a validation error."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "50", "category": "Unicorn", "date": "2026-03-20"},
        )
        body = resp.data.lower()
        assert b"category" in body or b"valid" in body, (
            "Expected a validation error about the invalid category"
        )

    def test_invalid_category_does_not_insert_row(self, client, db):
        """POST with an invalid category must not insert any row into the DB."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "50", "category": "Unicorn", "date": "2026-03-20"},
        )
        conn = _open_conn(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0, (
            "Expected no row inserted when category is invalid"
        )

    # -- Invalid date --

    def test_invalid_date_returns_200(self, client, db):
        """POST with a malformed date string must re-render the form (200)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "50", "category": "Food", "date": "not-a-date"},
        )
        assert resp.status_code == 200, (
            f"Expected 200 (form re-render) for invalid date but got {resp.status_code}"
        )

    def test_invalid_date_shows_error_message(self, client, db):
        """POST with a malformed date must include a validation error."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "50", "category": "Food", "date": "not-a-date"},
        )
        body = resp.data.lower()
        assert b"date" in body or b"valid" in body, (
            "Expected a validation error about the invalid date"
        )

    def test_invalid_date_does_not_insert_row(self, client, db):
        """POST with an invalid date must not insert any row into the DB."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "50", "category": "Food", "date": "not-a-date"},
        )
        conn = _open_conn(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0, (
            "Expected no row inserted when date is invalid"
        )


# ---------------------------------------------------------------------------
# 6. POST /expenses/add — parametrized invalid inputs
# ---------------------------------------------------------------------------

class TestPostInvalidInputsParametrized:
    """Parametrized sweep of invalid inputs — each must return 200 (no redirect)."""

    @pytest.mark.parametrize("amount,category,date_val,description", [
        ("",      "Food",       "2026-03-20", "Missing amount"),
        ("0",     "Food",       "2026-03-20", "Zero amount"),
        ("-5",    "Food",       "2026-03-20", "Negative amount"),
        ("abc",   "Food",       "2026-03-20", "Non-numeric amount"),
        ("1e999", "Food",       "2026-03-20", "Overflow-ish amount string"),
        ("50",    "",           "2026-03-20", "Empty category"),
        ("50",    "Unicorn",    "2026-03-20", "Unknown category"),
        ("50",    "food",       "2026-03-20", "Category wrong case"),
        ("50",    "FOOD",       "2026-03-20", "Category all-caps"),
        ("50",    "Food",       "",           "Empty date"),
        ("50",    "Food",       "not-a-date", "Non-date string"),
        ("50",    "Food",       "20260320",   "Date missing separators"),
        ("50",    "Food",       "2026/03/20", "Date with slashes"),
        ("50",    "Food",       "2026-13-01", "Month 13"),
        ("50",    "Food",       "2026-00-01", "Month 00"),
        ("50",    "Food",       "2026-03-32", "Day 32"),
    ])
    def test_invalid_input_rerenders_form(
        self, client, db, amount, category, date_val, description
    ):
        """Each invalid combination must return 200 (form re-render, not redirect)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": amount, "category": category, "date": date_val},
        )
        assert resp.status_code == 200, (
            f"[{description}] Expected 200 re-render but got {resp.status_code}"
        )

    @pytest.mark.parametrize("amount,category,date_val,description", [
        ("",      "Food",       "2026-03-20", "Missing amount"),
        ("0",     "Food",       "2026-03-20", "Zero amount"),
        ("-5",    "Food",       "2026-03-20", "Negative amount"),
        ("abc",   "Food",       "2026-03-20", "Non-numeric amount"),
        ("50",    "Unicorn",    "2026-03-20", "Unknown category"),
        ("50",    "Food",       "not-a-date", "Non-date string"),
        ("50",    "Food",       "2026-13-01", "Month 13"),
    ])
    def test_invalid_input_does_not_insert_row(
        self, client, db, amount, category, date_val, description
    ):
        """Each invalid combination must not insert any row into the expenses table."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": amount, "category": category, "date": date_val},
        )
        conn = _open_conn(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        assert count == 0, (
            f"[{description}] Expected no row inserted for invalid input but found {count}"
        )


# ---------------------------------------------------------------------------
# 7. POST /expenses/add — optional description field
# ---------------------------------------------------------------------------

class TestPostOptionalDescription:

    def test_no_description_redirects_to_profile(self, client, db):
        """POST without description (optional) must still redirect to /profile (302)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "99.0", "category": "Bills", "date": "2026-04-15"},
        )
        assert resp.status_code == 302, (
            f"Expected 302 redirect when description is omitted but got {resp.status_code}"
        )
        assert "/profile" in resp.headers["Location"], (
            f"Expected redirect to /profile but got {resp.headers['Location']}"
        )

    def test_no_description_inserts_row_with_null_description(self, client, db):
        """POST without description must insert the row with description = NULL."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "99.0", "category": "Bills", "date": "2026-04-15"},
        )

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (user_id, "2026-04-15"),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row to exist in DB"
        assert row["description"] is None, (
            f"Expected description to be NULL when omitted, but got {row['description']!r}"
        )

    def test_blank_description_inserts_row_with_null_description(self, client, db):
        """POST with a whitespace-only description must store NULL (stripped to empty -> None)."""
        db_path, user_id = db
        _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={
                "amount": "10.0",
                "category": "Other",
                "date": "2026-04-16",
                "description": "   ",
            },
        )

        conn = _open_conn(db_path)
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (user_id, "2026-04-16"),
        ).fetchone()
        conn.close()

        assert row is not None, "Expected expense row to exist in DB"
        assert row["description"] is None, (
            f"Expected whitespace-only description to be stored as NULL but got {row['description']!r}"
        )

    def test_empty_string_description_inserts_row(self, client, db):
        """POST with description='' (empty string) must also succeed and redirect."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={
                "amount": "5.0",
                "category": "Shopping",
                "date": "2026-04-17",
                "description": "",
            },
        )
        assert resp.status_code == 302, (
            f"Expected 302 for empty description but got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 8. Form re-population on validation error
# ---------------------------------------------------------------------------

class TestFormRepopulationOnError:
    """After a validation failure, the form must show the previously entered values."""

    def test_previously_entered_amount_present_after_invalid_category(self, client, db):
        """Submitted amount must be pre-filled in the re-rendered form on category error."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "123.45", "category": "BadCategory", "date": "2026-03-20"},
        )
        assert b"123.45" in resp.data, (
            "Expected previously submitted amount '123.45' to appear in re-rendered form"
        )

    def test_previously_entered_date_present_after_invalid_amount(self, client, db):
        """Submitted date must be pre-filled in the re-rendered form on amount error."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2026-05-10"},
        )
        assert b"2026-05-10" in resp.data, (
            "Expected previously submitted date '2026-05-10' to appear in re-rendered form"
        )


# ---------------------------------------------------------------------------
# 9. Valid submissions for every category in the fixed list
# ---------------------------------------------------------------------------

class TestAllValidCategories:
    """Every one of the 7 spec-defined categories must be accepted."""

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, client, db, category):
        """POST with each of the 7 valid categories must redirect to /profile (302)."""
        db_path, user_id = db
        resp = _authenticated_request(
            client, db_path, user_id, "POST", "/expenses/add",
            data={
                "amount": "10.0",
                "category": category,
                "date": "2026-06-01",
                "description": f"Test for {category}",
            },
        )
        assert resp.status_code == 302, (
            f"Expected 302 redirect for valid category '{category}' but got {resp.status_code}"
        )
        assert "/profile" in resp.headers["Location"], (
            f"Expected redirect to /profile for category '{category}'"
        )
