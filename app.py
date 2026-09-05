# ---------- app.py ----------
# Work Order System (Flask 3.x compatible)
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo   # built-in from Python 3.9+
from werkzeug.security import generate_password_hash, check_password_hash
import time
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")

app.config["TEMPLATES_AUTO_RELOAD"] = env_bool("TEMPLATES_AUTO_RELOAD", False)

# ----------------------------------------------------------------------
# LOCAL TIMEZONE DETECTION
# ----------------------------------------------------------------------
try:
    LOCAL_TZ = ZoneInfo.local()  # Available in Python 3.13+
except AttributeError:
    tz_name = os.environ.get("TZ")
    LOCAL_TZ = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")

# ----------------------------------------------------------------------
# DATABASE SETUP
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def now_local_str():
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")

def epoch_now():
    return str(int(time.time()))

def init_db():
    """Ensure all tables exist using current schema."""
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS workorders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            room TEXT,
            needed DATETIME,
            requested_by TEXT,
            submitted TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            completion_text TEXT,
            last_update TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS internal_account (
            user_key INTEGER PRIMARY KEY AUTOINCREMENT,
            created_date TEXT NOT NULL,
            role_date TEXT,
            last_login TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            role_key INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT NOT NULL,
            role_perm INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_auth (
            user_key INTEGER PRIMARY KEY,
            auth_provider TEXT NOT NULL,
            user_id TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile_preferences (
            user_key INTEGER NOT NULL PRIMARY KEY,
            full_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            timezone TEXT NOT NULL,
            theme TEXT NOT NULL,
            default_view TEXT NOT NULL,
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_roles (
            user_key INTEGER NOT NULL,
            role_key INTEGER NOT NULL,
            PRIMARY KEY (user_key, role_key),
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key) ON DELETE CASCADE,
            FOREIGN KEY (role_key) REFERENCES user_roles(role_key)
        )
    """)

    existing_roles = conn.execute("SELECT COUNT(*) AS cnt FROM user_roles").fetchone()["cnt"]
    if existing_roles == 0:
        conn.executemany("""
            INSERT INTO user_roles (role_key, role_name, role_perm)
            VALUES (?, ?, ?)
        """, [
            (1, "pending", 0),
            (2, "submitter", 1),
            (3, "fulfiller", 1),
            (4, "admin", 2),
            (5, "suspended", 0),
            (6, "rejected", 0),
        ])

    conn.commit()
    conn.close()

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
init_db()

# ----------------------------------------------------------------------
# JINJA FILTERS
# ----------------------------------------------------------------------
@app.template_filter('format_needed_date')
def format_needed_date(value):
    if not value:
        return ''
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%b %d, %Y")
    except Exception:
        return value

@app.template_filter('format_needed_time')
def format_needed_time(value):
    if not value:
        return ''
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return ''

# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
PASSWORD_REGEX = re.compile(
    r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!\-_().])[A-Za-z\d!\-_().]{8,}$"
)

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
            ORDER BY ur.role_perm ASC, ur.role_name ASC
        """, (user_key,)).fetchall()
        return rows
    finally:
        conn.close()

def get_effective_role_perm(user_key):
    roles = get_all_user_roles(user_key)
    perms = [int(r["role_perm"]) for r in roles]

    if 0 in perms:
        return 0
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
    return effective_perm in (1, 2)

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

def get_nav_context():
    user = get_current_user()
    return {
        "current_user": user,
        "current_roles": get_all_user_roles(user["user_key"]) if user else [],
        "current_effective_perm": get_effective_role_perm(user["user_key"]) if user else None,
    }

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped

def active_access_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("index"))
        if not user_profile_complete(user["user_key"]):
            return redirect(url_for("create_profile"))

        effective_perm = get_effective_role_perm(user["user_key"])
        if effective_perm == 0:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("user_profile"))
        if effective_perm not in (1, 2):
            return redirect(url_for("user_profile"))

        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("index"))
        if not user_profile_complete(user["user_key"]):
            return redirect(url_for("create_profile"))

        effective_perm = get_effective_role_perm(user["user_key"])
        if effective_perm == 0:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("user_profile"))
        if effective_perm != 2:
            flash("Admin access required.")
            return redirect(url_for("user_profile"))

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

# ----------------------------------------------------------------------
# ROUTES
# ----------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        email = request.form.get("user_id", "")
        password = request.form.get("password", "")

        success, result = authenticate_user(email, password)
        if not success:
            flash(str(result))
            return redirect(url_for("index"))

        session["user_key"] = result
        if not user_profile_complete(result):
            return redirect(url_for("create_profile"))

        effective_perm = get_effective_role_perm(result)
        if effective_perm == 0:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("user_profile"))
        if effective_perm in (1, 2):
            flash("Login successful.")
            return redirect(url_for("wo_current"))

        flash("Your account does not have access to the work order system.")
        return redirect(url_for("user_profile"))

    if get_current_user():
        user = get_current_user()
        if not user_profile_complete(user["user_key"]):
            return redirect(url_for("create_profile"))

        effective_perm = get_effective_role_perm(user["user_key"])
        if effective_perm == 0:
            return redirect(url_for("user_profile"))
        if effective_perm in (1, 2):
            return redirect(url_for("wo_current"))

        return redirect(url_for("user_profile"))

    return render_template("user_login.html", **get_nav_context())

@app.route("/wo/current")
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

@app.route("/wo/create")
@active_access_required
def wo_create():
    return render_template("wo_create.html", **get_nav_context())

@app.route("/completed")
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

@app.route("/add", methods=["POST"])
@active_access_required
def add():
    user = get_current_user()
    effective_perm = get_effective_role_perm(user["user_key"])
    if effective_perm not in (1, 2):
        return redirect(url_for("user_profile"))

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
    return redirect(url_for("wo_current"))

@app.route("/edit/<int:wo_id>")
@active_access_required
def wo_edit(wo_id):
    conn = get_db()
    wo = conn.execute("SELECT * FROM workorders WHERE id = ?", (wo_id,)).fetchone()
    conn.close()
    return render_template("wo_edit.html", wo=wo, **get_nav_context())

@app.route("/update/<int:wo_id>", methods=["POST"])
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
            return redirect(url_for("wo_current"))

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
        return redirect(url_for("wo_current"))
    finally:
        conn.close()

@app.route("/user/create", methods=["GET", "POST"])
def user_create():
    if request.method == "POST":
        email = request.form.get("user_id", "")
        password = request.form.get("password", "")
        verify_password = request.form.get("verify_password", "")

        if not is_valid_email(email):
            flash("Please enter a valid email address.")
            return redirect(url_for("user_create"))

        if password != verify_password:
            flash("Passwords do not match.")
            return redirect(url_for("user_create"))

        success, result = create_user_account(email, password)
        if not success:
            flash(str(result))
            return redirect(url_for("user_create"))

        session["user_key"] = result
        if not user_profile_complete(result):
            return redirect(url_for("create_profile"))

        effective_perm = get_effective_role_perm(result)
        if effective_perm == 0:
            flash("Your account is blocked from accessing the work order system.")
            return redirect(url_for("user_profile"))
        if effective_perm in (1, 2):
            flash("Account created successfully.")
            return redirect(url_for("wo_current"))

        flash("Account created, but no work order access is available.")
        return redirect(url_for("user_profile"))

    return render_template("user_create.html", **get_nav_context())

@app.route("/user/logout")
@login_required
def user_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/user/profile", methods=["GET", "POST"])
@login_required
def user_profile():
    return redirect(url_for("create_profile"))

@app.route("/profile/create", methods=["GET", "POST"])
@login_required
def create_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("index"))

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
                return redirect(url_for("create_profile"))

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
                return redirect(url_for("user_profile"))

            if effective_perm in (1, 2):
                flash("Profile saved.")
                return redirect(url_for("wo_current"))

            flash("Profile saved.")
            return redirect(url_for("user_profile"))

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

@app.route("/admin/users")
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
            ORDER BY
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM account_roles ar
                        JOIN user_roles ur ON ur.role_key = ar.role_key
                        WHERE ar.user_key = ia.user_key AND ur.role_name = 'pending'
                    ) THEN 1
                    WHEN EXISTS (
                        SELECT 1
                        FROM account_roles ar
                        JOIN user_roles ur ON ur.role_key = ar.role_key
                        WHERE ar.user_key = ia.user_key AND ur.role_name = 'submitter'
                    ) THEN 2
                    WHEN EXISTS (
                        SELECT 1
                        FROM account_roles ar
                        JOIN user_roles ur ON ur.role_key = ar.role_key
                        WHERE ar.user_key = ia.user_key AND ur.role_name = 'fulfiller'
                    ) THEN 3
                    WHEN EXISTS (
                        SELECT 1
                        FROM account_roles ar
                        JOIN user_roles ur ON ur.role_key = ar.role_key
                        WHERE ar.user_key = ia.user_key AND ur.role_name = 'admin'
                    ) THEN 4
                    WHEN EXISTS (
                        SELECT 1
                        FROM account_roles ar
                        JOIN user_roles ur ON ur.role_key = ar.role_key
                        WHERE ar.user_key = ia.user_key AND ur.role_name = 'suspended'
                    ) THEN 5
                    WHEN EXISTS (
                        SELECT 1
                        FROM account_roles ar
                        JOIN user_roles ur ON ur.role_key = ar.role_key
                        WHERE ar.user_key = ia.user_key AND ur.role_name = 'rejected'
                    ) THEN 6
                    ELSE 7
                END,
                la.user_id ASC
        """).fetchall()

        users = []
        for row in raw_users:
            user_dict = dict(row)
            user_dict["roles"] = conn.execute("""
                SELECT ur.role_key, ur.role_name, ur.role_perm
                FROM account_roles ar
                JOIN user_roles ur ON ur.role_key = ar.role_key
                WHERE ar.user_key = ?
                ORDER BY ur.role_perm ASC, ur.role_name ASC
            """, (row["user_key"],)).fetchall()
            users.append(user_dict)

        return render_template(
            "admin_users.html",
            users=users,
            **get_nav_context()
        )
    finally:
        conn.close()

@app.route("/admin/user/<int:user_key>", methods=["GET", "POST"])
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
            return redirect(url_for("admin_users"))

        prefs = conn.execute("""
            SELECT * FROM profile_preferences WHERE user_key = ?
        """, (user_key,)).fetchone()

        all_roles = conn.execute("""
            SELECT role_key, role_name, role_perm
            FROM user_roles
            ORDER BY role_perm ASC, role_name ASC
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
                return redirect(url_for("admin_user_edit", user_key=user_key))

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
            access_roles = request.form.getlist("access_roles")

            if status_role:
                conn.execute(
                    "INSERT OR IGNORE INTO account_roles (user_key, role_key) VALUES (?, ?)",
                    (user_key, status_role)
                )

            for role_key in access_roles:
                conn.execute(
                    "INSERT OR IGNORE INTO account_roles (user_key, role_key) VALUES (?, ?)",
                    (user_key, role_key)
                )

            conn.commit()
            flash("User updated.")
            return redirect(url_for("admin_user_edit", user_key=user_key))

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

if __name__ == "__main__":
    debug = env_bool("FLASK_DEBUG", False)
    app.run(host="0.0.0.0", port=8080, debug=debug)
# ---------- end app.py ----------
