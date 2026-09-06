from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from db import get_db
from helpers import (
    login_required,
    admin_required,
    get_current_user,
    get_nav_context,
    get_timezones,
    user_status_text,
    user_profile_complete,
    get_effective_role_perm,
    is_valid_email,
    create_user_account,
)

users_bp = Blueprint("users", __name__)

@users_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        email = request.form.get("user_id", "")
        password = request.form.get("password", "")

        from helpers import authenticate_user
        success, result = authenticate_user(email, password)
        if not success:
            flash(str(result))
            return redirect(url_for("users.index"))

        session["user_key"] = result
        if not user_profile_complete(result):
            return redirect(url_for("users.create_profile"))

        effective_perm = get_effective_role_perm(result)
        if effective_perm == 0:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("users.user_profile"))
        if effective_perm in (1, 2, 3):
            flash("Login successful.")
            return redirect(url_for("workorders.wo_current"))

        flash("Your account does not have access to the work order system.")
        return redirect(url_for("users.user_profile"))

    if get_current_user():
        user = get_current_user()
        if not user_profile_complete(user["user_key"]):
            return redirect(url_for("users.create_profile"))

        effective_perm = get_effective_role_perm(user["user_key"])
        if effective_perm == 0:
            return redirect(url_for("users.user_profile"))
        if effective_perm in (1, 2, 3):
            return redirect(url_for("workorders.wo_current"))

        return redirect(url_for("users.user_profile"))

    return render_template("user_login.html", **get_nav_context())

@users_bp.route("/user/create", methods=["GET", "POST"])
def user_create():
    if request.method == "POST":
        email = request.form.get("user_id", "")
        password = request.form.get("password", "")
        verify_password = request.form.get("verify_password", "")

        if not is_valid_email(email):
            flash("Please enter a valid email address.")
            return redirect(url_for("users.user_create"))

        if password != verify_password:
            flash("Passwords do not match.")
            return redirect(url_for("users.user_create"))

        success, result = create_user_account(email, password)
        if not success:
            flash(str(result))
            return redirect(url_for("users.user_create"))

        session["user_key"] = result
        if not user_profile_complete(result):
            return redirect(url_for("users.create_profile"))

        effective_perm = get_effective_role_perm(result)
        if effective_perm == 0:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("users.user_profile"))
        if effective_perm in (1, 2, 3):
            flash("Account created successfully.")
            return redirect(url_for("workorders.wo_current"))

        flash("Account created, but no work order access is available.")
        return redirect(url_for("users.user_profile"))

    return render_template("user_create.html", **get_nav_context())

@users_bp.route("/user/logout")
@login_required
def user_logout():
    session.clear()
    return redirect(url_for("users.index"))

@users_bp.route("/user/profile", methods=["GET", "POST"])
@login_required
def user_profile():
    return redirect(url_for("users.create_profile"))

@users_bp.route("/profile/create", methods=["GET", "POST"])
@login_required
def create_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("users.index"))

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT 1 FROM profile_preferences WHERE user_key = ?",
            (user["user_key"],)
        ).fetchone()

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            display_name = request.form.get("display_name", "").strip()
            timezone = request.form.get("timezone", "").strip()
            theme = request.form.get("theme", "").strip()
            default_view = request.form.get("default_view", "").strip()

            if not all([full_name, display_name, timezone, theme, default_view]):
                flash("All profile fields are required.")
                return redirect(url_for("users.create_profile"))

            if existing:
                conn.execute("""
                    UPDATE profile_preferences
                    SET full_name = ?, display_name = ?, timezone = ?, theme = ?, default_view = ?
                    WHERE user_key = ?
                """, (full_name, display_name, timezone, theme, default_view, user["user_key"]))
            else:
                conn.execute("""
                    INSERT INTO profile_preferences
                    (user_key, full_name, display_name, timezone, theme, default_view)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user["user_key"], full_name, display_name, timezone, theme, default_view))

            conn.commit()

            effective_perm = get_effective_role_perm(user["user_key"])
            if effective_perm == 0:
                flash("Profile saved, but your account is blocked from the work order system.")
                return redirect(url_for("users.user_profile"))

            if effective_perm in (1, 2, 3):
                flash("Profile saved.")
                return redirect(url_for("workorders.wo_current"))

            flash("Profile saved.")
            return redirect(url_for("users.user_profile"))

        prefs = None
        if existing:
            prefs = conn.execute("""
                SELECT * FROM profile_preferences WHERE user_key = ?
            """, (user["user_key"],)).fetchone()

        return render_template(
            "create_profile.html",
            prefs=prefs,
            timezones=get_timezones(),
            status_text=user_status_text(user["user_key"]),
            **get_nav_context()
        )
    finally:
        conn.close()

@users_bp.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    try:
        raw_users = conn.execute("""
            SELECT ia.user_key, la.user_id,
                   COALESCE(pp.full_name, '') AS full_name,
                   COALESCE(pp.display_name, '') AS display_name
            FROM internal_account ia
            JOIN login_auth la ON la.user_key = ia.user_key
            LEFT JOIN profile_preferences pp ON pp.user_key = ia.user_key
            ORDER BY la.user_id ASC
        """).fetchall()

        users = []
        for row in raw_users:
            user_dict = dict(row)
            user_dict["roles"] = conn.execute("""
                SELECT ur.role_key, ur.role_name, ur.role_perm
                FROM account_roles ar
                JOIN user_roles ur ON ur.role_key = ar.role_key
                WHERE ar.user_key = ?
                ORDER BY ur.role_key ASC
            """, (row["user_key"],)).fetchall()
            users.append(user_dict)

        return render_template(
            "admin_users.html",
            users=users,
            **get_nav_context()
        )
    finally:
        conn.close()

@users_bp.route("/admin/user/<int:user_key>", methods=["GET", "POST"])
@admin_required
def admin_user_edit(user_key):
    conn = get_db()
    try:
        user = conn.execute("""
            SELECT ia.user_key, la.user_id
            FROM internal_account ia
            JOIN login_auth la ON la.user_key = ia.user_key
            WHERE ia.user_key = ?
        """, (user_key,)).fetchone()

        if not user:
            flash("User not found.")
            return redirect(url_for("users.admin_users"))

        prefs = conn.execute("""
            SELECT * FROM profile_preferences WHERE user_key = ?
        """, (user_key,)).fetchone()

        all_roles = conn.execute("""
            SELECT role_key, role_name, role_perm
            FROM user_roles
            ORDER BY role_key ASC
        """).fetchall()

        assigned_role_keys = {
            int(r["role_key"])
            for r in conn.execute(
                "SELECT role_key FROM account_roles WHERE user_key = ?",
                (user_key,)
            ).fetchall()
        }

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            display_name = request.form.get("display_name", "").strip()

            if not all([full_name, display_name]):
                flash("Full Name and Display Name are required.")
                return redirect(url_for("users.admin_user_edit", user_key=user_key))

            if prefs:
                conn.execute("""
                    UPDATE profile_preferences
                    SET full_name = ?, display_name = ?
                    WHERE user_key = ?
                """, (full_name, display_name, user_key))
            else:
                conn.execute("""
                    INSERT INTO profile_preferences
                    (user_key, full_name, display_name, timezone, theme, default_view)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_key, full_name, display_name, "UTC", "light", "option1"))

            conn.execute("DELETE FROM account_roles WHERE user_key = ?", (user_key,))

            status_role = request.form.get("status_role", "").strip()
            if status_role:
                conn.execute(
                    "INSERT OR IGNORE INTO account_roles (user_key, role_key) VALUES (?, ?)",
                    (user_key, status_role)
                )

            conn.commit()
            flash("User updated.")
            return redirect(url_for("users.admin_users"))

        return render_template(
            "admin_user_edit.html",
            user=user,
            prefs=prefs,
            all_roles=all_roles,
            assigned_role_keys=assigned_role_keys,
            status_text=user_status_text(user_key),
            **get_nav_context()
        )
    finally:
        conn.close()
