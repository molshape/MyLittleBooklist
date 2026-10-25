# 📚 MyTinyBookLog

Kleine, selbst gehostete Verwaltung der eigenen Bücher (nur bibliographische Daten, keine E-Books).

- Cover-Galerie, Detailseite, Bearbeiten, Suche über alle Felder
- ISBN-Lookup inkl. Cover (Large) über [OpenLibrary](https://openlibrary.org/developers/api)
- Gemeinsamer Katalog: Beschreibung gilt für alle, Bewertung ist pro Benutzer
- Benutzerverwaltung durch Admin, Dark/Light Mode
- Flask + SQLite (Cover liegen in der DB → eine Datei = komplettes Backup)

## Start mit Docker

```sh
cp .env.example .env      # SECRET_KEY und ADMIN_PASSWORD setzen
docker compose up -d --build
```

→ http://localhost:8000, Login mit `ADMIN_USER`/`ADMIN_PASSWORD` aus `.env`.
Die Datenbank wird beim ersten Start leer angelegt und liegt im Volume `booklog-data`
(`/data/books.db`). Neu anfangen: `docker compose down -v`.

## Entwicklung (uv)

```sh
uv sync
ADMIN_PASSWORD=admin uv run flask --app app run --debug   # legt books.db an
uv run pytest
```

## Demo-Daten (optional)

`demo.py` füllt eine Datenbank mit zwei Beispielnutzern (`demo/demo`, `anna/anna`) und
12 Büchern inkl. Cover – je Nutzer 10 Bücher, davon 8 in Besitz und 6 gelesen:

```sh
uv run python demo.py                          # lokal (DB_PATH, Standard books.db)
docker compose exec booklog python demo.py     # im laufenden Container
```

- Dauert ~1 Minute und braucht Internet: Buchdaten und Cover kommen von OpenLibrary, gemäß
  deren Fair-Use-Regeln mit höchstens einer Anfrage pro Sekunde.
- Mehrfach ausführbar: vorhandene Nutzer und Bücher bleiben unverändert.
- Der Admin kommt wie immer aus `ADMIN_USER`/`ADMIN_PASSWORD`.
- Die Demo-Bücher stehen in `DEMO_BOOKS` in `demo.py`.
