# 📚 My Little Booklist

A small, self-hosted web app to catalog the books on your shelf – for yourself, your family or a shared flat. It manages bibliographic data only (no e-books, no reading of files).

Add a book by its ISBN and title, author, year, description and cover are fetched automatically from [Open Library](https://openlibrary.org). Everything lives in a single SQLite file, so a backup is just one copy.

## Features

- **Cover gallery** with detail pages, editing and full-text search across all fields
- **ISBN lookup** including large cover image via the Open Library API
- **Multiple users** with a shared catalog: book data is entered once and shared, while each user has their own collection, 1–5 star rating and *read* / *owned* flags
- **Filters** for read/unread and owned/not owned
- **User management** by the admin, password change for every user
- **Dark/light mode**
- **Multilingual UI**: English and German, chosen automatically from the browser language
- **Single-file storage**: covers are stored inside the database → one file = complete backup

## Tech stack

[Flask](https://flask.palletsprojects.com/) · SQLite · [Pico CSS](https://picocss.com/) · [isbnlib](https://pypi.org/project/isbnlib/) · [Flask-Babel](https://python-babel.github.io/flask-babel/) · Gunicorn · Docker · [uv](https://docs.astral.sh/uv/)

## Quick start (Docker)

Requires Docker with Compose.

```sh
git clone <repository-url> && cd MyLittleBooklist
cp .env.example .env      # set SECRET_KEY and ADMIN_PASSWORD
docker compose up -d --build
```

Open http://localhost:8000 and log in with `ADMIN_USER` / `ADMIN_PASSWORD` from `.env`.

The database is created empty on first start and lives in the `booklog-data` volume (`/data/books.db`). To start over, run `docker compose down -v` (⚠️ deletes all data).

## Configuration

All settings are read from environment variables (via `.env` with Docker):

| Variable         | Default                        | Description |
|------------------|--------------------------------|-------------|
| `SECRET_KEY`     | random on each start           | Signs session cookies. Set it, otherwise all users are logged out on every restart. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `ADMIN_USER`     | `admin`                        | Name of the first admin account. |
| `ADMIN_PASSWORD` | random, printed to the log     | Password of the first admin account. |
| `DB_PATH`        | `books.db` (`/data/books.db` in Docker) | Path to the SQLite database. |

The admin account is only created when the database has no users yet; changing `ADMIN_USER`/`ADMIN_PASSWORD` later has no effect on existing accounts.

## Backup

The whole library – books, covers, users and ratings – is in the one SQLite file. With Docker, copy it out of the container:

```sh
docker compose cp booklog:/data/books.db ./books-backup.db
```

## Development

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pybabel compile -d translations                    # builds the .mo files
ADMIN_PASSWORD=admin uv run flask --app app run --debug   # creates books.db
uv run pytest
uv run ruff check . && uv run ruff format --check .       # lint and formatting
uv run mypy .                                             # type check
uv run bandit -r app.py demo.py                           # security scan
uv run pip-audit                                          # known vulnerabilities in dependencies
```

### Project layout

```text
app.py          Flask app: routes, auth, Open Library lookup
schema.sql      database schema (created automatically on start)
demo.py         optional demo data loader
templates/      Jinja templates
static/         CSS and logo
translations/   translation template (messages.pot) and catalogs per language (messages.po)
babel.cfg       extraction config for pybabel
test_app.py     tests
```

### Translating

UI texts are written in English and marked with `_("…")` in `app.py` and the templates. The language is picked from the browser's `Accept-Language` header; English is the fallback. Every language folder in `translations/` is picked up automatically – no code change needed.

```sh
uv run pybabel extract -F babel.cfg --project="My Little Booklist" -o translations/messages.pot .   # after changing texts
uv run pybabel update -i translations/messages.pot -d translations       # merge new texts into all languages
uv run pybabel init -i translations/messages.pot -d translations -l eo   # new language, e.g. eo = Esperanto
uv run pybabel compile -d translations                                   # build the .mo files
```

Then translate the entries in `translations/<lang>/LC_MESSAGES/messages.po`. The compiled `.mo` files are not committed. They are compiled by Docker build.

## Demo data (optional)

`demo.py` fills a database with two sample users (`demo`:`demo`, `anna`:`anna`) and 12 books including covers – 10 books per user, 8 of them owned and 6 read:

```sh
uv run python demo.py                          # locally (uses DB_PATH, default books.db)
docker compose exec booklog python demo.py     # inside the running container
```

- Takes about a minute and needs internet access: book data and covers come from Open Library, at most one request per second in line with their fair-use rules.
- Safe to run repeatedly: existing users and books are left unchanged.
- The admin account still comes from `ADMIN_USER` / `ADMIN_PASSWORD`.
- The demo books are defined in `DEMO_BOOKS` in `demo.py`.

## Contributing

Bug reports, fixes, small improvements and new translations are welcome – the app is kept deliberately simple, though. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

Book data and covers via [Open Library](https://openlibrary.org) (Internet Archive). Cover images remain the property of their respective rights holders.

Built with the help of [Claude Code](https://claude.com/claude-code).

## License

[MIT](LICENSE) © 2026 Axel Müller
