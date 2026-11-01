"""Gallery, book details and the personal collection."""

import re
import sqlite3
from typing import Any

from flask import abort, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from mylittlebooklist import openlibrary
from mylittlebooklist.app import app
from mylittlebooklist.database import db, remove_orphans
from mylittlebooklist.routes.auth import login_required

FLAGS = {"read": "is_read", "owned": "is_owned"}  # URL name -> column in user_books


@app.route("/")
@login_required
def gallery() -> ResponseReturnValue:
    q = request.args.get("q", "").strip()
    catalog = request.args.get("all") == "1"  # whole shared catalog instead of own collection
    like = f"%{q}%"
    isbn_like = "%" + re.sub(r"[-\s]", "", q) + "%"
    params = [g.user["id"], q, like, like, like, isbn_like, like]
    # Filter per flag: '1' = yes, '0' = no, otherwise all
    filters = {k: v for k in FLAGS if (v := request.args.get(k)) in ("0", "1")}
    flag_sql = "".join(f" AND ub.{FLAGS[k]} = ?" for k in filters)
    params += [int(v) for v in filters.values()]
    books = (
        db()
        .execute(
            f"""SELECT b.id, b.title, b.author, b.year, b.cover IS NOT NULL AS has_cover,
                  ub.rating, ub.is_read, ub.is_owned
           FROM books b {"LEFT JOIN" if catalog else "JOIN"} user_books ub
             ON ub.book_id = b.id AND ub.user_id = ?
           WHERE (? = '' OR b.title LIKE ? OR b.author LIKE ? OR CAST(b.year AS TEXT) LIKE ?
                  OR b.isbn LIKE ? OR b.description LIKE ?){flag_sql}
           ORDER BY b.author COLLATE NOCASE, b.year, b.title COLLATE NOCASE""",  # nosec B608
            params,
        )
        .fetchall()
    )
    return render_template("gallery.html", books=books, q=q, filters=filters, catalog=catalog)


@app.template_global()
def gallery_url(**changes: str) -> str:
    """Gallery URL with the current search/filter parameters, some of them changed ('' = remove)."""
    args: dict[str, Any] = {**request.args.to_dict(), **changes}
    return url_for("gallery", **{k: v for k, v in args.items() if v})


def catalog_book(book_id: int) -> sqlite3.Row:
    """Any book of the shared catalog; 'mine' tells whether it is in the user's collection."""
    book: sqlite3.Row | None = (
        db()
        .execute(
            """SELECT b.*, ub.rating, ub.is_read, ub.is_owned, ub.user_id IS NOT NULL AS mine
           FROM books b LEFT JOIN user_books ub ON ub.book_id = b.id AND ub.user_id = ?
           WHERE b.id = ?""",
            (g.user["id"], book_id),
        )
        .fetchone()
    )
    if book is None:
        abort(404)
    return book


def owned_book(book_id: int) -> sqlite3.Row:
    book = catalog_book(book_id)
    if not book["mine"]:
        abort(404)
    return book


@app.route("/book/<int:book_id>")
@login_required
def book_detail(book_id: int) -> ResponseReturnValue:
    return render_template("book.html", book=catalog_book(book_id))


@app.route("/cover/<int:book_id>")
@login_required
def cover(book_id: int) -> ResponseReturnValue:
    book = catalog_book(book_id)
    if not book["cover"]:
        abort(404)
    return book["cover"], {
        "Content-Type": book["cover_mime"],
        "Cache-Control": "private, max-age=3600",
    }


@app.post("/book/<int:book_id>/rate")
@login_required
def rate(book_id: int) -> ResponseReturnValue:
    owned_book(book_id)
    db().execute(
        "UPDATE user_books SET rating = ? WHERE user_id = ? AND book_id = ?",
        (parse_rating(request.form.get("rating")), g.user["id"], book_id),
    )
    db().commit()
    return redirect(url_for("book_detail", book_id=book_id))


@app.post("/book/<int:book_id>/flag/<name>")
@login_required
def set_flag(book_id: int, name: str) -> ResponseReturnValue:
    if name not in FLAGS:
        abort(404)
    owned_book(book_id)
    # Column name comes from the FLAGS whitelist, never from the URL
    db().execute(
        f"UPDATE user_books SET {FLAGS[name]} = ? WHERE user_id = ? AND book_id = ?",  # nosec B608
        (int(request.form.get("value") == "1"), g.user["id"], book_id),
    )
    db().commit()
    return redirect(url_for("book_detail", book_id=book_id))


@app.post("/book/<int:book_id>/add")
@login_required
def add(book_id: int) -> ResponseReturnValue:
    catalog_book(book_id)
    db().execute(
        "INSERT OR IGNORE INTO user_books (user_id, book_id) VALUES (?, ?)",
        (g.user["id"], book_id),
    )
    db().commit()
    flash(_("Book added to your collection."), "ok")
    return redirect(url_for("book_detail", book_id=book_id))


@app.post("/book/<int:book_id>/remove")
@login_required
def remove(book_id: int) -> ResponseReturnValue:
    owned_book(book_id)
    db().execute(
        "DELETE FROM user_books WHERE user_id = ? AND book_id = ?", (g.user["id"], book_id)
    )
    remove_orphans()
    db().commit()
    flash(_("Book removed from your collection."), "ok")
    return redirect(url_for("gallery"))


def parse_rating(raw: str | None) -> int | None:
    return int(raw) if raw in {"1", "2", "3", "4", "5"} else None


def read_form() -> tuple[dict[str, Any], list[str]]:
    """Reads the form fields; returns (fields, list of errors)."""
    f = request.form
    data: dict[str, Any] = {
        "isbn": f.get("isbn", "").strip(),
        "title": f.get("title", "").strip(),
        "author": f.get("author", "").strip(),
        "year": f.get("year", "").strip(),
        "description": f.get("description", "").strip(),
        "rating": parse_rating(f.get("rating")),
        "is_read": int("is_read" in f),
        "is_owned": int("is_owned" in f),
        "cover_url": f.get("cover_url", ""),
    }
    errors = []
    if data["isbn"] and not openlibrary.normalize_isbn(data["isbn"]):
        errors.append(_("ISBN must have 10 or 13 digits."))
    if data["year"] and not re.fullmatch(r"-?\d{1,4}", data["year"]):
        errors.append(_("Year of publication must be a number."))
    return data, errors


def form_cover(data: dict[str, Any]) -> tuple[bytes | None, str | None]:
    """Cover from the upload or (after an ISBN lookup) from OpenLibrary; (None, None) if there is none."""
    upload = request.files.get("cover")
    if upload and upload.filename:
        if not (upload.mimetype or "").startswith("image/"):
            return None, None
        return upload.read(), upload.mimetype
    return openlibrary.fetch_cover(data["cover_url"])


def do_lookup(data: dict[str, Any], book_id: int | None = None) -> dict[str, Any] | int:
    isbn = openlibrary.normalize_isbn(data["isbn"])
    if not isbn:
        flash(_("Please enter a valid ISBN (10 or 13 digits)."), "error")
        return data
    if book_id is None:
        existing = db().execute("SELECT id FROM books WHERE isbn = ?", (isbn,)).fetchone()
        if existing:
            return int(existing["id"])
    found = openlibrary.lookup_isbn(isbn)
    if not found:
        flash(_("Nothing found on OpenLibrary – please fill in manually."), "error")
        return data
    flash(_("Data taken from OpenLibrary – please check and save."), "ok")
    return {**data, **{k: v or "" for k, v in found.items()}, "isbn": isbn}


def insert_user_book(book_id: int | None, data: dict[str, Any], ignore: bool = False) -> None:
    db().execute(
        f"INSERT {'OR IGNORE ' if ignore else ''}INTO user_books"  # nosec B608
        " (user_id, book_id, rating, is_read, is_owned) VALUES (?, ?, ?, ?, ?)",
        (g.user["id"], book_id, data["rating"], data["is_read"], data["is_owned"]),
    )


def add_to_collection(book_id: int, data: dict[str, Any]) -> ResponseReturnValue:
    insert_user_book(book_id, data, ignore=True)
    db().commit()
    flash(_("This book is already in the catalog and was added to your collection."), "ok")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/book/new", methods=["GET", "POST"])
@login_required
def book_new() -> ResponseReturnValue:
    if request.method == "GET":
        return render_template("book_form.html", book={"is_owned": 1}, new=True)
    data, errors = read_form()
    if request.form.get("action") == "lookup":
        result = do_lookup(data)
        if isinstance(result, int):
            return add_to_collection(result, data)
        return render_template("book_form.html", book=result, new=True)
    if not data["title"]:
        errors.append(_("Title is required."))
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("book_form.html", book=data, new=True)
    isbn = openlibrary.normalize_isbn(data["isbn"])
    if isbn and (
        existing := db().execute("SELECT id FROM books WHERE isbn = ?", (isbn,)).fetchone()
    ):
        return add_to_collection(existing["id"], data)
    cover_bytes, mime = form_cover(data)
    cur = db().execute(
        "INSERT INTO books (title, author, year, isbn, description, cover, cover_mime) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            data["title"],
            data["author"],
            data["year"] or None,
            isbn,
            data["description"],
            cover_bytes,
            mime,
        ),
    )
    insert_user_book(cur.lastrowid, data)
    db().commit()
    flash(_("Book saved."), "ok")
    return redirect(url_for("book_detail", book_id=cur.lastrowid))


@app.route("/book/<int:book_id>/edit", methods=["GET", "POST"])
@login_required
def book_edit(book_id: int) -> ResponseReturnValue:
    book = owned_book(book_id)
    if request.method == "GET":
        return render_template("book_form.html", book=book, new=False)
    data, errors = read_form()
    data["id"], data["cover"] = book_id, book["cover"]
    if request.form.get("action") == "lookup":
        return render_template("book_form.html", book=do_lookup(data, book_id), new=False)
    if not data["title"]:
        errors.append(_("Title is required."))
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("book_form.html", book=data, new=False)
    cover_bytes, mime = form_cover(data)
    try:
        db().execute(
            "UPDATE books SET title=?, author=?, year=?, isbn=?, description=? WHERE id=?",
            (
                data["title"],
                data["author"],
                data["year"] or None,
                openlibrary.normalize_isbn(data["isbn"]),
                data["description"],
                book_id,
            ),
        )
    except sqlite3.IntegrityError:
        flash(_("Another book with this ISBN already exists."), "error")
        return render_template("book_form.html", book=data, new=False)
    if cover_bytes:
        db().execute(
            "UPDATE books SET cover=?, cover_mime=? WHERE id=?", (cover_bytes, mime, book_id)
        )
    db().execute(
        "UPDATE user_books SET rating=?, is_read=?, is_owned=? WHERE user_id=? AND book_id=?",
        (data["rating"], data["is_read"], data["is_owned"], g.user["id"], book_id),
    )
    db().commit()
    flash(_("Changes saved."), "ok")
    return redirect(url_for("book_detail", book_id=book_id))
