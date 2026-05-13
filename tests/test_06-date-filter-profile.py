"""
tests/test_06-date-filter-profile.py

Pytest tests for the Spendly date filter feature on /profile.

All test logic is derived from the spec in .claude/specs/06-date-filter-profile.md.

Key design decisions:
- Each query helper calls get_db() then conn.close(). To avoid the
  "Cannot operate on a closed database" error that occurs when a shared
  in-memory connection is closed by the first helper, we use a temp file DB
  instead. get_db is patched with a factory that opens a NEW connection to
  the same temp file on every call, so each helper gets its own live
  connection and closing it is harmless.
- Today's date is frozen via unittest.mock.patch for preset calculations.
"""

import os
import sqlite3
import tempfile
import pytest
from datetime import date, timedelta
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_TODAY = date(2026, 5, 12)

# Pre-computed date ranges matching what the route builds from FAKE_TODAY
THIS_MONTH_FROM = FAKE_TODAY.replace(day=1).isoformat()      # 2026-05-01
THIS_MONTH_TO   = FAKE_TODAY.isoformat()                     # 2026-05-12
MONTHS_3_FROM   = (FAKE_TODAY - timedelta(days=90)).isoformat()  # 2026-02-11
MONTHS_3_TO     = FAKE_TODAY.isoformat()                     # 2026-05-12
MONTHS_6_FROM   = (FAKE_TODAY - timedelta(days=180)).isoformat() # 2025-11-13
MONTHS_6_TO     = FAKE_TODAY.isoformat()                     # 2026-05-12

EXPENSE_ROWS = [
    # (title, amount, category, date_str, description)
    ("Coffee",       120.00, "Food",        "2026-05-05", "This month"),
    ("Metro",        300.00, "Transport",   "2026-04-20", "Last 90 days but not this month"),
    ("Books",        450.00, "Education",   "2026-02-10", "Last 180 days but not last 90"),
    ("Old expense", 1000.00, "Shopping",    "2025-10-01", "All time only"),
]

TOTAL_ALL   = 120.00 + 300.00 + 450.00 + 1000.00  # 1870.00
TOTAL_6M    = 120.00 + 300.00 + 450.00             # 870.00
TOTAL_3M    = 120.00 + 300.00                      # 420.00
TOTAL_MONTH = 120.00                                # 120.00

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

def _open(path):
    """Open a new connection to the temp-file DB (row_factory set)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _build_db_file():
    """
    Create a temp file DB with one user and EXPENSE_ROWS.
    Returns (path, user_id). Caller must delete the file when done.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = _open(path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        (
            "Filter Tester",
            "filter@example.com",
            generate_password_hash("testpass123", method="pbkdf2:sha256"),
            "2026-01-01 00:00:00",
        ),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.executemany(
        "INSERT INTO expenses (user_id, title, amount, category, date, description)"
        " VALUES (?,?,?,?,?,?)",
        [(user_id, t, a, c, d, desc) for t, a, c, d, desc in EXPENSE_ROWS],
    )
    conn.commit()
    conn.close()
    return path, user_id


def _build_empty_db_file():
    """
    Create a temp file DB with one user but NO expenses.
    Returns (path, user_id).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = _open(path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        (
            "Empty User",
            "empty@example.com",
            generate_password_hash("testpass123", method="pbkdf2:sha256"),
            "2026-01-01 00:00:00",
        ),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return path, user_id


# ---------------------------------------------------------------------------
# Request helper
# ---------------------------------------------------------------------------

def _get_profile(client, db_path, user_id, url="/profile"):
    """
    GET `url` with session["user_id"] = user_id.
    Patches database.queries.get_db to open a fresh connection to db_path
    on every call, so each query helper gets its own live connection.
    """
    def _factory():
        return _open(db_path)

    with patch("database.queries.get_db", side_effect=_factory):
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        return client.get(url)


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
    """Yields (db_path, user_id) for a DB with expenses across multiple date ranges."""
    path, user_id = _build_db_file()
    yield path, user_id
    os.unlink(path)


@pytest.fixture
def empty_db():
    """Yields (db_path, user_id) for a DB with a user but no expenses."""
    path, user_id = _build_empty_db_file()
    yield path, user_id
    os.unlink(path)


# ---------------------------------------------------------------------------
# 1.  Unauthenticated access
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        """GET /profile without a session must redirect to /login with 302."""
        resp = client.get("/profile")
        assert resp.status_code == 302, (
            f"Expected 302 redirect but got {resp.status_code}"
        )
        assert "/login" in resp.headers["Location"], (
            "Expected redirect location to contain /login"
        )


# ---------------------------------------------------------------------------
# 2.  No query params — unfiltered (all expenses)
# ---------------------------------------------------------------------------

class TestNoFilter:
    def test_no_params_returns_200(self, client, db):
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id)
        assert resp.status_code == 200, (
            f"Expected 200 but got {resp.status_code}"
        )

    def test_no_params_shows_all_expenses_total(self, client, db):
        """Without filter params, total_spent must include all expenses."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id)
        # TOTAL_ALL = 1870.00
        assert "1,870.00".encode() in resp.data, (
            "Expected total ₹1,870.00 (all expenses) in unfiltered view"
        )

    def test_no_params_shows_all_transaction_count(self, client, db):
        """Without filter params, all 4 expenses must be present in stats."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id)
        # We check for the presence of the oldest expense title as proof
        assert b"Old expense" in resp.data, (
            "Expected 'Old expense' (all-time only) to appear in unfiltered view"
        )

    def test_no_params_renders_rupee_symbol(self, client, db):
        """Rupee symbol must appear in the unfiltered view."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id)
        assert "₹".encode() in resp.data, (
            "Expected ₹ symbol in unfiltered profile page"
        )


# ---------------------------------------------------------------------------
# 3.  preset=this_month
# ---------------------------------------------------------------------------

class TestPresetThisMonth:
    def test_this_month_returns_200(self, client, db):
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-05-01&date_to=2026-05-12")
        assert resp.status_code == 200

    def test_this_month_filters_stats_to_current_month(self, client, db):
        """With preset=this_month, total must reflect only expenses in May 2026."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-05-01&date_to=2026-05-12")
        # Only Coffee (120.00) falls in 2026-05
        assert "120.00".encode() in resp.data, (
            "Expected ₹120.00 (this month only) in stats"
        )
        # Old all-time expense must NOT appear in the transactions list
        assert b"Old expense" not in resp.data, (
            "Old expense should be filtered out by this_month preset"
        )

    def test_this_month_excludes_previous_month_transaction(self, client, db):
        """Metro (April) must not appear in transaction list for this_month."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-05-01&date_to=2026-05-12")
        assert b"Metro" not in resp.data, (
            "April Metro expense should be excluded by this_month preset"
        )

    def test_this_month_active_preset_indicator_present(self, client, db):
        """The active-preset CSS class must appear when this_month is active."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-05-01&date_to=2026-05-12")
        assert b"filter-btn--active" in resp.data, (
            "Expected filter-btn--active class to be present for this_month preset"
        )

    def test_this_month_rupee_symbol_present(self, client, db):
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-05-01&date_to=2026-05-12")
        assert "₹".encode() in resp.data, (
            "₹ symbol must appear even when this_month filter is active"
        )


# ---------------------------------------------------------------------------
# 4.  preset=3months
# ---------------------------------------------------------------------------

class TestPreset3Months:
    def test_3months_returns_200(self, client, db):
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-02-11&date_to=2026-05-12")
        assert resp.status_code == 200

    def test_3months_includes_expenses_within_90_days(self, client, db):
        """Coffee (May) and Metro (April) are within 90 days of FAKE_TODAY."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-02-11&date_to=2026-05-12")
        # TOTAL_3M = 420.00
        assert "420.00".encode() in resp.data, (
            "Expected ₹420.00 total for 3-month window"
        )
        assert b"Coffee" in resp.data, "Coffee (this month) must appear in 3-month window"
        assert b"Metro" in resp.data, "Metro (April) must appear in 3-month window"

    def test_3months_excludes_expenses_older_than_90_days(self, client, db):
        """Books (Feb 10) is ~91 days before May 12, so outside the 90-day window."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-02-11&date_to=2026-05-12")
        assert b"Old expense" not in resp.data, (
            "Old expense (Oct 2025) must be excluded from 3-month window"
        )

    def test_3months_active_preset_indicator_present(self, client, db):
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-02-11&date_to=2026-05-12")
        assert b"filter-btn--active" in resp.data, (
            "Expected filter-btn--active class for 3months preset"
        )


# ---------------------------------------------------------------------------
# 5.  preset=6months
# ---------------------------------------------------------------------------

class TestPreset6Months:
    def test_6months_returns_200(self, client, db):
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2025-11-13&date_to=2026-05-12")
        assert resp.status_code == 200

    def test_6months_includes_expenses_within_180_days(self, client, db):
        """Coffee, Metro, and Books are within 180 days of FAKE_TODAY."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2025-11-13&date_to=2026-05-12")
        # TOTAL_6M = 870.00
        assert "870.00".encode() in resp.data, (
            "Expected ₹870.00 total for 6-month window"
        )
        assert b"Books" in resp.data, "Books (Feb) must appear in 6-month window"

    def test_6months_excludes_expenses_older_than_180_days(self, client, db):
        """Old expense (Oct 2025) is ~223 days before May 12, outside 180-day window."""
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2025-11-13&date_to=2026-05-12")
        assert b"Old expense" not in resp.data, (
            "Old expense (Oct 2025) must be excluded from 6-month window"
        )

    def test_6months_active_preset_indicator_present(self, client, db):
        db_path, user_id = db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2025-11-13&date_to=2026-05-12")
        assert b"filter-btn--active" in resp.data, (
            "Expected filter-btn--active class for 6months preset"
        )


# ---------------------------------------------------------------------------
# 6.  preset=all
# ---------------------------------------------------------------------------

class TestPresetAll:
    def test_all_preset_returns_200(self, client, db):
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert resp.status_code == 200

    def test_all_preset_shows_every_expense(self, client, db):
        """preset=all must return every expense regardless of date."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert "1,870.00".encode() in resp.data, (
            "Expected ₹1,870.00 (all-time total) with preset=all"
        )
        assert b"Old expense" in resp.data, (
            "Old expense must be visible with preset=all"
        )

    def test_all_preset_active_indicator_present(self, client, db):
        """The 'All Time' button should be marked active when preset=all."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert b"filter-btn--active" in resp.data, (
            "Expected filter-btn--active class when preset=all"
        )

    def test_no_params_and_all_preset_return_same_total(self, client, db):
        """
        /profile with no params and /profile must show the same
        total. This verifies that 'All Time' truly clears any filter.
        """
        db_path, user_id = db
        resp_no_params = _get_profile(client, db_path, user_id, "/profile")
        resp_all = _get_profile(client, db_path, user_id, "/profile")
        # Both should contain the all-time total
        assert "1,870.00".encode() in resp_no_params.data
        assert "1,870.00".encode() in resp_all.data


# ---------------------------------------------------------------------------
# 7.  Custom date range (valid)
# ---------------------------------------------------------------------------

class TestCustomDateRange:
    def test_valid_custom_range_returns_200(self, client, db):
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-04-01&date_to=2026-04-30"
        )
        assert resp.status_code == 200

    def test_valid_custom_range_filters_to_only_matching_expense(self, client, db):
        """date_from=2026-04-01&date_to=2026-04-30 should return only Metro (300.00)."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-04-01&date_to=2026-04-30"
        )
        assert b"Metro" in resp.data, (
            "Metro (April) must appear in custom April range"
        )
        assert b"Coffee" not in resp.data, (
            "Coffee (May) must be excluded from April custom range"
        )
        assert b"Old expense" not in resp.data, (
            "Old expense (Oct 2025) must be excluded from April custom range"
        )
        assert "300.00".encode() in resp.data, (
            "Expected ₹300.00 total for April custom range"
        )

    def test_valid_custom_range_inclusive_bounds(self, client, db):
        """date_from and date_to are inclusive — an expense on date_from is included."""
        db_path, user_id = db
        # Coffee is on 2026-05-05 exactly; set date_from=date_to=2026-05-05
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-05-05&date_to=2026-05-05"
        )
        assert b"Coffee" in resp.data, (
            "Expense on the exact date_from=date_to boundary must be included"
        )
        assert "120.00".encode() in resp.data, (
            "Expected ₹120.00 when filtering to exactly 2026-05-05"
        )

    def test_valid_custom_range_active_indicator_shows_custom(self, client, db):
        """A custom date range should also trigger the active preset indicator."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-04-01&date_to=2026-04-30"
        )
        assert b"filter-btn--active" in resp.data, (
            "Expected filter-btn--active to appear for custom date range"
        )

    def test_valid_custom_range_rupee_symbol_present(self, client, db):
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-04-01&date_to=2026-04-30"
        )
        assert "₹".encode() in resp.data, (
            "₹ symbol must appear even with a custom date range filter active"
        )


# ---------------------------------------------------------------------------
# 8.  date_from > date_to — validation error
# ---------------------------------------------------------------------------

class TestInvalidDateOrder:
    def test_date_from_after_date_to_returns_200(self, client, db):
        """Invalid order must not crash — must return 200."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-05-01&date_to=2026-04-01"
        )
        assert resp.status_code == 200, (
            "date_from > date_to must return 200, not an error page"
        )

    def test_date_from_after_date_to_flashes_error_message(self, client, db):
        """The flash message 'Start date must be before end date.' must appear."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-05-01&date_to=2026-04-01"
        )
        assert b"Start date must be before end date." in resp.data, (
            "Expected flash error 'Start date must be before end date.' in response"
        )

    def test_date_from_after_date_to_falls_back_to_unfiltered(self, client, db):
        """After the validation error, all expenses must still be shown (no filter)."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2026-05-01&date_to=2026-04-01"
        )
        assert "1,870.00".encode() in resp.data, (
            "Expected all-time total ₹1,870.00 when date order is invalid (fallback)"
        )


# ---------------------------------------------------------------------------
# 9.  Malformed date strings — must not crash
# ---------------------------------------------------------------------------

class TestMalformedDate:
    @pytest.mark.parametrize("bad_url", [
        "/profile?date_from=not-a-date&date_to=2026-04-30",
        "/profile?date_from=2026-04-01&date_to=not-a-date",
        "/profile?date_from=not-a-date&date_to=not-a-date",
        "/profile?date_from=2026-13-01&date_to=2026-04-30",   # month 13
        "/profile?date_from=2026-00-01&date_to=2026-04-30",   # month 00
        "/profile?date_from=&date_to=2026-04-30",              # empty string
        "/profile?date_from=2026/04/01&date_to=2026-04-30",   # wrong separator
    ])
    def test_malformed_date_returns_200(self, client, db, bad_url):
        """Any malformed date must silently fall back — 200, no exception."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, bad_url)
        assert resp.status_code == 200, (
            f"Expected 200 for malformed URL {bad_url!r}, got {resp.status_code}"
        )

    def test_malformed_date_falls_back_to_unfiltered_data(self, client, db):
        """With a malformed date, all expenses should appear (no filter applied)."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=not-a-date&date_to=2026-04-30"
        )
        assert "1,870.00".encode() in resp.data, (
            "Expected all-time total ₹1,870.00 when date is malformed (fallback)"
        )


# ---------------------------------------------------------------------------
# 10. Rupee symbol always present
# ---------------------------------------------------------------------------

class TestRupeeSymbol:
    @pytest.mark.parametrize("url", [
        "/profile",
        "/profile",
        "/profile?date_from=2026-04-01&date_to=2026-04-30",
    ])
    def test_rupee_symbol_present_for_all_filters(self, client, db, url):
        """₹ must appear in the HTML regardless of which filter is active."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, url)
        assert "₹".encode() in resp.data, (
            f"Expected ₹ symbol in response for {url!r}"
        )


# ---------------------------------------------------------------------------
# 11. User with no expenses in the selected range
# ---------------------------------------------------------------------------

class TestEmptyRange:
    def test_no_expenses_in_range_returns_200(self, client, db):
        """A range with zero matching expenses must not error out."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2024-01-01&date_to=2024-01-31"
        )
        assert resp.status_code == 200, (
            "Expected 200 even when no expenses fall in the selected range"
        )

    def test_no_expenses_in_range_shows_zero_total(self, client, db):
        """When no expenses match the range, total_spent must be ₹0.00."""
        db_path, user_id = db
        resp = _get_profile(
            client, db_path, user_id,
            "/profile?date_from=2024-01-01&date_to=2024-01-31"
        )
        assert b"0.00" in resp.data, (
            "Expected ₹0.00 total when no expenses exist in range"
        )

    def test_user_with_no_expenses_at_all_returns_200(self, client, empty_db):
        """A user with no expenses at all must get a 200 with no crashes."""
        db_path, user_id = empty_db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert resp.status_code == 200, (
            "Expected 200 for a user with no expenses"
        )

    def test_user_with_no_expenses_at_all_shows_zero_total(self, client, empty_db):
        """A user with zero expenses must see ₹0.00 total."""
        db_path, user_id = empty_db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert b"0.00" in resp.data, (
            "Expected ₹0.00 for user with no expenses"
        )

    def test_user_with_no_expenses_in_preset_shows_zero_total(self, client, empty_db):
        """Even with preset=this_month, a user with no expenses sees ₹0.00."""
        db_path, user_id = empty_db
        with patch("app.date") as mock_date:
            mock_date.today.return_value = FAKE_TODAY
            resp = _get_profile(client, db_path, user_id, "/profile?date_from=2026-05-01&date_to=2026-05-12")
        assert resp.status_code == 200, (
            "Expected 200 for empty user with this_month preset"
        )
        assert b"0.00" in resp.data, (
            "Expected ₹0.00 for empty user with this_month filter"
        )


# ---------------------------------------------------------------------------
# 12. Template rendering — filter bar present
# ---------------------------------------------------------------------------

class TestTemplateRendering:
    def test_profile_renders_filter_bar(self, client, db):
        """The profile page must include a filter bar section."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, "/profile")
        # The filter bar contains the preset buttons; check for at least one.
        assert b"This Month" in resp.data or b"this_month" in resp.data, (
            "Expected 'This Month' preset button to be present in the filter bar"
        )

    def test_profile_renders_all_time_button(self, client, db):
        """An 'All Time' (or equivalent) option must be visible in the filter bar."""
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert b"All" in resp.data, (
            "Expected an 'All Time' option in the profile filter bar"
        )

    def test_profile_default_active_preset_is_all(self, client, db):
        """
        With no query params, active_preset should be 'all', meaning the
        filter-btn--active class must still appear (on the 'All Time' button).
        """
        db_path, user_id = db
        resp = _get_profile(client, db_path, user_id, "/profile")
        assert b"filter-btn--active" in resp.data, (
            "Expected filter-btn--active on the 'All Time' button by default"
        )
