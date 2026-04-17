# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Spendly** — a Flask-based personal expense tracker. This is a step-by-step student project where features are built incrementally (Steps 1–9 referenced in comments throughout the code).

## Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run the dev server (port 5001)
python app.py

# Run tests
pytest

# Run a single test file
pytest tests/test_foo.py

# Run a single test
pytest tests/test_foo.py::test_function_name
```

## Architecture

- **`app.py`** — single-file Flask app, all routes defined here. Routes for auth, expenses, and static pages.
- **`database/db.py`** — SQLite helpers to be implemented: `get_db()` (connection with row_factory + foreign keys), `init_db()` (CREATE TABLE IF NOT EXISTS), `seed_db()` (sample data).
- **`templates/`** — Jinja2 templates. `base.html` is the shared layout (navbar + footer); all other templates extend it via `{% extends "base.html" %}`.
- **`static/css/`** — `style.css` is the global stylesheet loaded in `base.html`; `landing.css` is landing-page-specific and loaded via `{% block head %}`.
- **`static/js/main.js`** — global JS entry point; page-specific JS goes in `{% block scripts %}` within the template.

## Key conventions

- The app runs on **port 5001** (not the Flask default 5000).
- SQLite is the database. The `database/` package is where all DB logic lives; routes import from there.
- Templates use Jinja2 blocks: `title`, `head` (extra CSS), `content`, `scripts` (extra JS).
- Currency is in **Indian Rupees (₹)**; keep this consistent in any UI text.
