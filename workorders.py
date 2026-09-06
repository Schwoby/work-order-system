from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime, timedelta

from db import get_db
from helpers import active_access_required, get_nav_context, get_current_user, get_effective_role_perm, now_local_str, LOCAL_TZ

workorders_bp = Blueprint("workorders", __name__)

@workorders_bp.route("/wo/current")
@active_access_required
def wo_current():
    conn = get_db()
    wos = conn.execute("""
        SELECT * FROM workorders
        WHERE completed = 0
        ORDER BY
          CASE
            WHEN needed IS NOT NULL
                 AND TRIM(needed) != ''
                 AND needed <= strftime('%Y-%m-%dT%H:%M') THEN 0
            WHEN needed IS NOT NULL
                 AND TRIM(needed) != '' THEN 1
            ELSE 2
          END,
          needed ASC,
          submitted ASC
    """).fetchall()
    conn.close()
    return render_template(
        "wo_current.html",
        workorders=wos,
        now=datetime.now(LOCAL_TZ),
        soon=datetime.now(LOCAL_TZ) + timedelta(hours=72),
        **get_nav_context()
    )

@workorders_bp.route("/wo/create")
@active_access_required
def wo_create():
    return render_template("wo_create.html", **get_nav_context())

@workorders_bp.route("/completed")
@active_access_required
def wo_completed():
    conn = get_db()
    wos = conn.execute("""
        SELECT * FROM workorders
        WHERE completed = 1
        ORDER BY last_update DESC
    """).fetchall()
    conn.close()
    return render_template("wo_completed.html", workorders=wos, **get_nav_context())

@workorders_bp.route("/add", methods=["POST"])
@active_access_required
def add():
    user = get_current_user()
    effective_perm = get_effective_role_perm(user["user_key"])
    if effective_perm not in (1, 2):
        return redirect(url_for("users.user_profile"))

    subject = request.form["subject"]
    body = request.form["body"]
    room = request.form.get("room")
    needed = request.form.get("needed")
    requested_by = request.form.get("requested_by")

    now_local = now_local_str()

    conn = get_db()
    conn.execute("""
        INSERT INTO workorders
        (subject, body, room, needed, requested_by, submitted, last_update)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (subject, body, room, needed, requested_by, now_local, now_local))
    conn.commit()
    conn.close()
    return redirect(url_for("workorders.wo_current"))

@workorders_bp.route("/edit/<int:wo_id>")
@active_access_required
def wo_edit(wo_id):
    conn = get_db()
    wo = conn.execute("SELECT * FROM workorders WHERE id = ?", (wo_id,)).fetchone()
    conn.close()
    return render_template("wo_edit.html", wo=wo, **get_nav_context())

@workorders_bp.route("/update/<int:wo_id>", methods=["POST"])
@active_access_required
def update(wo_id):
    user = get_current_user()
    effective_perm = get_effective_role_perm(user["user_key"])

    completed = 1 if request.form.get("completed") == "on" else 0
    subject = request.form["subject"]
    body = request.form["body"]
    room = request.form.get("room")
    needed = request.form.get("needed")
    requested_by = request.form.get("requested_by")
    completion_text = request.form.get("completion_text")

    ts = now_local_str()

    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM workorders WHERE id = ?", (wo_id,)).fetchone()
        if not existing:
            flash("Work order not found.")
            return redirect(url_for("workorders.wo_current"))

        if effective_perm == 1:
            conn.execute("""
                UPDATE workorders
                SET subject = ?,
                    body = ?,
                    room = ?,
                    needed = ?,
                    requested_by = ?,
                    last_update = ?
                WHERE id = ?
            """, (subject, body, room, needed, requested_by, ts, wo_id))
        else:
            conn.execute("""
                UPDATE workorders
                SET subject = ?,
                    body = ?,
                    room = ?,
                    needed = ?,
                    requested_by = ?,
                    completion_text = ?,
                    completed = ?,
                    last_update = ?
                WHERE id = ?
            """, (subject, body, room, needed, requested_by,
                  completion_text, completed, ts, wo_id))

        conn.commit()
        return redirect(url_for("workorders.wo_current"))
    finally:
        conn.close()
