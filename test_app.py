import os
import tempfile

os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "test.db"), DEMO="0",
                  ADMIN_USER="admin", ADMIN_PASSWORD="secret", SECRET_KEY="test")

import pytest  # noqa: E402

import app as bookapp  # noqa: E402


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
    r = post(client, "/book/new", title="Der Zauberberg", author="Thomas Mann", year="1924",
             description="Davos", rating="4", action="save")
    assert "Der Zauberberg" in r.text
    assert "Der Zauberberg" in client.get("/?q=davos").text
    assert "Der Zauberberg" not in client.get("/?q=Kafka").text

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


def test_normalize_isbn():
    assert bookapp.normalize_isbn("3-499-22572-x") == "349922572X"
    assert bookapp.normalize_isbn("123") is None
    assert bookapp.format_isbn("9783499225727") == "978-3-499-22572-7"
    assert bookapp.format_isbn("349922572X") == "349922572X"  # falsche Prüfziffer bleibt unverändert
