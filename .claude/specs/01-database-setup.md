# Spec: Step 1 — Database Setup

## Overview

SQLite database layer for Spendly. Database file lives at `database/spendly.db` and is
created automatically on first app startup.

---

## Tables

### `users`
| Column     | Type    | Constraints                        |
|------------|---------|------------------------------------|
| id         | INTEGER | PRIMARY KEY AUTOINCREMENT          |
| name       | TEXT    | NOT NULL                           |
| email      | TEXT    | NOT NULL UNIQUE                    |
| password   | TEXT    | NOT NULL (pbkdf2:sha256 hashed)    |
| created_at | TEXT    | NOT NULL DEFAULT (datetime('now')) |

### `expenses`
| Column      | Type    | Constraints                   |
|-------------|---------|-------------------------------|
| id          | INTEGER | PRIMARY KEY AUTOINCREMENT     |
| user_id     | INTEGER | NOT NULL REFERENCES users(id) |
| title       | TEXT    | NOT NULL                      |
| amount      | REAL    | NOT NULL (in ₹)               |
| category    | TEXT    | NOT NULL                      |
| date        | TEXT    | NOT NULL (ISO YYYY-MM-DD)     |
| description | TEXT    | nullable                      |

---

## Functions (`database/db.py`)

| Function | Description |
|----------|-------------|
| `get_db()` | Opens connection, sets `row_factory = sqlite3.Row`, enables `PRAGMA foreign_keys = ON` |
| `init_db()` | Creates both tables with `CREATE TABLE IF NOT EXISTS` |
| `seed_db()` | Inserts 1 demo user + 8 sample expenses if users table is empty |
| `get_user_by_email(email)` | Returns `sqlite3.Row` or `None` |
| `create_user(name, email, password)` | Hashes password, inserts row, returns new `id` |
| `get_expenses_for_user(user_id)` | Returns all expenses for a user ordered by date DESC |
| `get_expense_by_id(expense_id)` | Returns a single expense row or `None` |
| `add_expense(user_id, title, amount, category, date, description)` | Inserts and returns new `id` |
| `update_expense(expense_id, title, amount, category, date, description)` | Updates existing row |
| `delete_expense(expense_id)` | Deletes row by id |

---

## Startup wiring (`app.py`)

```python
with app.app_context():
    init_db()
    seed_db()
```

---

## Acceptance checklist

- [ ] Database file is created on app startup
- [ ] Both tables exist with correct schema and constraints
- [ ] Demo user exists with hashed password
- [ ] 8 sample expenses exist across categories
- [ ] No duplicate seed data on repeated runs
- [ ] App starts without errors
- [ ] Foreign key enforcement works
- [ ] All queries use parameterized SQL
