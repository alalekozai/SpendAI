import os
import re
import math
import random
from datetime import date, datetime, timedelta
from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify, abort
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import init_db, seed_db, create_user, get_user_by_email, get_db, get_expense_by_id, update_expense
from database.queries import (
    get_user_by_id, get_summary_stats,
    get_recent_transactions, get_category_breakdown,
    insert_expense,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([name, email, password, confirm_password]):
            flash("All fields are required.")
            return render_template("register.html", form=request.form)

        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$', email):
            flash("Enter a valid email address.")
            return render_template("register.html", form=request.form)

        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return render_template("register.html", form=request.form)

        if password != confirm_password:
            flash("Passwords do not match.")
            return render_template("register.html", form=request.form)

        if get_user_by_email(email):
            flash("An account with that email already exists.")
            return render_template("register.html", form=request.form)

        user_id = create_user(name, email, password)
        session["user_id"] = user_id
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("All fields are required.")
            return render_template("login.html", form=request.form)

        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password"], password):
            flash("Invalid email or password.")
            return render_template("login.html", form=request.form)

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/dashboard")
def dashboard():
    return "Dashboard — coming in Step 5"


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = get_user_by_id(session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    raw_from = request.args.get("date_from", "")
    raw_to   = request.args.get("date_to", "")
    today    = date.today()

    # Pre-compute preset date ranges so the template can embed them in links
    preset_dates = {
        "this_month": (today.replace(day=1).isoformat(), today.isoformat()),
        "3months":    ((today - timedelta(days=90)).isoformat(), today.isoformat()),
        "6months":    ((today - timedelta(days=180)).isoformat(), today.isoformat()),
    }

    date_from = date_to = None

    if raw_from or raw_to:
        try:
            if not raw_from or not raw_to:
                raise ValueError("Both dates required")
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date().isoformat()
            date_to   = datetime.strptime(raw_to,   "%Y-%m-%d").date().isoformat()
            if date_from > date_to:
                flash("Start date must be before end date.")
                date_from = date_to = None
        except ValueError:
            date_from = date_to = None

    # Detect which preset (if any) matches the active date range
    active_preset = "all"
    if date_from and date_to:
        matched = next(
            (name for name, (f, t) in preset_dates.items() if f == date_from and t == date_to),
            None,
        )
        active_preset = matched if matched else "custom"

    stats        = get_summary_stats(session["user_id"], date_from, date_to)
    transactions = get_recent_transactions(session["user_id"], date_from=date_from, date_to=date_to)
    categories   = get_category_breakdown(session["user_id"], date_from, date_to)

    return render_template("profile.html",
                           user=user, stats=stats,
                           transactions=transactions, categories=categories,
                           date_from=date_from, date_to=date_to,
                           active_preset=active_preset,
                           preset_dates=preset_dates)


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


VALID_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "POST":
        amount_raw  = request.form.get("amount", "").strip()
        category    = request.form.get("category", "").strip()
        date_raw    = request.form.get("date", "").strip()
        description = request.form.get("description", "").strip() or None

        error = None
        amount = None

        try:
            amount = float(amount_raw)
            if amount <= 0 or math.isinf(amount) or math.isnan(amount):
                raise ValueError
        except ValueError:
            error = "Amount must be a positive number."

        if not error and category not in VALID_CATEGORIES:
            error = "Please select a valid category."

        if not error:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Please enter a valid date."

        if not error and description and len(description) > 200:
            error = "Description must be 200 characters or fewer."

        if error:
            flash(error)
            return render_template("add_expense.html", form=request.form,
                                   categories=VALID_CATEGORIES)

        insert_expense(session["user_id"], amount, category, date_raw, description)
        flash("Expense added successfully.")
        return redirect(url_for("profile"))

    return render_template("add_expense.html",
                           form={},
                           categories=VALID_CATEGORIES,
                           today=date.today().isoformat())


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id)
    if expense is None:
        abort(404)
    if expense["user_id"] != session["user_id"]:
        abort(403)

    if request.method == "POST":
        title_raw   = request.form.get("title", "").strip()
        amount_raw  = request.form.get("amount", "").strip()
        category    = request.form.get("category", "").strip()
        date_raw    = request.form.get("date", "").strip()
        description = request.form.get("description", "").strip() or None

        error = None
        amount = None

        if not title_raw:
            error = "Title is required."
        elif len(title_raw) > 100:
            error = "Title must be 100 characters or fewer."

        if not error:
            try:
                amount = float(amount_raw)
                if amount <= 0 or math.isinf(amount) or math.isnan(amount):
                    raise ValueError
            except ValueError:
                error = "Amount must be a positive number."

        if not error and category not in VALID_CATEGORIES:
            error = "Please select a valid category."

        if not error:
            try:
                datetime.strptime(date_raw, "%Y-%m-%d")
            except ValueError:
                error = "Please enter a valid date."

        if not error and description and len(description) > 200:
            error = "Description must be 200 characters or fewer."

        if error:
            flash(error)
            return render_template("edit_expense.html",
                                   form=request.form,
                                   expense=expense,
                                   categories=VALID_CATEGORIES)

        update_expense(id, title_raw, amount, category, date_raw, description)
        flash("Expense updated successfully.")
        return redirect(url_for("profile"))

    return render_template("edit_expense.html",
                           form=expense,
                           expense=expense,
                           categories=VALID_CATEGORIES)


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


@app.route("/seed-expenses/<int:num_users>/<int:min_exp>/<int:max_exp>")
def seed_expenses(num_users, min_exp, max_exp):
    _FIRST_NAMES = [
        "Aarav", "Aditi", "Amit", "Ananya", "Arun", "Deepa", "Divya",
        "Ishaan", "Kavya", "Kiran", "Meera", "Mohan", "Neha", "Priya",
        "Rahul", "Riya", "Rohan", "Sana", "Sneha", "Suresh", "Vikram",
    ]
    _LAST_NAMES = [
        "Agarwal", "Bhat", "Chaudhary", "Das", "Gupta", "Iyer", "Joshi",
        "Kumar", "Mehta", "Nair", "Patel", "Rao", "Reddy", "Sharma",
        "Singh", "Verma",
    ]
    _EXPENSES = [
        ("Groceries",      "Food",          300,  900),
        ("Restaurant",     "Food",          150,  600),
        ("Coffee",         "Food",           80,  200),
        ("Metro card",     "Transport",     200,  600),
        ("Uber",           "Transport",     100,  400),
        ("Petrol",         "Transport",     400, 1200),
        ("Netflix",        "Entertainment", 199,  649),
        ("Movie tickets",  "Entertainment", 200,  500),
        ("Spotify",        "Entertainment",  59,  199),
        ("Electricity",    "Utilities",     600, 2000),
        ("Internet",       "Utilities",     500, 1200),
        ("Mobile recharge","Utilities",     179,  599),
        ("Gym membership", "Health",        500, 1500),
        ("Doctor visit",   "Health",        300,  800),
        ("Medicine",       "Health",        100,  500),
        ("Books",          "Education",     200,  800),
        ("Online course",  "Education",     500, 2000),
        ("Clothing",       "Shopping",      500, 3000),
        ("Electronics",    "Shopping",     1000, 8000),
    ]

    conn = get_db()
    created = []

    for _ in range(num_users):
        # generate unique email
        for _attempt in range(20):
            name = f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"
            suffix = random.randint(10, 99)
            email = f"{name.split()[0].lower()}.{name.split()[1].lower()}{suffix}@example.com"
            if not conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                break

        pw = generate_password_hash("password123", method="pbkdf2:sha256")
        conn.execute(
            "INSERT INTO users (name, email, password) VALUES (?,?,?)",
            (name, email, pw),
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        n_exp = random.randint(min_exp, max_exp)
        expenses = []
        for _ in range(n_exp):
            title, category, lo, hi = random.choice(_EXPENSES)
            amount = round(random.uniform(lo, hi), 2)
            days_ago = random.randint(0, 90)
            exp_date = (date.today() - timedelta(days=days_ago)).isoformat()
            expenses.append((user_id, title, amount, category, exp_date, ""))

        conn.executemany(
            "INSERT INTO expenses (user_id, title, amount, category, date, description)"
            " VALUES (?,?,?,?,?,?)",
            expenses,
        )
        conn.commit()
        created.append({"id": user_id, "name": name, "email": email, "expenses": n_exp})

    conn.close()
    return jsonify({"seeded": created})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
