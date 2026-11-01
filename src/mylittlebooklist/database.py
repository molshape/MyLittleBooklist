"""SQLite connection, schema setup and migrations."""

import os
import secrets
import sqlite3
from typing import cast

from flask import current_app, g
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("DB_PATH", "books.db")


def db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return cast(sqlite3.Connection, g.db)


def close_db(_exc: BaseException | None) -> None:
    if (conn := g.pop("db", None)) is not None:
        conn.close()


def remove_orphans() -> None:
    db().execute("DELETE FROM books WHERE id NOT IN (SELECT book_id FROM user_books)")


# Schema changes for existing databases, entry n brings a database to version n (PRAGMA
# user_version). Append only, never edit or reorder entries, and update schema.sql as well
# so new databases start in the final state.
MIGRATIONS: list[str] = []


def migrate() -> None:
    version: int = db().execute("PRAGMA user_version").fetchone()[0]
    if version > len(MIGRATIONS):
        raise RuntimeError(f"Database version {version} is newer than this app supports")
    if version == len(MIGRATIONS):
        return
    backup = sqlite3.connect(f"{DB_PATH}.v{version}.bak")
    db().backup(backup)
    backup.close()
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        try:
            # One transaction per step: a failing step leaves the database at version i - 1
            db().executescript(f"BEGIN; {sql}; PRAGMA user_version = {i}; COMMIT;")
        except sqlite3.Error:
            db().rollback()
            raise
        current_app.logger.info("Database migrated to version %d", i)


def init_db() -> None:
    is_new = not db().execute("SELECT 1 FROM sqlite_master WHERE name = 'users'").fetchone()
    with open(os.path.join(current_app.root_path, "schema.sql"), encoding="utf-8") as f:
        db().executescript(f.read())
    if is_new:
        db().execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
    migrate()
    if db().execute("SELECT 1 FROM users").fetchone():
        return
    name = os.environ.get("ADMIN_USER", "admin")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(12)
        current_app.logger.warning(
            "ADMIN_PASSWORD not set – generated for '%s': %s", name, password
        )
    db().execute(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
        (name, generate_password_hash(password)),
    )
    db().commit()
