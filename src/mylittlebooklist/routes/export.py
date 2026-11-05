"""Export of the current gallery view as CSV, Excel workbook or printable index cards."""

import csv
import io
import sqlite3
from typing import Any

from flask import render_template
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from PIL import Image
from xlsxwriter import Workbook

from mylittlebooklist.app import app
from mylittlebooklist.database import db
from mylittlebooklist.routes.auth import login_required
from mylittlebooklist.routes.books import categories_by_book, current_books

COVER_SIZE = (150, 220)  # pixels in the Excel sheet
MAX_COVER_PIXELS = 20_000_000  # a few MB of upload can decode to gigabytes of memory
ROW_HEIGHT = COVER_SIZE[1] * 0.75  # points
COLUMN_WIDTHS = {"A": 22, "B": 40, "C": 30, "F": 60, "J": 30}  # the rest keeps Excel's default
MAX_CELL_TEXT = 32_767  # Excel's limit; xlsxwriter would silently leave a longer cell empty


def header() -> list[str]:
    return [
        _("Title"),
        _("Author"),
        _("Year of publication"),
        "ISBN",
        _("Description"),
        _("Rating"),
        _("Read"),
        _("Owned"),
        _("Categories"),
    ]


def yes_no(flag: int | None) -> str:
    # NULL: a catalog book outside the user's collection
    return "" if flag is None else _("Yes") if flag else _("No")


def table(books: list[sqlite3.Row]) -> list[list[Any]]:
    """One row per book, in the order of header()."""
    categories = categories_by_book()
    return [
        [
            b["title"],
            b["author"],
            b["year"],
            b["isbn"],
            b["description"],
            b["rating"],
            yes_no(b["is_read"]),
            yes_no(b["is_owned"]),
            ", ".join(categories.get(b["id"], [])),
        ]
        for b in books
    ]


def csv_safe(value: Any) -> Any:
    # Texts come from the shared catalog; Excel would otherwise run '=...' as a formula
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def thumbnail(cover: bytes) -> io.BytesIO | None:
    """A small JPEG of the cover, None if it can't be read."""
    try:
        with Image.open(io.BytesIO(cover), formats=("JPEG", "PNG", "GIF", "WEBP")) as image:
            if image.width * image.height > MAX_COVER_PIXELS:
                return None
            image.thumbnail(COVER_SIZE)
            out = io.BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=80)
            out.seek(0)
            return out
    except Exception:  # Pillow raises many types on broken files; one must not stop the export
        return None


@app.route("/export.csv")
@login_required
def export_csv() -> ResponseReturnValue:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(header())
    for row in table(current_books()):
        writer.writerow([csv_safe(value) for value in row])
    # The BOM makes Excel read the file as UTF-8
    return out.getvalue().encode("utf-8-sig"), {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="booklist.csv"',
    }


@app.route("/export.xlsx")
@login_required
def export_xlsx() -> ResponseReturnValue:
    out = io.BytesIO()
    # Catalog text starting with '=' or 'http' must stay plain text. No in_memory: with it,
    # XlsxWriter 3.3.1 stores a part name with a leading '/', and Excel refuses the file
    workbook = Workbook(out, {"strings_to_formulas": False, "strings_to_urls": False})
    sheet = workbook.add_worksheet()
    sheet.write_row(0, 0, [_("Cover"), *header()])
    for column, width in COLUMN_WIDTHS.items():
        sheet.set_column(f"{column}:{column}", width)
    cell_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    books = current_books()
    for number, (book, row) in enumerate(zip(books, table(books)), start=1):
        sheet.set_row(number, ROW_HEIGHT)
        values = [v[:MAX_CELL_TEXT] if isinstance(v, str) else v for v in row]
        sheet.write_row(number, 1, values, cell_format)
        if book["has_cover"]:
            cover = db().execute("SELECT cover FROM books WHERE id = ?", (book["id"],)).fetchone()
            if image := thumbnail(cover["cover"]):
                # In the cell, not above it; needs Excel 2024 or 365, older versions show an error
                options = {"image_data": image, "description": book["title"]}
                sheet.embed_image(number, 0, "cover.jpg", options)
    workbook.close()
    return out.getvalue(), {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": 'attachment; filename="booklist.xlsx"',
    }


@app.route("/export/cards")
@login_required
def export_cards() -> ResponseReturnValue:
    return render_template(
        "export_cards.html", books=current_books(), categories=categories_by_book()
    )
