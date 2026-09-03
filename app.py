# ---------- app.py ----------
# Work Order System (Flask 3.x compatible)
from flask import Flask, render_template, request, redirect, url_for
import sqlite3, os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo   # built-in from Python 3.9+

app = Flask(__name__)

def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")

app.config["TEMPLATES_AUTO_RELOAD"] = env_bool("TEMPLATES_AUTO_RELOAD", False)

# ----------------------------------------------------------------------
# LOCAL TIMEZONE DETECTION
# ----------------------------------------------------------------------
# Try to detect the host's local time zone automatically.
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
    return conn

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

    # Login/auth table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_auth (
            user_key INTEGER NOT NULL,
            auth_provider TEXT NOT NULL,
            user_id TEXT NOT NULL,
            password_hash TEXT,
            PRIMARY KEY (user_key),
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key)
        )
    """)

    # Profile/preferences table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile_preferences (
            user_key INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            timezone TEXT NOT NULL,
            theme TEXT NOT NULL,
            default_view TEXT NOT NULL,
            PRIMARY KEY (user_key),
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key)
        )
    """)

    # Role definitions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            role_key INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT NOT NULL,
            role_desc TEXT NOT NULL,
            role_perm TEXT NOT NULL
        )
    """)

    # User-role link table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_roles (
            user_key INTEGER NOT NULL,
            role_key INTEGER NOT NULL,
            PRIMARY KEY (user_key, role_key),
            FOREIGN KEY (user_key) REFERENCES internal_account(user_key),
            FOREIGN KEY (role_key) REFERENCES user_roles(role_key)
        )
    """)

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
        # %I gives 12-hour time with leading zero → strip() removes it safely
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return ''

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
                 AND needed <= strftime('%Y-%m-%dT%H:%M') THEN 0   -- Past due first
            WHEN needed IS NOT NULL
                 AND TRIM(needed) != '' THEN 1                      -- Future scheduled
            ELSE 2                                                  -- No needed date → last
          END,
          needed ASC,
          submitted ASC
    """).fetchall()
    conn.close()
    return render_template("index.html", workorders=wos, now=datetime.now(LOCAL_TZ), soon = datetime.now(LOCAL_TZ) + timedelta(hours=72))

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
    return render_template("completed.html", workorders=wos)

@app.route("/add", methods=["POST"])
def add():
    """Insert new work order."""
    subject = request.form["subject"]
    body = request.form["body"]
    room = request.form.get("room")
    needed = request.form.get("needed")
    requested_by = request.form.get("requested_by")

    # Local timestamp for this host system
    now_local = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")

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
    return render_template("edit.html", wo=wo)

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

    # Local timestamp for last_update
    ts = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")

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

# ----------------------------------------------------------------------
# APP LAUNCHER
# ----------------------------------------------------------------------
if __name__ == "__main__":
    debug = env_bool("FLASK_DEBUG", False)
    app.run(host="0.0.0.0", port=8080, debug=debug)
# ---------- end app.py ----------
