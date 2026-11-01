import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mylittlebooklist import openlibrary
from tests.helpers import login, post


def add_book(client: FlaskClient) -> TestResponse:
    return post(
        client,
        "/book/new",
        title="Der Zauberberg",
        author="Thomas Mann",
        year="1924",
        description="Davos",
        rating="4",
        is_owned="on",
        action="save",
    )


def test_new_book_is_owned_by_default(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    assert 'name="is_owned" checked' in client.get("/book/new").text


def test_create_and_search(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    assert "Der Zauberberg" in add_book(client).text
    assert "Der Zauberberg" in client.get("/?q=davos").text
    assert "Der Zauberberg" not in client.get("/?q=Kafka").text


def test_flags_and_filters(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_book(client)
    assert "Der Zauberberg" not in client.get("/?read=1").text
    post(client, "/book/1/flag/read", value="1")
    assert "Der Zauberberg" in client.get("/?read=1&q=mann").text
    assert "Der Zauberberg" not in client.get("/?read=0").text
    post(client, "/book/1/flag/owned")  # switch off -> no value
    assert "Der Zauberberg" in client.get("/?owned=0").text
    with client.session_transaction() as s:
        assert client.post("/book/1/flag/rating", data={"csrf": s["csrf"]}).status_code == 404


def test_isbn_lookup_prefills_form(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client, "admin", "secret")
    monkeypatch.setattr(
        openlibrary,
        "lookup_isbn",
        lambda isbn: {
            "title": "Der Process",
            "author": "Franz Kafka",
            "year": 1925,
            "cover_url": "",
        },
    )
    r = post(client, "/book/new", isbn="978-3-596-90614-2", title="", action="lookup")
    assert 'value="Der Process"' in r.text and 'value="9783596906142"' in r.text


def test_shared_catalog(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_book(client)
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")

    # bob doesn't see admin's book in his collection...
    assert "Der Zauberberg" not in client.get("/").text
    # ...but finds it in the shared catalog, can view it, but not rate or edit it
    assert "Der Zauberberg" in client.get("/?all=1").text
    assert "Add to my collection" in client.get("/book/1").text
    with client.session_transaction() as s:
        assert client.post("/book/1/rate", data={"csrf": s["csrf"]}).status_code == 404
    assert client.get("/book/1/edit").status_code == 404
    post(client, "/book/1/add")
    assert "Der Zauberberg" in client.get("/").text


def test_unknown_book(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    assert client.get("/book/99").status_code == 404
