# spendAI
# SpendAI — AI-Assisted Expense Tracking Application

&gt; A full-stack expense tracking web app built with Python (Flask), SQLite, and AI-assisted development (Claude Code). Designed for personal finance management with an intuitive UI.

---

## Live Demo

Soon with Graph and Matrix

---

## Screenshots

| Dashboard | Add Expense | Analytics |
|-----------|-------------|-----------|
<img width="2048" height="1335" alt="1781045536272" src="https://github.com/user-attachments/assets/33a44c32-3aeb-49d9-a436-03ec34ef89e6" />

) <img width="2048" height="1335" alt="1781045536408" src="https://github.com/user-attachments/assets/89351fbd-15db-45d9-a55a-dc3bfef87d9b" />
 | ![](Soon!) |

---

## Features

- Track daily expenses with categories and tags
- Monthly spending analytics and visual summaries
- SQLite database for lightweight, zero-config storage
- AI-assisted development workflow using Claude Code
- Responsive HTML/CSS frontend

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python, Flask |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript |
| AI Tools | Claude Code (AI-assisted development) |
| Deployment | *(add your platform: Render, Heroku, GCP)* |

---

## Project Structure
spendai/
├── app/
│   ├── init.py
│   ├── routes.py
│   ├── models.py
│   └── templates/
├── static/
│   ├── css/
│   └── js/
├── instance/
│   └── expenses.db
├── requirements.txt
├── run.py
└── README.md


---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/alwaris/spendai.git
cd spendai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python run.py
# Open http://localhost:50001 in your browser

| Method | Endpoint             | Description              |
| ------ | -------------------- | ------------------------ |
| GET    | `/`                  | Dashboard view           |
| POST   | `/add`               | Add new expense          |
| GET    | `/api/expenses`      | List all expenses (JSON) |
| DELETE | `/api/expenses/<id>` | Delete an expense        |

What I Learned
Building RESTful APIs with Flask and Jinja2 templating
Database schema design with SQLite and SQLAlchemy
Frontend-backend integration without a JavaScript framework
Using AI-assisted development (Claude Code) to accelerate coding workflows
The importance of clean project structure for maintainability


Future Improvements
[ ] Migrate to PostgreSQL for production
[ ] Add user authentication (JWT or OAuth)
[ ] Deploy to Google Cloud Run with Docker
[ ] Add expense categorization with ML/NLP
[ ] Build a React frontend for better UX



