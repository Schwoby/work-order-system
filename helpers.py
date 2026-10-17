import os
import re
import time
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import session, redirect, url_for, flash

from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db

def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")

# ----------------------------------------------------------------------
# LOCAL TIMEZONE DETECTION
# ----------------------------------------------------------------------
try:
    LOCAL_TZ = ZoneInfo.local()
except AttributeError:
    tz_name = os.environ.get("TZ")
    LOCAL_TZ = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")

# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
PASSWORD_REGEX = re.compile(
    r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!\-_().])[A-Za-z\d!\-_().]{8,}$"
)

def epoch_now():
    return int(time.time())

def normalize_email(email):
    return (email or "").strip().lower()

def is_valid_email(email):
    email = email or ""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

def password_meets_rules(password):
    return bool(PASSWORD_REGEX.match(password or ""))

def get_role_key(conn, role_name):
    row = conn.execute(
        "SELECT role_key FROM user_roles WHERE role_name = ?",
        (role_name,)
    ).fetchone()
    return row["role_key"] if row else None

def user_exists_by_email(conn, user_id_lower):
    row = conn.execute(
        "SELECT 1 FROM login_auth WHERE LOWER(user_id) = ? LIMIT 1",
        (user_id_lower,),
    ).fetchone()
    return row is not None

def first_user_role_name(conn):
    row = conn.execute("SELECT COUNT(*) AS cnt FROM login_auth").fetchone()
    return "admin" if row["cnt"] == 0 else "pending"

def get_current_user():
    user_key = session.get("user_key")
    if not user_key:
        return None

    conn = get_db()
    try:
        user = conn.execute("""
            SELECT ia.user_key, la.user_id, ia.created_date, ia.last_login
            FROM internal_account ia
            JOIN login_auth la ON la.user_key = ia.user_key
            WHERE ia.user_key = ?
        """, (user_key,)).fetchone()
        return user
    finally:
        conn.close()

def get_all_user_roles(user_key):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT ur.role_key, ur.role_name, ur.role_perm
            FROM account_roles ar
            JOIN user_roles ur ON ur.role_key = ar.role_key
            WHERE ar.user_key = ?
            ORDER BY ur.role_key ASC
        """, (user_key,)).fetchall()
        return rows
    finally:
        conn.close()

def get_effective_role_perm(user_key):
    roles = get_all_user_roles(user_key)
    perms = [int(r["role_perm"]) for r in roles]

    if 0 in perms:
        return 0
    if 3 in perms:
        return 3
    if 2 in perms:
        return 2
    if 1 in perms:
        return 1
    return None

def user_profile_complete(user_key):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM profile_preferences WHERE user_key = ?",
            (user_key,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()

def user_access_allowed(user_key):
    effective_perm = get_effective_role_perm(user_key)
    return effective_perm in (1, 2, 3)

def user_status_text(user_key):
    roles = get_all_user_roles(user_key)
    if not roles:
        return "Unknown"
    return ", ".join([r["role_name"].capitalize() for r in roles])

def get_timezones():
    return [
        "UTC",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Paris",
    ]

def get_current_user_theme():
    user = get_current_user()
    if not user:
        return "light"

    conn = get_db()
    try:
        row = conn.execute("""
            SELECT theme
            FROM profile_preferences
            WHERE user_key = ?
        """, (user["user_key"],)).fetchone()
        return row["theme"] if row and row["theme"] else "light"
    finally:
        conn.close()

def get_current_user_name_view():
    user = get_current_user()
    if not user:
        return "user_id"

    conn = get_db()
    try:
        row = conn.execute("""
            SELECT name_view
            FROM profile_preferences
            WHERE user_key = ?
        """, (user["user_key"],)).fetchone()
        return row["name_view"] if row and row["name_view"] else "user_id"
    finally:
        conn.close()

def get_requested_by(user_key_value):
    if not user_key_value:
        return ""

    conn = get_db()
    try:
        row = conn.execute("""
            SELECT la.user_id,
                   COALESCE(pp.full_name, '') AS full_name,
                   COALESCE(pp.display_name, '') AS display_name
            FROM login_auth la
            LEFT JOIN profile_preferences pp ON pp.user_key = la.user_key
            WHERE la.user_key = ?
        """, (user_key_value,)).fetchone()

        if not row:
            return str(user_key_value)

        name_view = get_current_user_name_view()
        if name_view == "user_name":
            return row["full_name"] or row["user_id"]
        if name_view == "display_name":
            return row["display_name"] or row["user_id"]
        return row["user_id"]
    finally:
        conn.close()

def get_nav_context():
    user = get_current_user()
    return {
        "current_user": user,
        "current_roles": get_all_user_roles(user["user_key"]) if user else [],
        "current_effective_perm": get_effective_role_perm(user["user_key"]) if user else None,
        "current_theme": get_current_user_theme(),
        "current_name_view": get_current_user_name_view(),
    }

def get_default_view_path(default_view):
    mapping = {
        "option1": "workorders.wo_current",
        "option2": "workorders.wo_create",
        "option3": "workorders.wo_completed",
    }
    return mapping.get(default_view, "workorders.wo_current")

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("users.index"))
        return view(*args, **kwargs)
    return wrapped

def active_access_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("users.index"))
        if not user_profile_complete(user["user_key"]):
            return redirect(url_for("users.create_profile"))

        effective_perm = get_effective_role_perm(user["user_key"])
        if effective_perm == 0 or effective_perm is None:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("users.user_profile"))

        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("users.index"))
        if not user_profile_complete(user["user_key"]):
            return redirect(url_for("users.create_profile"))

        effective_perm = get_effective_role_perm(user["user_key"])
        if effective_perm == 0 or effective_perm is None:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("users.user_profile"))
        if effective_perm != 3:
            flash("Admin access required.")
            return redirect(url_for("users.user_profile"))

        return view(*args, **kwargs)
    return wrapped

def create_user_account(email, password):
    email_clean = normalize_email(email)

    conn = get_db()
    try:
        if not is_valid_email(email_clean):
            return False, "Please enter a valid email address."

        if user_exists_by_email(conn, email_clean):
            return False, "That email address is already registered."

        if not password_meets_rules(password):
            return False, (
                "Password must be at least 8 characters and include "
                "1 uppercase letter, 1 lowercase letter, 1 number, and 1 special character "
                "from: ! - _ ( ) ."
            )

        role_name = first_user_role_name(conn)
        role_key = get_role_key(conn, role_name)
        if role_key is None:
            raise RuntimeError(f"Role '{role_name}' not found.")

        created_date = epoch_now()
        role_date = epoch_now()
        password_hash = generate_password_hash(password)

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO internal_account (created_date, role_date, last_login) VALUES (?, ?, ?)",
            (created_date, role_date, None)
        )
        user_key = cur.lastrowid

        cur.execute(
            """
            INSERT INTO login_auth (user_key, auth_provider, user_id, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (user_key, "local", email_clean, password_hash)
        )

        cur.execute(
            "INSERT INTO account_roles (user_key, role_key) VALUES (?, ?)",
            (user_key, role_key)
        )

        conn.commit()
        return True, user_key

    except sqlite3.IntegrityError as e:
        conn.rollback()
        return False, f"Database integrity error: {e}"
    except Exception as e:
        conn.rollback()
        return False, f"Error creating user: {e}"
    finally:
        conn.close()

def authenticate_user(email, password):
    email_clean = normalize_email(email)
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT ia.user_key, ia.last_login, la.password_hash, la.user_id
            FROM login_auth la
            JOIN internal_account ia ON ia.user_key = la.user_key
            WHERE LOWER(la.user_id) = ?
            LIMIT 1
        """, (email_clean,)).fetchone()

        if not row:
            return False, "Invalid login."

        if not check_password_hash(row["password_hash"], password or ""):
            return False, "Invalid login."

        ts = epoch_now()
        conn.execute(
            "UPDATE internal_account SET last_login = ? WHERE user_key = ?",
            (ts, row["user_key"])
        )
        conn.commit()
        return True, row["user_key"]

    finally:
        conn.close()

def parse_user_timezone():
    user = get_current_user()
    if not user:
        return ZoneInfo("UTC")

    conn = get_db()
    try:
        row = conn.execute("""
            SELECT timezone
            FROM profile_preferences
            WHERE user_key = ?
        """, (user["user_key"],)).fetchone()
        tz_name = row["timezone"] if row and row["timezone"] else "UTC"
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")
    finally:
        conn.close()

def epoch_to_local_dt(value, tz=None):
    if value is None or value == "":
        return None
    try:
        epoch_val = int(value)
    except (TypeError, ValueError):
        return None
    tz = tz or parse_user_timezone()
    return datetime.fromtimestamp(epoch_val, tz=timezone.utc).astimezone(tz)

def epoch_to_local_date(value, tz=None):
    dt = epoch_to_local_dt(value, tz)
    return dt.strftime("%m/%d/%Y") if dt else ""

def epoch_to_local_time(value, tz=None):
    dt = epoch_to_local_dt(value, tz)
    return dt.strftime("%I:%M %p").lstrip("0") if dt else ""

def local_datetime_str_to_epoch(value, tz=None):
    if not value:
        return None
    tz = tz or parse_user_timezone()
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        try:
            dt = datetime.fromisoformat(str(value).replace("T", " "))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return int(dt.astimezone(timezone.utc).timestamp())
