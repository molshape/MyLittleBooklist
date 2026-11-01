import time

import pytest

from mylittlebooklist import database, demo, openlibrary
from mylittlebooklist.app import app


def test_demo_ratios() -> None:
    # Demo: per user 80 % owned, 60 % read; ratings only for read books
    for user in demo.DEMO_USERS:
        entries = [users[user] for *_, users in demo.DEMO_BOOKS if user in users]
        assert len(entries) == 10
        assert sum(owned for _, _, owned in entries) == 8
        assert sum(read for _, read, _ in entries) == 6
        assert all(read for rating, read, _ in entries if rating)


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
