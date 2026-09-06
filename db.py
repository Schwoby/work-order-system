import os
import sqlite3

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

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
