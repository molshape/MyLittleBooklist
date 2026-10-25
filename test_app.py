import os
import tempfile

os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "test.db"),
                  ADMIN_USER="admin", ADMIN_PASSWORD="secret", SECRET_KEY="test")

import pytest  # noqa: E402

import app as bookapp  # noqa: E402
import demo  # noqa: E402


@pytest.fixture
def client():
    bookapp.app.config["TESTING"] = True
    return bookapp.app.test_client()


def csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s["csrf"]


def login(client, user, password):
    return client.post("/login", data={"username": user, "password": password, "csrf": csrf(client)})


def post(client, url, **data):
    with client.session_transaction() as s:
        data["csrf"] = s["csrf"]
    return client.post(url, data=data, follow_redirects=True)


def test_flow(client, monkeypatch):
    assert client.get("/").status_code == 302  # Login nötig
    assert client.post("/login", data={"username": "admin", "password": "secret"}).status_code == 400  # CSRF

    login(client, "admin", "secret")
    with client.session_transaction() as s:
        old_token = s["csrf"]
        assert s.permanent
    post(client, "/users", username="bob", password="bobpw")

    # Manuelles Buch anlegen und finden
    assert 'name="is_owned" checked' in client.get("/book/new").text  # Default: in Besitz
    r = post(client, "/book/new", title="Der Zauberberg", author="Thomas Mann", year="1924",
             description="Davos", rating="4", is_owned="on", action="save")
    assert "Der Zauberberg" in r.text
    assert "Der Zauberberg" in client.get("/?q=davos").text
    assert "Der Zauberberg" not in client.get("/?q=Kafka").text

    # Flags umschalten und filtern (auch kombiniert mit Suche)
    assert "Der Zauberberg" not in client.get("/?read=1").text
    post(client, "/book/1/flag/read", value="1")
    assert "Der Zauberberg" in client.get("/?read=1&q=mann").text
    assert "Der Zauberberg" not in client.get("/?read=0").text
    post(client, "/book/1/flag/owned")  # Switch aus -> kein value
    assert "Der Zauberberg" in client.get("/?owned=0").text
    with client.session_transaction() as s:
        assert client.post("/book/1/flag/rating", data={"csrf": s["csrf"]}).status_code == 404

    # ISBN-Lookup (OpenLibrary gemockt) füllt das Formular vor
    monkeypatch.setattr(bookapp, "lookup_isbn", lambda isbn: {
        "title": "Der Process", "author": "Franz Kafka", "year": 1925, "cover_url": ""})
    r = post(client, "/book/new", isbn="978-3-596-90614-2", title="", action="lookup")
    assert 'value="Der Process"' in r.text and 'value="9783596906142"' in r.text

    # Neuer Login erneuert das CSRF-Token; bob sieht admins Buch nicht
    client.post("/logout", data={"csrf": old_token})
    login(client, "bob", "bobpw")
    with client.session_transaction() as s:
        assert s["csrf"] != old_token
    assert "Der Zauberberg" not in client.get("/").text
    assert client.get("/book/1").status_code == 404
    assert client.get("/users").status_code == 403


def test_demo_ratios():
    # Demo: je User 80 % in Besitz, 60 % gelesen; Bewertung nur für gelesene Bücher
    for user in demo.DEMO_USERS:
        entries = [users[user] for *_, users in demo.DEMO_BOOKS if user in users]
        assert len(entries) == 10
        assert sum(owned for _, _, owned in entries) == 8
        assert sum(read for _, read, _ in entries) == 6
        assert all(read for rating, read, _ in entries if rating)


def test_demo_seed(monkeypatch):
    monkeypatch.setattr(bookapp, "DB_PATH", os.path.join(tempfile.mkdtemp(), "demo.db"))
    monkeypatch.setattr(bookapp, "lookup_isbn", lambda isbn: None)  # offline, ohne Cover
    monkeypatch.setattr(demo.time, "sleep", lambda s: None)
    with bookapp.app.app_context():
        bookapp.init_db()
        assert demo.seed() == ["demo", "anna"]
        assert demo.seed() == []  # zweiter Lauf legt nichts doppelt an
        counts = bookapp.db().execute(
            "SELECT u.username, COUNT(*) FROM user_books ub JOIN users u ON u.id = ub.user_id GROUP BY u.username").fetchall()
    assert dict(map(tuple, counts)) == {"demo": 10, "anna": 10}


def test_normalize_isbn():
    assert bookapp.normalize_isbn("3-499-22572-x") == "349922572X"
    assert bookapp.normalize_isbn("123") is None
    assert bookapp.format_isbn("9783499225727") == "978-3-499-22572-7"
    assert bookapp.format_isbn("349922572X") == "349922572X"  # falsche Prüfziffer bleibt unverändert
