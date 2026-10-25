# 📚 MyTinyBookLog

Kleine, selbst gehostete Verwaltung der eigenen Bücher (nur bibliographische Daten, keine E-Books).

- Cover-Galerie, Detailseite, Bearbeiten, Suche über alle Felder
- ISBN-Lookup inkl. Cover (Large) über [OpenLibrary](https://openlibrary.org/developers/api)
- Gemeinsamer Katalog: Beschreibung gilt für alle, Bewertung ist pro Benutzer
- Benutzerverwaltung durch Admin, Dark/Light Mode
- Flask + SQLite (Cover liegen in der DB → eine Datei = komplettes Backup)

## Start mit Docker

```sh
cp .env.example .env      # SECRET_KEY und ADMIN_PASSWORD setzen, DEMO=1 für Demo-Daten
docker compose up -d --build
```

→ http://localhost:8000. Demo-Logins: `admin/admin`, `demo/demo`, `anna/anna`.
Die Datenbank liegt im Volume `booklog-data` (`/data/books.db`).

## Entwicklung (uv)

```sh
uv sync
DEMO=1 uv run flask --app app run --debug
uv run pytest
uv run flask --app app seed-demo   # Demo-Daten in bestehende DB laden
```

## Demo-Datenbank

`demo.db` ist eine fertige Demo-Datenbank (12 Bücher inkl. Cover, Logins `admin/admin`,
`demo/demo`, `anna/anna`). Sie ist **nicht im Git-Repository** (`.gitignore`), weil die
Cover von OpenLibrary stammen, und muss nach dem Klonen einmal lokal erzeugt werden:

```sh
rm -f demo.db
DB_PATH=demo.db uv run flask --app app seed-demo                         # ~1 Minute
uv run python -c "import sqlite3; sqlite3.connect('demo.db').execute('VACUUM')"  # verkleinern
```

`seed-demo` fragt OpenLibrary gemäß deren Fair-Use-Regeln mit höchstens einer Anfrage pro
Sekunde ab (Buchdaten + Cover je Buch). Die Demo-Bücher selbst stehen in `DEMO_BOOKS` in `app.py`.

So wird sie verwendet:

- `docker compose up --build` packt eine vorhandene `demo.db` ins Image.
- Beim Start mit `DEMO=1` und noch **nicht vorhandener** Datenbank wird `demo.db` kopiert –
  der Container ist sofort bereit.
- Fehlt `demo.db`, wird die Demo stattdessen beim ersten Start über OpenLibrary erzeugt
  (der Container braucht dann ~1 Minute, bis er antwortet).
- Eine bestehende Datenbank wird nie überschrieben. Neu anfangen: `docker compose down -v`.
