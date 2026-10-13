import os
import sqlite3

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _column_exists(conn, table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)

def _ensure_column(conn, table_name, column_name, column_type, default_sql=None):
    if _column_exists(conn, table_name, column_name):
        return
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
    if default_sql is not None:
        sql += f" DEFAULT {default_sql}"
    conn.execute(sql)

def _get_initial_user_id(conn):
    row = conn.execute("""
        SELECT user_id
        FROM login_auth
        WHERE user_key = 1
    """).fetchone()
    return row["user_id"] if row else ""

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
            (3, "fulfiller", 2),
            (4, "admin", 3),
            (5, "suspended", 0),
            (6, "rejected", 0),
        ])

    _ensure_column(conn, "workorders", "requested_for", "TEXT")
    _ensure_column(conn, "workorders", "completed_by", "TEXT")

    initial_user_id = _get_initial_user_id(conn)

    # Move old requested_by content into requested_for if requested_for is blank.
    conn.execute("""
        UPDATE workorders
        SET requested_for = requested_by
        WHERE (requested_for IS NULL OR TRIM(requested_for) = '')
          AND requested_by IS NOT NULL
          AND TRIM(requested_by) != ''
    """)

    # Populate requested_by for all existing rows with the initial user's user_id.
    if initial_user_id:
        conn.execute("""
            UPDATE workorders
            SET requested_by = ?
            WHERE requested_by IS NULL OR TRIM(requested_by) = ''
        """, (initial_user_id,))

        conn.execute("""
            UPDATE workorders
            SET completed_by = ?
            WHERE completed = 1
              AND (completed_by IS NULL OR TRIM(completed_by) = '')
        """, (initial_user_id,))

    conn.commit()
    conn.close()
