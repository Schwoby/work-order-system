# ---------- app.py ----------
# Work Order System (Flask 3.x compatible)
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo   # built-in from Python 3.9+
from werkzeug.security import generate_password_hash, check_password_hash

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

def init_db():
    """Ensure all tables exist using current schema."""
    conn = get_db()

    # Existing workorders table
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

    # Internal account table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS internal_account (
            user_key INTEGER PRIMARY KEY AUTOINCREMENT,
            created_date TEXT NOT NULL,
            role_date TEXT,
            last_login TEXT
        )
    """)

    # User roles table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            role_key INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT NOT NULL,
            role_perm INTEGER NOT NULL
        )
    """)

    # Login/auth table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_auth (
            user_key INTEGER PRIMARY KEY,
            auth_provider TEXT NOT NULL,
            user_id TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key) ON DELETE CASCADE
        )
    """)

    # Profile/preferences table
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

    # User-role link table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_roles (
            user_key INTEGER NOT NULL,
            role_key INTEGER NOT NULL,
            PRIMARY KEY (user_key, role_key),
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key) ON DELETE CASCADE,
            FOREIGN KEY (role_key) REFERENCES user_roles(role_key)
        )
    """)

    # Seed default roles if table is empty
    existing_roles = conn.execute("SELECT COUNT(*) AS cnt FROM user_roles").fetchone()["cnt"]
    if existing_roles == 0:
        conn.executemany("""
            INSERT INTO user_roles (role_key, role_name, role_perm)
            VALUES (?, ?, ?)
        """, [
            (1, "pending", 0),
            (2, "suspended", 0),
            (3, "rejected", 0),
            (4, "admin", 1),
            (5, "submitter", 2),
            (6, "fulfiller", 3),
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
        (user_id_lower,)
    ).fetchone()
    return row is not None

def is_first_user(conn):
    row = conn.execute("SELECT COUNT(*) AS cnt FROM internal_account").fetchone()
    return row["cnt"] == 0

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

        created_date = now_local_str()
        password_hash = generate_password_hash(password)
        password = None

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO internal_account (created_date, role_date, last_login) VALUES (?, ?, ?)",
            (created_date, None, None)
        )
        user_key = cur.lastrowid

        cur.execute(
            """
            INSERT INTO login_auth (user_key, auth_provider, user_id, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (user_key, "local", email_clean, password_hash)
        )

        role_name = "admin" if is_first_user(conn) else "pending"
        role_key = get_role_key(conn, role_name)
        if role_key is None:
            raise RuntimeError(f"Role '{role_name}' not found.")

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
        password_hash = None

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

        ts = now_local_str()
        conn.execute(
            "UPDATE internal_account SET last_login = ? WHERE user_key = ?",
            (ts, row["user_key"])
        )
        conn.commit()
        return True, row["user_key"]

    finally:
        conn.close()

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

# ----------------------------------------------------------------------
# ROUTES
# ----------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

@app.route("/")
def index():
    """Show all open (not completed) work orders; order: past due → scheduled → no date."""
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
        "index.html",
        workorders=wos,
        now=datetime.now(LOCAL_TZ),
        soon=datetime.now(LOCAL_TZ) + timedelta(hours=72),
        current_user=get_current_user()
    )

@app.route("/completed")
def completed():
    """Show completed work orders."""
    conn = get_db()
    wos = conn.execute("""
        SELECT * FROM workorders
        WHERE completed = 1
        ORDER BY last_update DESC
    """).fetchall()
    conn.close()
    return render_template("completed.html", workorders=wos, current_user=get_current_user())

@app.route("/add", methods=["POST"])
def add():
    """Insert new work order."""
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
    return redirect(url_for("index"))

@app.route("/edit/<int:wo_id>")
def edit(wo_id):
    """Edit page."""
    conn = get_db()
    wo = conn.execute("SELECT * FROM workorders WHERE id = ?", (wo_id,)).fetchone()
    conn.close()
    return render_template("edit.html", wo=wo, current_user=get_current_user())

@app.route("/update/<int:wo_id>", methods=["POST"])
def update(wo_id):
    """Update an existing work order."""
    completed = 1 if request.form.get("completed") == "on" else 0
    subject = request.form["subject"]
    body = request.form["body"]
    room = request.form.get("room")
    needed = request.form.get("needed")
    requested_by = request.form.get("requested_by")
    completion_text = request.form.get("completion_text")

    ts = now_local_str()

    conn = get_db()
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
    conn.close()
    return redirect(url_for("index"))

# ---------------- USER MANAGEMENT ROUTES ----------------

@app.route("/user/create", methods=["GET", "POST"])
def user_create():
    if request.method == "POST":
        email = request.form.get("user_id", "")
        password = request.form.get("password", "")
        verify_password = request.form.get("verify_password", "")

        if password != verify_password:
            flash("Passwords do not match.")
            return redirect(url_for("user_create"))

        success, result = create_user_account(email, password)
        if not success:
            flash(str(result))
            return redirect(url_for("user_create"))

        session["user_key"] = result
        flash("Account created successfully. Please complete your profile.")
        return redirect(url_for("user_profile"))

    return render_template("user_create.html", current_user=get_current_user())

@app.route("/user/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        email = request.form.get("user_id", "")
        password = request.form.get("password", "")

        success, result = authenticate_user(email, password)
        if not success:
            flash(str(result))
            return redirect(url_for("user_login"))

        session["user_key"] = result
        return redirect(url_for("index"))

    return render_template("user_login.html", current_user=get_current_user())

@app.route("/user/logout")
def user_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/user/profile", methods=["GET", "POST"])
def user_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("user_login"))

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
                return redirect(url_for("user_profile"))

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
            flash("Profile saved.")
            return redirect(url_for("index"))

        prefs = None
        if existing:
            prefs = conn.execute("""
                SELECT * FROM profile_preferences WHERE user_key = ?
            """, (user["user_key"],)).fetchone()

        return render_template(
            "user_profile.html",
            current_user=user,
            prefs=prefs,
            timezones=get_timezones()
        )
    finally:
        conn.close()

@app.route("/user/edit/<int:user_key>", methods=["GET", "POST"])
def user_edit(user_key):
    conn = get_db()
    try:
        user = conn.execute("""
            SELECT ia.user_key, la.user_id, la.auth_provider
            FROM internal_account ia
            JOIN login_auth la ON la.user_key = ia.user_key
            WHERE ia.user_key = ?
        """, (user_key,)).fetchone()

        if not user:
            flash("User not found.")
            return redirect(url_for("user_login"))

        prefs = conn.execute("""
            SELECT * FROM profile_preferences WHERE user_key = ?
        """, (user_key,)).fetchone()

        if request.method == "POST":
            new_email = normalize_email(request.form.get("user_id", ""))
            new_password = request.form.get("password", "")
            verify_password = request.form.get("verify_password", "")
            full_name = request.form.get("full_name", "").strip()
            display_name = request.form.get("display_name", "").strip()
            timezone = request.form.get("timezone", "").strip()
            theme = request.form.get("theme", "").strip()
            default_view = request.form.get("default_view", "").strip()

            if not is_valid_email(new_email):
                flash("Please enter a valid email address.")
                return redirect(url_for("user_edit", user_key=user_key))

            email_owner = conn.execute("""
                SELECT user_key FROM login_auth
                WHERE LOWER(user_id) = ? AND user_key != ?
                LIMIT 1
            """, (new_email, user_key)).fetchone()
            if email_owner:
                flash("That email address is already registered to another user.")
                return redirect(url_for("user_edit", user_key=user_key))

            if new_password or verify_password:
                if new_password != verify_password:
                    flash("Passwords do not match.")
                    return redirect(url_for("user_edit", user_key=user_key))
                if not password_meets_rules(new_password):
                    flash(
                        "Password must be at least 8 characters and include "
                        "1 uppercase letter, 1 lowercase letter, 1 number, and 1 special character "
                        "from: ! - _ ( ) ."
                    )
                    return redirect(url_for("user_edit", user_key=user_key))

                password_hash = generate_password_hash(new_password)
                conn.execute("""
                    UPDATE login_auth
                    SET user_id = ?, password_hash = ?
                    WHERE user_key = ?
                """, (new_email, password_hash, user_key))
                new_password = None
                password_hash = None
            else:
                conn.execute("""
                    UPDATE login_auth
                    SET user_id = ?
                    WHERE user_key = ?
                """, (new_email, user_key))

            if not all([full_name, display_name, timezone, theme, default_view]):
                flash("All profile fields are required.")
                return redirect(url_for("user_edit", user_key=user_key))

            if prefs:
                conn.execute("""
                    UPDATE profile_preferences
                    SET full_name = ?, display_name = ?, timezone = ?, theme = ?, default_view = ?
                    WHERE user_key = ?
                """, (full_name, display_name, timezone, theme, default_view, user_key))
            else:
                conn.execute("""
                    INSERT INTO profile_preferences
                    (user_key, full_name, display_name, timezone, theme, default_view)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_key, full_name, display_name, timezone, theme, default_view))

            conn.commit()
            flash("User updated.")
            return redirect(url_for("user_profile"))

        return render_template(
            "user_edit.html",
            current_user=get_current_user(),
            user=user,
            prefs=prefs,
            timezones=get_timezones()
        )
    finally:
        conn.close()

# ----------------------------------------------------------------------
# APP LAUNCHER
# ----------------------------------------------------------------------
if __name__ == "__main__":
    debug = env_bool("FLASK_DEBUG", False)
    app.run(host="0.0.0.0", port=8080, debug=debug)
# ---------- end app.py ----------
