"""MyTinyBookLog – kleine Bücherverwaltung für zu Hause."""

import json
import os
import re
import secrets
import shutil
import sqlite3
import time
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
    demo_db = os.path.join(app.root_path, "demo.db")
    if os.environ.get("DEMO") == "1" and not os.path.exists(DB_PATH) and os.path.exists(demo_db):
        shutil.copyfile(demo_db, DB_PATH)  # fertige Demo-DB statt 24 OpenLibrary-Anfragen
    with open(os.path.join(app.root_path, "schema.sql"), encoding="utf-8") as f:
        db().executescript(f.read())
    if db().execute("SELECT 1 FROM users").fetchone():
        return
    if os.environ.get("DEMO") == "1":
        seed_demo()
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

@app.route("/")
@login_required
def gallery():
    q = request.args.get("q", "").strip()
    like = f"%{q}%"
    isbn_like = "%" + re.sub(r"[-\s]", "", q) + "%"
    books = db().execute(
        """SELECT b.id, b.title, b.author, b.year, b.cover IS NOT NULL AS has_cover, ub.rating
           FROM books b JOIN user_books ub ON ub.book_id = b.id AND ub.user_id = ?
           WHERE ? = '' OR b.title LIKE ? OR b.author LIKE ? OR CAST(b.year AS TEXT) LIKE ?
                 OR b.isbn LIKE ? OR b.description LIKE ?
           ORDER BY b.author COLLATE NOCASE, b.year, b.title COLLATE NOCASE""",
        (g.user["id"], q, like, like, like, isbn_like, like)).fetchall()
    return render_template("gallery.html", books=books, q=q)


def owned_book(book_id):
    book = db().execute(
        """SELECT b.*, ub.rating FROM books b
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


def add_to_collection(book_id, rating):
    db().execute("INSERT OR IGNORE INTO user_books (user_id, book_id, rating) VALUES (?, ?, ?)",
                 (g.user["id"], book_id, rating))
    db().commit()
    flash("Das Buch ist schon im Katalog und wurde deiner Sammlung hinzugefügt.", "ok")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/book/new", methods=["GET", "POST"])
@login_required
def book_new():
    if request.method == "GET":
        return render_template("book_form.html", book={}, new=True)
    data, errors = read_form()
    if request.form.get("action") == "lookup":
        result = do_lookup(data)
        if isinstance(result, int):
            return add_to_collection(result, data["rating"])
        return render_template("book_form.html", book=result, new=True)
    if not data["title"]:
        errors.append("Titel ist ein Pflichtfeld.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("book_form.html", book=data, new=True)
    isbn = normalize_isbn(data["isbn"])
    if isbn and (existing := db().execute("SELECT id FROM books WHERE isbn = ?", (isbn,)).fetchone()):
        return add_to_collection(existing["id"], data["rating"])
    cover_bytes, mime = form_cover(data)
    cur = db().execute(
        "INSERT INTO books (title, author, year, isbn, description, cover, cover_mime) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["title"], data["author"], data["year"] or None, isbn, data["description"], cover_bytes, mime))
    db().execute("INSERT INTO user_books (user_id, book_id, rating) VALUES (?, ?, ?)",
                 (g.user["id"], cur.lastrowid, data["rating"]))
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
    db().execute("UPDATE user_books SET rating=? WHERE user_id=? AND book_id=?",
                 (data["rating"], g.user["id"], book_id))
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


# --- Demo-Daten --------------------------------------------------------------

DEMO_BOOKS = [
    # (isbn, title, author, year, description, {user: rating})
    ("9780547928227", "The Hobbit", "J. R. R. Tolkien", 1937,
     "Bilbo Beutlin wird von Gandalf und dreizehn Zwergen auf eine Reise zum Einsamen Berg mitgenommen.",
     {"demo": 5, "anna": 4}),
    ("9780261103573", "The Fellowship of the Ring", "J. R. R. Tolkien", 1954,
     "Erster Teil des Herrn der Ringe: Frodo bricht auf, um den Einen Ring zu vernichten.", {"demo": 5}),
    ("9780451524935", "Nineteen Eighty-Four", "George Orwell", 1949,
     "Dystopie über Überwachung, Gedankenkontrolle und den Großen Bruder.", {"demo": 4, "anna": 5}),
    ("9780441172719", "Dune", "Frank Herbert", 1965,
     "Wüstenplanet Arrakis, das Spice und der Aufstieg von Paul Atreides.", {"demo": 5}),
    ("9780345391803", "The Hitchhiker's Guide to the Galaxy", "Douglas Adams", 1979,
     "Kurz bevor die Erde gesprengt wird, trampt Arthur Dent ins All. Don't panic!", {"demo": 4, "anna": 5}),
    ("9780743273565", "The Great Gatsby", "F. Scott Fitzgerald", 1925,
     "Jay Gatsby, Daisy Buchanan und der amerikanische Traum in den Roaring Twenties.", {"anna": 3}),
    ("9780141439518", "Pride and Prejudice", "Jane Austen", 1813,
     "Elizabeth Bennet und Mr. Darcy – Stolz und Vorurteil.", {"anna": 5}),
    ("9780061120084", "To Kill a Mockingbird", "Harper Lee", 1960,
     "Scout Finch erlebt, wie ihr Vater einen zu Unrecht angeklagten Schwarzen verteidigt.", {"demo": 4}),
    ("9780553380163", "A Brief History of Time", "Stephen Hawking", 1988,
     "Vom Urknall bis zu Schwarzen Löchern – Kosmologie für alle.", {"demo": 3}),
    ("9780316769488", "The Catcher in the Rye", "J. D. Salinger", 1951,
     "Holden Caulfield irrt drei Tage durch New York.", {"demo": 3}),
    ("9780140449136", "Crime and Punishment", "Fjodor Dostojewski", 1866,
     "Raskolnikow begeht einen Mord und ringt mit Schuld und Gewissen.", {"anna": 4}),
    ("9780439708180", "Harry Potter and the Sorcerer's Stone", "J. K. Rowling", 1997,
     "Harry erfährt an seinem elften Geburtstag, dass er ein Zauberer ist.", {"demo": 4, "anna": 4}),
]


def seed_demo():
    """Demo-User admin/admin, demo/demo, anna/anna plus Beispielbücher. Cover kommen von OpenLibrary (falls online)."""
    ids = {}
    for name, is_admin in (("admin", 1), ("demo", 0), ("anna", 0)):
        db().execute("INSERT OR IGNORE INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                     (name, generate_password_hash(name), is_admin))
        ids[name] = db().execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()["id"]
    for isbn, title, author, year, desc, ratings in DEMO_BOOKS:
        if db().execute("SELECT 1 FROM books WHERE isbn = ?", (isbn,)).fetchone():
            continue
        # OpenLibrary Fair Use: höchstens 1 Anfrage pro Sekunde
        found = lookup_isbn(isbn)
        time.sleep(1)
        cover_bytes, mime = fetch_cover(found["cover_url"] if found else None)
        time.sleep(1)
        cur = db().execute(
            "INSERT INTO books (title, author, year, isbn, description, cover, cover_mime) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, author, year, isbn, desc, cover_bytes, mime))
        for name, rating in ratings.items():
            db().execute("INSERT INTO user_books (user_id, book_id, rating) VALUES (?, ?, ?)",
                         (ids[name], cur.lastrowid, rating))
        app.logger.info("Demo-Buch: %s (%s)", title, "mit Cover" if cover_bytes else "ohne Cover")
    db().commit()


@app.cli.command("seed-demo")
def seed_demo_command():
    """Demo-Daten in die Datenbank laden."""
    init_db()
    seed_demo()
    print("Demo-Daten geladen. Logins: admin/admin, demo/demo, anna/anna")


with app.app_context():
    init_db()
