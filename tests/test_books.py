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
    assert "Der Zauberberg" in client.get("/?view=catalog").text
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


def test_flat_views_sort_by_title_without_shelves(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Zebra", "Krimi")
    add_categorized(client, "Ähren", "Urlaub")
    add_categorized(client, "Mitte")
    for view in ("books", "catalog"):
        html = client.get(f"/?view={view}").text
        assert "<details" not in html
        assert in_order(html, 'class="t">Ähren<', 'class="t">Mitte<', 'class="t">Zebra<')


def test_unknown_view_shows_shelves(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_book(client)
    assert "<details" in client.get("/?view=nonsense").text


def test_books_view_only_lists_own_books(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_book(client)
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    assert "Der Zauberberg" not in client.get("/?view=books").text


def test_search_keeps_view(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    hidden = 'form="search" name="view" value="catalog"'
    assert hidden in client.get("/?view=catalog").text
    assert 'name="view"' not in client.get("/").text


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
    assert "Geheim" not in client.get("/?view=catalog").text
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


def shelves_of(username: str = "admin") -> dict[str, set[str]]:
    """{category: titles} of a user's categorized books."""
    with app.app_context():
        rows = (
            database.db()
            .execute(
                """SELECT c.category, b.title FROM user_book_categories c
                   JOIN books b ON b.id = c.book_id JOIN users u ON u.id = c.user_id
                   WHERE u.username = ?""",
                (username,),
            )
            .fetchall()
        )
    shelves: dict[str, set[str]] = {}
    for row in rows:
        shelves.setdefault(row["category"], set()).add(row["title"])
    return shelves


def test_rename_category_moves_all_books(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    add_categorized(client, "Zwei", "Krimi", "Urlaub")
    r = post(client, "/category/rename", old="Krimi", new=" Thriller ")
    assert "Category renamed" in r.text
    assert shelves_of() == {"Thriller": {"Eins", "Zwei"}, "Urlaub": {"Zwei"}}


def test_rename_category_to_same_name_keeps_books(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    post(client, "/category/rename", old="Krimi", new="Krimi")
    assert shelves_of() == {"Krimi": {"Eins"}}


def test_rename_category_can_change_spelling(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "krimi")
    post(client, "/category/rename", old="krimi", new="Krimi")
    assert shelves_of() == {"Krimi": {"Eins"}}


def test_rename_category_merges_into_existing(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Beide", "Krimi", "Krimis")
    add_categorized(client, "Alt", "Krimis")
    add_categorized(client, "Ziel", "Krimi")
    r = post(client, "/category/rename", old="Krimis", new="krimi")
    assert "Category merged" in r.text
    assert shelves_of() == {"Krimi": {"Beide", "Alt", "Ziel"}}


@pytest.mark.parametrize("new", ["", "   ", "Krimi, Urlaub"])
def test_rename_category_rejects_invalid_names(client: FlaskClient, new: str) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    r = post(client, "/category/rename", old="Krimi", new=new)
    assert "must not be empty" in r.text
    assert shelves_of() == {"Krimi": {"Eins"}}


def test_category_actions_need_an_existing_category(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins")
    assert post(client, "/category/rename", old="", new="Neu").status_code == 404
    assert post(client, "/category/delete", name="Fremd").status_code == 404


def test_delete_category_keeps_books(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Nur hier", "Krimi")
    add_categorized(client, "Auch dort", "Krimi", "Urlaub")
    r = post(client, "/category/delete", name="Krimi")
    assert "Category “Krimi” deleted" in r.text
    assert shelves_of() == {"Urlaub": {"Auch dort"}}
    assert in_order(r.text, 'data-name="Urlaub"', 'data-name=""', 'class="t">Nur hier<')


def test_category_actions_only_affect_own_categories(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/users", username="bob", password="bobpw")
    add_categorized(client, "Buch", "Krimi", isbn="9783161484100")
    add_categorized(client, "Zweites", "Urlaub", isbn="9780306406157")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    add_categorized(client, "Buch", "Krimi", isbn="9783161484100")
    add_categorized(client, "Zweites", "Urlaub", isbn="9780306406157")
    post(client, "/category/rename", old="Krimi", new="Thriller")
    post(client, "/category/delete", name="Urlaub")
    assert shelves_of("bob") == {"Thriller": {"Buch"}}
    assert shelves_of() == {"Krimi": {"Buch"}, "Urlaub": {"Zweites"}}


def test_no_category_shelf_has_no_actions(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins")
    html = client.get("/").text
    assert "/category/rename" not in html
    assert "/category/delete" not in html
    add_categorized(client, "Zwei", "Krimi")
    html = client.get("/").text
    assert html.count('action="/category/rename') == 1
    assert html.count('action="/category/delete') == 1


def test_category_actions_keep_filters(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi", is_read="on")
    assert 'action="/category/rename?read=1"' in client.get("/?read=1").text
    with client.session_transaction() as s:
        data = {"csrf": s["csrf"], "old": "Krimi", "new": "Thriller"}
    r = client.post("/category/rename?read=1", data=data)
    assert r.headers["Location"] == "/?read=1"


def assign(
    client: FlaskClient, *items: tuple[str, str], url: str = "/category/assign", **data: str
) -> TestResponse:
    """Sends (title, source shelf) pairs the way the selection form does."""
    with client.session_transaction() as s:
        form: dict[str, str | list[str]] = {**data, "csrf": s["csrf"]}
    with app.app_context():
        ids = {
            row["title"]: row["id"] for row in database.db().execute("SELECT id, title FROM books")
        }
    form["item"] = [f"{ids[title]}:{source}" for title, source in items]
    return client.post(url, data=form, follow_redirects=True)


def test_move_book_to_another_category(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi", "Urlaub")
    add_categorized(client, "Zwei", "Roman")
    r = assign(client, ("Eins", "Krimi"), target="Roman", mode="move")
    assert "1 book moved" in r.text
    assert shelves_of() == {"Roman": {"Eins", "Zwei"}, "Urlaub": {"Eins"}}


def test_copy_book_keeps_it_on_its_shelf(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    r = assign(client, ("Eins", "Krimi"), target="Roman", mode="copy")
    assert "1 book copied" in r.text
    assert shelves_of() == {"Krimi": {"Eins"}, "Roman": {"Eins"}}


def test_move_several_books_from_different_shelves(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    add_categorized(client, "Zwei", "Urlaub")
    add_categorized(client, "Ohne")
    r = assign(
        client, ("Eins", "Krimi"), ("Zwei", "Urlaub"), ("Ohne", ""), target="Roman", mode="move"
    )
    assert "3 books moved" in r.text
    assert shelves_of() == {"Roman": {"Eins", "Zwei", "Ohne"}}


def test_move_to_shelf_already_holding_the_book(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi", "Roman")
    assign(client, ("Eins", "Krimi"), target="Roman", mode="move")
    assert shelves_of() == {"Roman": {"Eins"}}


def test_move_to_own_shelf_keeps_the_book(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    assign(client, ("Eins", "Krimi"), target="krimi", mode="move")
    assert shelves_of() == {"Krimi": {"Eins"}}


def test_assign_creates_category_and_reuses_spelling(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    add_categorized(client, "Zwei")
    assign(client, ("Zwei", ""), target=" krimi ", mode="copy")
    assign(client, ("Eins", "Krimi"), target="Neu", mode="copy")
    assert shelves_of() == {"Krimi": {"Eins", "Zwei"}, "Neu": {"Eins"}}


def test_source_category_may_contain_a_colon(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Sci:Fi")
    assign(client, ("Eins", "Sci:Fi"), target="Roman", mode="move")
    assert shelves_of() == {"Roman": {"Eins"}}


@pytest.mark.parametrize("mode", ["move", "copy"])
@pytest.mark.parametrize("target", ["", "   ", "Krimi, Urlaub"])
def test_assign_rejects_invalid_targets(client: FlaskClient, mode: str, target: str) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    r = assign(client, ("Eins", "Krimi"), target=target, mode=mode)
    assert "must not be empty" in r.text
    assert shelves_of() == {"Krimi": {"Eins"}}


def test_remove_only_leaves_the_source_shelf(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi", "Urlaub")
    add_categorized(client, "Zwei", "Krimi")
    r = assign(client, ("Eins", "Krimi"), ("Zwei", "Krimi"), mode="remove")
    assert "2 books removed" in r.text
    assert shelves_of() == {"Urlaub": {"Eins"}}
    assert in_order(r.text, 'data-name="Urlaub"', 'data-name=""', 'class="t">Zwei<')


def test_assign_counts_a_book_selected_on_two_shelves_once(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi", "Urlaub")
    r = assign(client, ("Eins", "Krimi"), ("Eins", "Urlaub"), target="Roman", mode="move")
    assert "1 book moved" in r.text
    assert shelves_of() == {"Roman": {"Eins"}}


def test_assign_rejects_foreign_books_without_partial_changes(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/users", username="bob", password="bobpw")
    add_categorized(client, "Fremd", "Krimi")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    add_categorized(client, "Meins", "Urlaub")
    r = assign(client, ("Meins", "Urlaub"), ("Fremd", "Krimi"), target="Roman", mode="move")
    assert r.status_code == 404
    assert shelves_of("bob") == {"Urlaub": {"Meins"}}
    assert shelves_of() == {"Krimi": {"Fremd"}}


@pytest.mark.parametrize(
    "data",
    [
        {"mode": "steal"},
        {"mode": "move", "item": "abc:Krimi"},
        {"mode": "move", "item": "999:Krimi"},
    ],
)
def test_assign_rejects_bad_requests(client: FlaskClient, data: dict[str, str]) -> None:
    login(client, "admin", "secret")
    assert post(client, "/category/assign", target="Roman", **data).status_code == 404


def test_assign_needs_csrf_token(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    r = client.post("/category/assign", data={"item": "1:Krimi", "target": "Roman", "mode": "copy"})
    assert r.status_code == 400
    assert shelves_of() == {"Krimi": {"Eins"}}


def test_assign_keeps_filters(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi", is_read="on")
    assert 'action="/category/assign?read=1"' in client.get("/?read=1").text
    with client.session_transaction() as s:
        data = {"csrf": s["csrf"], "target": "Roman", "mode": "copy"}
    assert client.post("/category/assign?read=1", data=data).headers["Location"] == "/?read=1"


def test_books_can_only_be_selected_on_shelves(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    add_categorized(client, "Eins", "Krimi")
    assert 'class="pick"' in client.get("/").text
    assert 'class="pick"' not in client.get("/?view=books").text
    assert 'class="pick"' not in client.get("/?view=catalog").text
