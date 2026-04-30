import re
from flask import Flask, render_template, session, redirect, url_for, flash, request
from werkzeug.security import check_password_hash
from database.db import init_db, seed_db, create_user, get_user_by_email

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-prod"

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
        return redirect(url_for("landing"))
<<<<<<< HEAD

=======
>>>>>>> d5a8a221d5014fa05985dc9488a3f5b2227cf32d
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
        return redirect(url_for("landing"))

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
        return redirect(url_for("landing"))

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
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
