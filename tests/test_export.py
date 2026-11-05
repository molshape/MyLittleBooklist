import csv
import io
import re
import zipfile
from typing import Any

import pytest
from flask.testing import FlaskClient
from openpyxl import load_workbook
from PIL import Image

from mylittlebooklist.app import app
from mylittlebooklist.database import db
from tests.helpers import login, post

ROUTES = ["/export.csv", "/export.xlsx", "/export/cards"]


def read_csv(client: FlaskClient, url: str = "/export.csv") -> list[list[str]]:
    return list(csv.reader(io.StringIO(client.get(url).data.decode("utf-8-sig"), newline="")))


def read_xlsx(client: FlaskClient) -> Any:
    return load_workbook(io.BytesIO(client.get("/export.xlsx").data)).active


def embedded_covers(client: FlaskClient) -> tuple[list[str], list[bytes]]:
    """Cells holding a cover and the images in the workbook; openpyxl can't see either."""
    with zipfile.ZipFile(io.BytesIO(client.get("/export.xlsx").data)) as z:
        assert not [name for name in z.namelist() if "drawing" in name]  # nothing floats
        assert not [name for name in z.namelist() if name.startswith("/")]  # Excel refuses it
        cells = re.findall(r'<c r="(\w+)"[^>]* vm="', z.read("xl/worksheets/sheet1.xml").decode())
        return cells, [z.read(name) for name in z.namelist() if name.startswith("xl/media/")]


def export_text(client: FlaskClient, route: str, query: str) -> str:
    r = client.get(route + query)
    if route == "/export.xlsx":
        sheet = load_workbook(io.BytesIO(r.data)).active
        return str([cell.value for row in sheet.iter_rows() for cell in row])
    return str(r.data.decode("utf-8-sig"))


def set_cover(client: FlaskClient, title: str, cover: bytes) -> None:
    post(client, "/book/new", title=title)
    with app.app_context():
        db().execute("UPDATE books SET cover = ? WHERE title = ?", (cover, title))
        db().commit()


def webp() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (600, 900), "red").save(out, "WEBP")
    return out.getvalue()


@pytest.mark.parametrize("route", ROUTES)
def test_export_requires_login(client: FlaskClient, route: str) -> None:
    assert "/login" in client.get(route).headers["Location"]


def test_csv_format(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/book/new", title="Ärger", author="Ä, B", new_category="Krimi, Alt", is_read="on")
    post(client, "/book/new", title="=1+1", is_owned="on")
    r = client.get("/export.csv")
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]
    assert r.data.startswith(b"\xef\xbb\xbf")
    assert '"Ä, B"'.encode() in r.data  # comma separated, so a comma in a value gets quoted
    rows = read_csv(client)
    assert rows[0][0] == "Title"
    assert rows[1] == ["'=1+1", "", "", "", "", "", "No", "Yes", ""]
    assert rows[2] == ["Ärger", "Ä, B", "", "", "", "", "Yes", "No", "Alt, Krimi"]


@pytest.mark.parametrize("route", ROUTES)
def test_export_follows_the_filters(client: FlaskClient, route: str) -> None:
    login(client, "admin", "secret")
    post(client, "/book/new", title="Gelesen", is_read="on")
    post(client, "/book/new", title="Offen")
    assert "Gelesen" in export_text(client, route, "?read=1")
    assert "Offen" not in export_text(client, route, "?read=1")
    assert "Offen" in export_text(client, route, "?q=off")
    assert "Gelesen" not in export_text(client, route, "?q=off")


@pytest.mark.parametrize("route", ROUTES)
def test_export_keeps_users_apart(client: FlaskClient, route: str) -> None:
    login(client, "admin", "secret")
    post(client, "/book/new", title="Zauberberg", new_category="Geheim")
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    assert "Zauberberg" not in export_text(client, route, "")
    catalog = export_text(client, route, "?view=catalog")
    assert "Zauberberg" in catalog
    assert "Geheim" not in catalog


def test_catalog_flags_stay_empty(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/book/new", title="Zauberberg")
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    assert read_csv(client, "/export.csv?view=catalog")[1][6:8] == ["", ""]


def test_xlsx_keeps_hostile_text_as_text(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/book/new", title="=1+1", author="http://x.example", description="a\x0bb")
    r = client.get("/export.xlsx")
    assert "spreadsheetml.sheet" in str(r.mimetype)
    sheet: Any = load_workbook(io.BytesIO(r.data)).active
    assert sheet["B2"].value == "=1+1"
    assert sheet["B2"].data_type == "s"
    assert sheet["C2"].hyperlink is None
    assert sheet["F2"].value == "a_x000B_b"  # the file format's escape, Excel reads it back


def test_xlsx_cuts_text_at_the_excel_limit(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/book/new", title="Lang", description="x" * 40_000)
    assert len(read_xlsx(client)["F2"].value) == 32_767


def test_xlsx_embeds_readable_covers_only(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    set_cover(client, "A & <gut>", webp())
    set_cover(client, "B kaputt", b"<svg onload='alert(1)'/>")
    post(client, "/book/new", title="C ohne")
    cells, images = embedded_covers(client)
    assert cells == ["A2"]
    assert max(Image.open(io.BytesIO(images[0])).size) <= 220


def test_xlsx_skips_huge_covers(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    out = io.BytesIO()
    Image.new("1", (5000, 5000)).save(out, "PNG")
    set_cover(client, "Riesig", out.getvalue())
    assert embedded_covers(client) == ([], [])


def test_cards_show_each_book(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    set_cover(client, "Mit Bild", webp())
    post(client, "/book/new", title="<Ohne> Bild", new_category="Krimi")
    text = client.get("/export/cards").text
    assert text.count('class="export-card"') == 2
    assert text.count('src="/cover/') == 1
    assert 'loading="lazy"' not in text
    assert "&lt;Ohne&gt; Bild" in text
    assert "Krimi" in text


def test_gallery_menu(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    assert "/export.csv" not in client.get("/").text
    post(client, "/book/new", title="Zauberberg", is_read="on")
    text = client.get("/?read=1&q=zauber").text
    for route in ROUTES:
        assert f"{route}?read=1&amp;q=zauber" in text
