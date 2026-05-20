from datetime import datetime

from database.db import get_db


def _apply_date_filter(sql, params, date_from, date_to):
    if date_from and date_to:
        sql += " AND date BETWEEN ? AND ?"
        params += [date_from, date_to]
    return sql, params


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    created_at = datetime.fromisoformat(row["created_at"])
    return {
        "name": row["name"],
        "email": row["email"],
        "initials": "".join(w[0].upper() for w in row["name"].split()[:2]),
        "member_since": created_at.strftime("%B %Y"),
    }


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    sql, params = _apply_date_filter(
        "SELECT amount, category FROM expenses WHERE user_id = ?",
        [user_id], date_from, date_to,
    )
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return {"total_spent": "₹0.00", "tx_count": 0, "top_category": "—"}
    total = sum(r["amount"] for r in rows)
    cat_totals = {}
    for r in rows:
        cat_totals[r["category"]] = cat_totals.get(r["category"], 0) + r["amount"]
    top_cat = max(cat_totals, key=cat_totals.get)
    return {
        "total_spent": f"₹{total:,.2f}",
        "tx_count": len(rows),
        "top_category": top_cat,
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    sql, params = _apply_date_filter(
        "SELECT id, title, amount, category, date FROM expenses WHERE user_id = ?",
        [user_id], date_from, date_to,
    )
    sql += " ORDER BY date DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        result.append({
            "id": r["id"],
            "date": d.strftime("%d %b %Y"),
            "description": r["title"],
            "category": r["category"],
            "amount": f"₹{r['amount']:,.2f}",
        })
    return result


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    sql, params = _apply_date_filter(
        "SELECT category, SUM(amount) as total FROM expenses WHERE user_id = ?",
        [user_id], date_from, date_to,
    )
    sql += " GROUP BY category ORDER BY total DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return []
    grand_total = sum(r["total"] for r in rows)
    result = [
        {
            "name": r["category"],
            "total": f"₹{r['total']:,.2f}",
            "pct": int(r["total"] / grand_total * 100),
        }
        for r in rows
    ]
    diff = 100 - sum(item["pct"] for item in result)
    if diff and result:
        result[0]["pct"] += diff
    return result


def insert_expense(user_id, amount, category, date, description):
    conn = get_db()
    title = description or category
    conn.execute(
        "INSERT INTO expenses (user_id, title, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, title, amount, category, date, description),
    )
    conn.commit()
    expense_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return expense_id
