import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "spendly.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            email    TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            title       TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT
        );
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    conn.execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        ("Nitish Kumar", "nitish@example.com", generate_password_hash("password123", method="pbkdf2:sha256")),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    sample_expenses = [
        (user_id, "Groceries",     850.00, "Food",          "2026-04-01", "Weekly groceries"),
        (user_id, "Metro card",    500.00, "Transport",     "2026-04-02", "Monthly top-up"),
        (user_id, "Netflix",       649.00, "Entertainment", "2026-04-03", "Monthly subscription"),
        (user_id, "Electricity",  1200.00, "Utilities",     "2026-04-05", "March bill"),
        (user_id, "Lunch",         180.00, "Food",          "2026-04-10", "Office lunch"),
        (user_id, "Gym membership",999.00, "Health",        "2026-04-11", "Monthly fee"),
        (user_id, "Uber",          320.00, "Transport",     "2026-04-13", "Weekend rides"),
        (user_id, "Books",         450.00, "Education",     "2026-04-15", "Programming books"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, title, amount, category, date, description) VALUES (?,?,?,?,?,?)",
        sample_expenses,
    )
    conn.commit()
    conn.close()
