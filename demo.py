"""Optionale Demo-Daten: füllt die Datenbank (DB_PATH, Standard books.db) mit Beispielnutzern und -büchern.

Aufruf: uv run python demo.py   (im Container: docker compose exec booklog python demo.py)
Mehrfach ausführbar – vorhandene Nutzer und Bücher bleiben unverändert.
"""

import time

from werkzeug.security import generate_password_hash

import app

# Passwort = Benutzername; der Admin kommt wie immer aus ADMIN_USER/ADMIN_PASSWORD
DEMO_USERS = ["demo", "anna"]

DEMO_BOOKS = [
    # (isbn, title, author, year, description, {user: (rating, is_read, is_owned)})
    ("9780547928227", "The Hobbit", "J. R. R. Tolkien", 1937,
     "Bilbo Beutlin wird von Gandalf und dreizehn Zwergen auf eine Reise zum Einsamen Berg mitgenommen.",
     {"demo": (5, 1, 1), "anna": (4, 1, 0)}),
    ("9780261103573", "The Fellowship of the Ring", "J. R. R. Tolkien", 1954,
     "Erster Teil des Herrn der Ringe: Frodo bricht auf, um den Einen Ring zu vernichten.", {"demo": (5, 1, 1), "anna": (None, 0, 1)}),
    ("9780451524935", "Nineteen Eighty-Four", "George Orwell", 1949,
     "Dystopie über Überwachung, Gedankenkontrolle und den Großen Bruder.", {"demo": (4, 1, 1), "anna": (5, 1, 1)}),
    ("9780441172719", "Dune", "Frank Herbert", 1965,
     "Wüstenplanet Arrakis, das Spice und der Aufstieg von Paul Atreides.", {"demo": (None, 0, 1), "anna": (None, 0, 1)}),
    ("9780345391803", "The Hitchhiker's Guide to the Galaxy", "Douglas Adams", 1979,
     "Kurz bevor die Erde gesprengt wird, trampt Arthur Dent ins All. Don't panic!", {"demo": (4, 1, 0), "anna": (5, 1, 1)}),
    ("9780743273565", "The Great Gatsby", "F. Scott Fitzgerald", 1925,
     "Jay Gatsby, Daisy Buchanan und der amerikanische Traum in den Roaring Twenties.", {"demo": (None, 0, 0), "anna": (3, 1, 1)}),
    ("9780141439518", "Pride and Prejudice", "Jane Austen", 1813,
     "Elizabeth Bennet und Mr. Darcy – Stolz und Vorurteil.", {"anna": (5, 1, 1)}),
    ("9780061120084", "To Kill a Mockingbird", "Harper Lee", 1960,
     "Scout Finch erlebt, wie ihr Vater einen zu Unrecht angeklagten Schwarzen verteidigt.", {"demo": (4, 1, 1), "anna": (4, 1, 1)}),
    ("9780553380163", "A Brief History of Time", "Stephen Hawking", 1988,
     "Vom Urknall bis zu Schwarzen Löchern – Kosmologie für alle.", {"demo": (None, 0, 1)}),
    ("9780316769488", "The Catcher in the Rye", "J. D. Salinger", 1951,
     "Holden Caulfield irrt drei Tage durch New York.", {"demo": (3, 1, 1)}),
    ("9780140449136", "Crime and Punishment", "Fjodor Dostojewski", 1866,
     "Raskolnikow begeht einen Mord und ringt mit Schuld und Gewissen.", {"anna": (None, 0, 1)}),
    ("9780439708180", "Harry Potter and the Sorcerer's Stone", "J. K. Rowling", 1997,
     "Harry erfährt an seinem elften Geburtstag, dass er ein Zauberer ist.", {"demo": (None, 0, 1), "anna": (None, 0, 0)}),
]


def seed():
    """Legt fehlende Demo-Nutzer und -Bücher an; liefert die Namen der neu angelegten Nutzer."""
    db = app.db()
    created = []
    for name in DEMO_USERS:
        cur = db.execute("INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)",
                         (name, generate_password_hash(name)))
        if cur.rowcount:
            created.append(name)
    ids = {name: db.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()["id"]
           for name in DEMO_USERS}
    for isbn, title, author, year, desc, users in DEMO_BOOKS:
        if db.execute("SELECT 1 FROM books WHERE isbn = ?", (isbn,)).fetchone():
            continue
        # OpenLibrary Fair Use: höchstens 1 Anfrage pro Sekunde
        found = app.lookup_isbn(isbn)
        time.sleep(1)
        cover, mime = app.fetch_cover(found["cover_url"] if found else None)
        time.sleep(1)
        cur = db.execute(
            "INSERT INTO books (title, author, year, isbn, description, cover, cover_mime) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, author, year, isbn, desc, cover, mime))
        for name, (rating, is_read, is_owned) in users.items():
            db.execute("INSERT INTO user_books (user_id, book_id, rating, is_read, is_owned) VALUES (?, ?, ?, ?, ?)",
                       (ids[name], cur.lastrowid, rating, is_read, is_owned))
        db.commit()  # pro Buch, damit ein Abbruch den Fortschritt behält
        print(f"  {title} ({'mit' if cover else 'ohne'} Cover)")
    db.commit()
    return created


if __name__ == "__main__":
    print(f"Demo-Daten für {app.DB_PATH} …")
    with app.app.app_context():
        created = seed()
    print("Fertig. Neu angelegte Logins (Passwort = Benutzername):", ", ".join(created) or "keine")
