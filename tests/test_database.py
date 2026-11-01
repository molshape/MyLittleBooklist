import os
import sqlite3
import tempfile

import pytest

from mylittlebooklist import database
from mylittlebooklist.app import app


def test_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "DB_PATH", os.path.join(tempfile.mkdtemp(), "old.db"))
    monkeypatch.setattr(database, "MIGRATIONS", [])

    def version() -> int:
        return int(database.db().execute("PRAGMA user_version").fetchone()[0])

    with app.app_context():
        database.init_db()
        assert version() == 0  # new database starts at the current version
        monkeypatch.setattr(
            database,
            "MIGRATIONS",
            [
                "ALTER TABLE books ADD COLUMN publisher TEXT",
                "ALTER TABLE books ADD COLUMN broken TEXT; SELECT * FROM missing",
            ],
        )
        with pytest.raises(sqlite3.OperationalError):
            database.init_db()
        assert version() == 1  # first step kept, failed step rolled back
        columns = [row[1] for row in database.db().execute("PRAGMA table_info(books)")]
        assert "publisher" in columns and "broken" not in columns
        assert os.path.exists(database.DB_PATH + ".v0.bak")

        monkeypatch.setattr(database, "MIGRATIONS", [])
        with pytest.raises(RuntimeError):  # older app must not touch a newer database
            database.init_db()

    monkeypatch.setattr(database, "DB_PATH", os.path.join(tempfile.mkdtemp(), "new.db"))
    monkeypatch.setattr(database, "MIGRATIONS", ["ALTER TABLE missing ADD COLUMN never_run TEXT"])
    with app.app_context():
        database.init_db()
        assert version() == 1  # new database skips existing migrations
        assert not os.path.exists(database.DB_PATH + ".v0.bak")


def test_categories_migration_keeps_data() -> None:
    with app.app_context():
        conn = database.db()
        conn.execute("INSERT INTO books (id, title) VALUES (1, 'Alt')")
        conn.execute("INSERT INTO user_books (user_id, book_id) VALUES (1, 1)")
        conn.commit()
        conn.executescript("DROP TABLE user_book_categories; PRAGMA user_version = 0")

        database.init_db()

        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(database.MIGRATIONS)
        assert conn.execute("SELECT COUNT(*) FROM user_book_categories").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_books").fetchone()[0] == 1
        assert os.path.exists(database.DB_PATH + ".v0.bak")
