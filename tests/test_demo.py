import time

import pytest

from mylittlebooklist import database, demo, openlibrary
from mylittlebooklist.app import app


def test_demo_ratios() -> None:
    # Demo: per user 80 % owned, 60 % read, 80 % in a category; ratings only for read books
    for user in demo.DEMO_USERS:
        entries = [users[user] for *_, users in demo.DEMO_BOOKS if user in users]
        assert len(entries) == 10
        assert sum(owned for _, _, owned, _ in entries) == 8
        assert sum(read for _, read, _, _ in entries) == 6
        assert all(read for rating, read, _, _ in entries if rating)
        assert sum(bool(categories) for *_, categories in entries) == 8
        assert sum(len(categories) == 2 for *_, categories in entries) in (2, 3)


def test_demo_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openlibrary, "lookup_isbn", lambda isbn: None)  # offline, without cover
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with app.app_context():
        assert demo.seed() == ["demo", "anna"]
        assert demo.seed() == []  # second run creates no duplicates
        counts = (
            database.db()
            .execute(
                "SELECT u.username, COUNT(*) FROM user_books ub JOIN users u ON u.id = ub.user_id GROUP BY u.username"
            )
            .fetchall()
        )
    assert dict(map(tuple, counts)) == {"demo": 10, "anna": 10}


def test_demo_categories_are_added_to_existing_books(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openlibrary, "lookup_isbn", lambda isbn: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def count() -> int:
        return int(database.db().execute("SELECT COUNT(*) FROM user_book_categories").fetchone()[0])

    with app.app_context():
        demo.seed()
        expected = count()
        db = database.db()
        db.execute("DELETE FROM user_book_categories")
        db.execute(
            "INSERT INTO user_book_categories SELECT user_id, book_id, 'Eigene' FROM user_books LIMIT 1"
        )
        # A demo book with categories that was removed from the collection must not cause an error
        db.execute(
            """DELETE FROM user_books WHERE user_id = (SELECT id FROM users WHERE username = 'demo')
               AND book_id = (SELECT id FROM books WHERE isbn = '9780441172719')"""
        )
        db.commit()
        demo.seed()
        assert count() == expected  # one category less for the removed book, plus 'Eigene'
