import sqlite3
import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    """In-memory SQLite DB with one seed user and 8 expenses."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
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
    """)
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        ("Nitish Kumar", "nitish@example.com",
         generate_password_hash("password123", method="pbkdf2:sha256"), "2026-01-15 10:00:00"),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.executemany(
        "INSERT INTO expenses (user_id, title, amount, category, date, description)"
        " VALUES (?,?,?,?,?,?)",
        [
            (user_id, "Groceries",      850.00, "Food",          "2026-04-01", ""),
            (user_id, "Metro card",     500.00, "Transport",     "2026-04-02", ""),
            (user_id, "Netflix",        649.00, "Entertainment", "2026-04-03", ""),
            (user_id, "Electricity",   1200.00, "Utilities",     "2026-04-05", ""),
            (user_id, "Lunch",          180.00, "Food",          "2026-04-10", ""),
            (user_id, "Gym membership", 999.00, "Health",        "2026-04-11", ""),
            (user_id, "Uber",           320.00, "Transport",     "2026-04-13", ""),
            (user_id, "Books",          450.00, "Education",     "2026-04-15", ""),
        ],
    )
    conn.commit()
    yield conn, user_id
    conn.close()


@pytest.fixture
def empty_user_db():
    """In-memory DB with one user but no expenses."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT
        );
    """)
    conn.execute(
        "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
        ("New User", "new@example.com",
         generate_password_hash("pass1234", method="pbkdf2:sha256"), "2026-05-01 09:00:00"),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    yield conn, user_id
    conn.close()


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

def test_get_user_by_id_valid(db_conn):
    conn, user_id = db_conn
    with patch("database.queries.get_db", return_value=conn):
        result = get_user_by_id(user_id)
    assert result["name"] == "Nitish Kumar"
    assert result["email"] == "nitish@example.com"
    assert result["initials"] == "NK"
    assert result["member_since"] == "January 2026"


def test_get_user_by_id_not_found(db_conn):
    conn, _ = db_conn
    with patch("database.queries.get_db", return_value=conn):
        result = get_user_by_id(9999)
    assert result is None


# ---------------------------------------------------------------------------
# get_summary_stats
# ---------------------------------------------------------------------------

def test_get_summary_stats_with_expenses(db_conn):
    conn, user_id = db_conn
    with patch("database.queries.get_db", return_value=conn):
        result = get_summary_stats(user_id)
    assert result["total_spent"] == "₹5,148.00"
    assert result["tx_count"] == 8
    assert result["top_category"] == "Utilities"


def test_get_summary_stats_no_expenses(empty_user_db):
    conn, user_id = empty_user_db
    with patch("database.queries.get_db", return_value=conn):
        result = get_summary_stats(user_id)
    assert result == {"total_spent": "₹0.00", "tx_count": 0, "top_category": "—"}


# ---------------------------------------------------------------------------
# get_recent_transactions
# ---------------------------------------------------------------------------

def test_get_recent_transactions_with_expenses(db_conn):
    conn, user_id = db_conn
    with patch("database.queries.get_db", return_value=conn):
        result = get_recent_transactions(user_id)
    assert len(result) == 8
    assert result[0]["description"] == "Books"   # newest date: 2026-04-15
    assert result[0]["date"] == "15 Apr 2026"
    assert result[0]["amount"] == "₹450.00"
    assert "category" in result[0]


def test_get_recent_transactions_no_expenses(empty_user_db):
    conn, user_id = empty_user_db
    with patch("database.queries.get_db", return_value=conn):
        result = get_recent_transactions(user_id)
    assert result == []


# ---------------------------------------------------------------------------
# get_category_breakdown
# ---------------------------------------------------------------------------

def test_get_category_breakdown_with_expenses(db_conn):
    conn, user_id = db_conn
    with patch("database.queries.get_db", return_value=conn):
        result = get_category_breakdown(user_id)
    assert len(result) == 6
    assert result[0]["name"] == "Utilities"
    assert sum(item["pct"] for item in result) == 100


def test_get_category_breakdown_no_expenses(empty_user_db):
    conn, user_id = empty_user_db
    with patch("database.queries.get_db", return_value=conn):
        result = get_category_breakdown(user_id)
    assert result == []


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_profile_unauthenticated():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        resp = c.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_authenticated():
    """Each call to get_db() inside the route must get a fresh connection."""
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"

    def make_conn():
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL, amount REAL NOT NULL,
                category TEXT NOT NULL, date TEXT NOT NULL, description TEXT
            );
        """)
        c.execute(
            "INSERT INTO users (name, email, password, created_at) VALUES (?,?,?,?)",
            ("Nitish Kumar", "nitish@example.com",
             generate_password_hash("password123", method="pbkdf2:sha256"),
             "2026-01-15 10:00:00"),
        )
        uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.executemany(
            "INSERT INTO expenses (user_id, title, amount, category, date, description)"
            " VALUES (?,?,?,?,?,?)",
            [
                (uid, "Groceries", 850.00, "Food", "2026-04-01", ""),
                (uid, "Electricity", 1200.00, "Utilities", "2026-04-05", ""),
                (uid, "Books", 450.00, "Education", "2026-04-15", ""),
            ],
        )
        c.commit()
        return c

    with flask_app.app.test_client() as c:
        with patch("database.queries.get_db", side_effect=make_conn):
            with c.session_transaction() as sess:
                sess["user_id"] = 1
            resp = c.get("/profile")
    assert resp.status_code == 200
    assert b"Nitish Kumar" in resp.data
    assert b"nitish@example.com" in resp.data
    assert "₹".encode() in resp.data
