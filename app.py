"""MyTinyBookLog – kleine Bücherverwaltung für zu Hause."""

import json
import os
import re
import secrets
import sqlite3
from datetime import timedelta
from functools import wraps
from urllib.error import URLError
from urllib.request import Request, urlopen

import isbnlib
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.environ.get("DB_PATH", "books.db")
USER_AGENT = {"User-Agent": "MyTinyBookLog/0.1 (private home library)"}
COVER_PREFIX = "https://covers.openlibrary.org/"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)
if not os.environ.get("SECRET_KEY"):
    app.logger.warning("SECRET_KEY nicht gesetzt – Sessions gelten nur bis zum Neustart.")


# --- Datenbank ---------------------------------------------------------------

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    if (conn := g.pop("db", None)) is not None:
        conn.close()


def remove_orphans():
    db().execute("DELETE FROM books WHERE id NOT IN (SELECT book_id FROM user_books)")


def init_db():
    with open(os.path.join(app.root_path, "schema.sql"), encoding="utf-8") as f:
        db().executescript(f.read())
    if db().execute("SELECT 1 FROM users").fetchone():
        return
    name = os.environ.get("ADMIN_USER", "admin")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(12)
        app.logger.warning("ADMIN_PASSWORD nicht gesetzt – generiert für '%s': %s", name, password)
    db().execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
                 (name, generate_password_hash(password)))
    db().commit()


# --- OpenLibrary -------------------------------------------------------------

def normalize_isbn(raw):
    isbn = re.sub(r"[^0-9Xx]", "", raw or "").upper()
    return isbn if len(isbn) in (10, 13) else None


@app.template_filter("isbn")
def format_isbn(isbn):
    """Mit Bindestrichen nach offizieller ISBN-Bereichstabelle; ungültige ISBNs unverändert."""
    try:
        return isbnlib.mask(isbn) or isbn
    except isbnlib.NotValidISBNError:
        return isbn


def lookup_isbn(isbn):
    """Liefert dict(title, author, year, cover_url) oder None, wenn unbekannt/offline."""
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        with urlopen(Request(url, headers=USER_AGENT), timeout=10) as resp:
            data = json.load(resp).get(f"ISBN:{isbn}")
    except (URLError, TimeoutError, ValueError):
        return None
    if not data:
        return None
    year = re.search(r"\d{4}", data.get("publish_date", ""))
    return {
        "title": data.get("title", ""),
        "author": ", ".join(a["name"] for a in data.get("authors", [])),
        "year": int(year.group()) if year else None,
        "cover_url": data.get("cover", {}).get("large")
                     or f"{COVER_PREFIX}b/isbn/{isbn}-L.jpg?default=false",
    }


def fetch_cover(url):
    """Lädt ein Cover von OpenLibrary; nur diese Domain, damit der Server keine beliebigen URLs abruft."""
    if not url or not url.startswith(COVER_PREFIX):
        return None, None
    try:
        with urlopen(Request(url, headers=USER_AGENT), timeout=15) as resp:
            mime = resp.headers.get_content_type()
            return (resp.read(), mime) if mime.startswith("image/") else (None, None)
    except (URLError, TimeoutError):
        return None, None


# --- Auth & CSRF -------------------------------------------------------------

@app.before_request
def load_user_and_check_csrf():
    g.user = None
    if uid := session.get("uid"):
        g.user = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        token = session.get("csrf")
        if not token or not secrets.compare_digest(token, request.form.get("csrf", "")):
            abort(400, "Ungültiges Formular-Token – bitte Seite neu laden.")


@app.context_processor
def inject_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return {"csrf": session["csrf"]}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = db().execute("SELECT * FROM users WHERE username = ?",
                            (request.form.get("username", "").strip(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            # Neue Session bei jedem Login (gegen Session-Fixation), 30 Tage gültig.
            session.clear()
            session.permanent = True
            session["uid"] = user["id"]
            session["csrf"] = secrets.token_urlsafe(32)
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("gallery"))
        flash("Benutzername oder Passwort falsch.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        new = request.form.get("new_password", "")
        if not check_password_hash(g.user["password_hash"], request.form.get("old_password", "")):
            flash("Aktuelles Passwort ist falsch.", "error")
        elif len(new) < 4:
            flash("Neues Passwort muss mindestens 4 Zeichen haben.", "error")
        else:
            db().execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(new), g.user["id"]))
            db().commit()
            flash("Passwort geändert.", "ok")
            return redirect(url_for("gallery"))
    return render_template("account.html")


# --- Bücher ------------------------------------------------------------------

FLAGS = {"read": "is_read", "owned": "is_owned"}  # URL-Name -> Spalte in user_books


@app.route("/")
@login_required
def gallery():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    isbn_like = "%" + re.sub(r"[-\s]", "", q) + "%"
    params = [g.user["id"], q, like, like, like, isbn_like, like]
    # Filter je Flag: '1' = ja, '0' = nein, sonst alle
    filters = {k: v for k in FLAGS if (v := request.args.get(k)) in ("0", "1")}
    flag_sql = "".join(f" AND ub.{FLAGS[k]} = ?" for k in filters)
    params += [int(v) for v in filters.values()]
    books = db().execute(
        f"""SELECT b.id, b.title, b.author, b.year, b.cover IS NOT NULL AS has_cover,
                  ub.rating, ub.is_read, ub.is_owned
           FROM books b JOIN user_books ub ON ub.book_id = b.id AND ub.user_id = ?
           WHERE (? = '' OR b.title LIKE ? OR b.author LIKE ? OR CAST(b.year AS TEXT) LIKE ?
                  OR b.isbn LIKE ? OR b.description LIKE ?){flag_sql}
           ORDER BY b.author COLLATE NOCASE, b.year, b.title COLLATE NOCASE""",
        params).fetchall()
    return render_template("gallery.html", books=books, q=q, filters=filters)


@app.template_global()
def gallery_url(**changes):
    """Galerie-URL mit den aktuellen Such-/Filterparametern, einzelne davon geändert ('' = entfernen)."""
    args = {**request.args.to_dict(), **changes}
    return url_for("gallery", **{k: v for k, v in args.items() if v})


def owned_book(book_id):
    book = db().execute(
        """SELECT b.*, ub.rating, ub.is_read, ub.is_owned FROM books b
           JOIN user_books ub ON ub.book_id = b.id AND ub.user_id = ? WHERE b.id = ?""",
        (g.user["id"], book_id)).fetchone()
    if book is None:
        abort(404)
    return book


@app.route("/book/<int:book_id>")
@login_required
def book_detail(book_id):
    return render_template("book.html", book=owned_book(book_id))


@app.route("/cover/<int:book_id>")
@login_required
def cover(book_id):
    book = owned_book(book_id)
    if not book["cover"]:
        abort(404)
    return book["cover"], {"Content-Type": book["cover_mime"],
                           "Cache-Control": "private, max-age=3600"}


@app.post("/book/<int:book_id>/rate")
@login_required
def rate(book_id):
    owned_book(book_id)
    db().execute("UPDATE user_books SET rating = ? WHERE user_id = ? AND book_id = ?",
                 (parse_rating(request.form.get("rating")), g.user["id"], book_id))
    db().commit()
    return redirect(url_for("book_detail", book_id=book_id))


@app.post("/book/<int:book_id>/flag/<name>")
@login_required
def set_flag(book_id, name):
    if name not in FLAGS:
        abort(404)
    owned_book(book_id)
    # Spaltenname stammt aus der FLAGS-Whitelist, nie aus der URL
    db().execute(f"UPDATE user_books SET {FLAGS[name]} = ? WHERE user_id = ? AND book_id = ?",
                 (int(request.form.get("value") == "1"), g.user["id"], book_id))
    db().commit()
    return redirect(url_for("book_detail", book_id=book_id))


@app.post("/book/<int:book_id>/remove")
@login_required
def remove(book_id):
    owned_book(book_id)
    db().execute("DELETE FROM user_books WHERE user_id = ? AND book_id = ?", (g.user["id"], book_id))
    remove_orphans()
    db().commit()
    flash("Buch aus deiner Sammlung entfernt.", "ok")
    return redirect(url_for("gallery"))


def parse_rating(raw):
    return int(raw) if raw in {"1", "2", "3", "4", "5"} else None


def read_form():
    """Formularfelder einlesen; liefert (felder, fehlerliste)."""
    f = request.form
    data = {
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
    if data["isbn"] and not normalize_isbn(data["isbn"]):
        errors.append("ISBN muss 10 oder 13 Stellen haben.")
    if data["year"] and not re.fullmatch(r"-?\d{1,4}", data["year"]):
        errors.append("Erscheinungsjahr muss eine Zahl sein.")
    return data, errors


def form_cover(data):
    """Cover aus Upload oder (nach ISBN-Lookup) von OpenLibrary; (None, None) wenn keins."""
    upload = request.files.get("cover")
    if upload and upload.filename:
        if not (upload.mimetype or "").startswith("image/"):
            return None, None
        return upload.read(), upload.mimetype
    return fetch_cover(data["cover_url"])


def do_lookup(data, book_id=None):
    isbn = normalize_isbn(data["isbn"])
    if not isbn:
        flash("Bitte eine gültige ISBN (10 oder 13 Stellen) eingeben.", "error")
        return data
    if book_id is None:
        existing = db().execute("SELECT id FROM books WHERE isbn = ?", (isbn,)).fetchone()
        if existing:
            return existing["id"]
    found = lookup_isbn(isbn)
    if not found:
        flash("Bei OpenLibrary nichts gefunden – bitte manuell ausfüllen.", "error")
        return data
    flash("Daten von OpenLibrary übernommen – bitte prüfen und speichern.", "ok")
    return {**data, **{k: v or "" for k, v in found.items()}, "isbn": isbn}


def insert_user_book(book_id, data, ignore=False):
    db().execute(f"INSERT {'OR IGNORE ' if ignore else ''}INTO user_books"
                 " (user_id, book_id, rating, is_read, is_owned) VALUES (?, ?, ?, ?, ?)",
                 (g.user["id"], book_id, data["rating"], data["is_read"], data["is_owned"]))


def add_to_collection(book_id, data):
    insert_user_book(book_id, data, ignore=True)
    db().commit()
    flash("Das Buch ist schon im Katalog und wurde deiner Sammlung hinzugefügt.", "ok")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/book/new", methods=["GET", "POST"])
@login_required
def book_new():
    if request.method == "GET":
        return render_template("book_form.html", book={"is_owned": 1}, new=True)
    data, errors = read_form()
    if request.form.get("action") == "lookup":
        result = do_lookup(data)
        if isinstance(result, int):
            return add_to_collection(result, data)
        return render_template("book_form.html", book=result, new=True)
    if not data["title"]:
        errors.append("Titel ist ein Pflichtfeld.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("book_form.html", book=data, new=True)
    isbn = normalize_isbn(data["isbn"])
    if isbn and (existing := db().execute("SELECT id FROM books WHERE isbn = ?", (isbn,)).fetchone()):
        return add_to_collection(existing["id"], data)
    cover_bytes, mime = form_cover(data)
    cur = db().execute(
        "INSERT INTO books (title, author, year, isbn, description, cover, cover_mime) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["title"], data["author"], data["year"] or None, isbn, data["description"], cover_bytes, mime))
    insert_user_book(cur.lastrowid, data)
    db().commit()
    flash("Buch gespeichert.", "ok")
    return redirect(url_for("book_detail", book_id=cur.lastrowid))


@app.route("/book/<int:book_id>/edit", methods=["GET", "POST"])
@login_required
def book_edit(book_id):
    book = owned_book(book_id)
    if request.method == "GET":
        return render_template("book_form.html", book=book, new=False)
    data, errors = read_form()
    data["id"], data["cover"] = book_id, book["cover"]
    if request.form.get("action") == "lookup":
        return render_template("book_form.html", book=do_lookup(data, book_id), new=False)
    if not data["title"]:
        errors.append("Titel ist ein Pflichtfeld.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("book_form.html", book=data, new=False)
    cover_bytes, mime = form_cover(data)
    try:
        db().execute("UPDATE books SET title=?, author=?, year=?, isbn=?, description=? WHERE id=?",
                     (data["title"], data["author"], data["year"] or None,
                      normalize_isbn(data["isbn"]), data["description"], book_id))
    except sqlite3.IntegrityError:
        flash("Ein anderes Buch mit dieser ISBN existiert bereits.", "error")
        return render_template("book_form.html", book=data, new=False)
    if cover_bytes:
        db().execute("UPDATE books SET cover=?, cover_mime=? WHERE id=?", (cover_bytes, mime, book_id))
    db().execute("UPDATE user_books SET rating=?, is_read=?, is_owned=? WHERE user_id=? AND book_id=?",
                 (data["rating"], data["is_read"], data["is_owned"], g.user["id"], book_id))
    db().commit()
    flash("Änderungen gespeichert.", "ok")
    return redirect(url_for("book_detail", book_id=book_id))


# --- Benutzerverwaltung (Admin) ---------------------------------------------

@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        name, password = request.form.get("username", "").strip(), request.form.get("password", "")
        if not name or len(password) < 4:
            flash("Benutzername und Passwort (mind. 4 Zeichen) angeben.", "error")
        else:
            try:
                db().execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                             (name, generate_password_hash(password), int("is_admin" in request.form)))
                db().commit()
                flash(f"Benutzer „{name}“ angelegt.", "ok")
            except sqlite3.IntegrityError:
                flash("Benutzername existiert bereits.", "error")
        return redirect(url_for("users"))
    rows = db().execute(
        """SELECT u.id, u.username, u.is_admin, COUNT(ub.book_id) AS books
           FROM users u LEFT JOIN user_books ub ON ub.user_id = u.id
           GROUP BY u.id ORDER BY u.username COLLATE NOCASE""").fetchall()
    return render_template("users.html", users=rows)


@app.post("/users/<int:user_id>/<action>")
@admin_required
def user_action(user_id, action):
    if user_id == g.user["id"] and action in ("delete", "toggle_admin"):
        flash("Du kannst dich nicht selbst löschen oder dir die Admin-Rechte entziehen.", "error")
    elif action == "delete":
        db().execute("DELETE FROM users WHERE id = ?", (user_id,))
        remove_orphans()
        flash("Benutzer gelöscht.", "ok")
    elif action == "toggle_admin":
        db().execute("UPDATE users SET is_admin = 1 - is_admin WHERE id = ?", (user_id,))
    elif action == "password":
        password = request.form.get("password", "")
        if len(password) < 4:
            flash("Passwort muss mindestens 4 Zeichen haben.", "error")
        else:
            db().execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(password), user_id))
            flash("Passwort zurückgesetzt.", "ok")
    else:
        abort(404)
    db().commit()
    return redirect(url_for("users"))


with app.app_context():
    init_db()
