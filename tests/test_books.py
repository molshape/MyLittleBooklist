import io

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mylittlebooklist import database, openlibrary
from mylittlebooklist.app import app
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


def upload_cover(client: FlaskClient, filename: str, mime: str) -> None:
    with client.session_transaction() as s:
        data = {
            "csrf": s["csrf"],
            "title": "Mit Cover",
            "action": "save",
            "cover": (io.BytesIO(b"<svg onload='alert(1)'/>"), filename, mime),
        }
    client.post("/book/new", data=data, content_type="multipart/form-data")


def test_svg_upload_is_not_stored(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    upload_cover(client, "evil.svg", "image/svg+xml")
    with app.app_context():
        assert database.db().execute("SELECT cover FROM books").fetchone()["cover"] is None
    assert client.get("/cover/1").status_code == 404


def test_png_cover_is_served_without_sniffing(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    upload_cover(client, "cover.png", "image/png")
    r = client.get("/cover/1")
    assert r.status_code == 200 and r.content_type == "image/png"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_stored_svg_cover_is_not_served(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    upload_cover(client, "cover.png", "image/png")
    with app.app_context():
        database.db().execute("UPDATE books SET cover_mime = 'image/svg+xml'")
        database.db().commit()
    assert client.get("/cover/1").status_code == 404


def add_categorized(client: FlaskClient, title: str, *categories: str, **fields: str) -> None:
    with client.session_transaction() as s:
        data = {"csrf": s["csrf"], "title": title, "action": "save", **fields}
    client.post("/book/new", data={**data, "category": list(categories)})


def in_order(html: str, *texts: str) -> bool:
    positions = [html.index(text) for text in texts]
    return positions == sorted(positions)


def test_gallery_groups_books_on_sorted_shelves(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Ohne Regal")
    add_categorized(client, "Zebra", "Ärzte")
    add_categorized(client, "Ähren", "Ärzte")
    add_categorized(client, "Mitte", "Zoo")
    add_categorized(client, "Beta", "Bäume")
    assert in_order(
        client.get("/").text,
        'data-name="Ärzte"',
        'class="t">Ähren<',
        'class="t">Zebra<',
        'data-name="Bäume"',
        'data-name="Zoo"',
        ">No category<",
        'class="t">Ohne Regal<',
    )


def test_no_category_shelf_is_shown_from_the_start(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_book(client)
    assert in_order(client.get("/").text, 'data-name=""', ">No category<", "Der Zauberberg")


def test_gallery_without_books_has_no_shelf(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    assert "<details" not in client.get("/").text


def test_comma_separates_new_categories(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Buch", new_category="Krimi, Urlaub,")
    html = client.get("/").text
    assert 'data-name="Krimi"' in html and 'data-name="Urlaub"' in html


def test_book_on_two_shelves_counts_once(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Doppelt", "Krimi", "Urlaub")
    html = client.get("/").text
    assert 'data-name="Krimi"' in html and 'data-name="Urlaub"' in html
    assert html.count('class="t">Doppelt<') == 2
    assert "1 book" in html
    assert "Krimi, Urlaub" in client.get("/book/1").text


def test_new_category_reuses_existing_spelling(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    add_categorized(client, "Zwei", new_category=" krimi ")
    html = client.get("/").text
    assert 'data-name="Krimi"' in html and 'data-name="krimi"' not in html


def test_unchecking_removes_book_from_shelf(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Buch", "Krimi", "Urlaub")
    assert 'name="category" value="Krimi"' in client.get("/book/1/edit").text
    with client.session_transaction() as s:
        data = {"csrf": s["csrf"], "title": "Buch", "action": "save", "category": ["Urlaub"]}
    client.post("/book/1/edit", data=data)
    html = client.get("/").text
    assert 'data-name="Krimi"' not in html and 'data-name="Urlaub"' in html


def test_new_category_survives_form_error(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    r = post(client, "/book/new", title="", action="save", new_category="Neu")
    assert 'name="category" value="Neu"' in r.text


def test_categories_are_personal(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Buch", "Geheim")
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    assert "Geheim" not in client.get("/?all=1").text
    assert "Geheim" not in client.get("/book/1").text
    assert "Geheim" not in client.get("/book/new").text


def test_existing_isbn_only_categorizes_new_collection_entry(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    isbn = "9783596906142"
    add_categorized(client, "Buch", "Erste", isbn=isbn)
    add_categorized(client, "Buch", "Zweite", isbn=isbn)  # already in the collection: unchanged
    assert "Zweite" not in client.get("/book/1").text
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    add_categorized(client, "Buch", "Bobs", isbn=isbn)
    assert "Bobs" in client.get("/book/1").text


def test_removing_book_removes_its_categories(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Buch", "Krimi")
    post(client, "/book/1/remove")
    with app.app_context():
        count = database.db().execute("SELECT COUNT(*) FROM user_book_categories").fetchone()[0]
    assert count == 0
