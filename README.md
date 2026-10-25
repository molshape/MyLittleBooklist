# 📚 My Little Booklist

Small, self-hosted manager for your own books (bibliographic data only, no e-books).

- Cover gallery, detail page, editing, search across all fields
- ISBN lookup incl. cover (large) via [OpenLibrary](https://openlibrary.org/developers/api)
- Shared catalog: the description applies to everyone, ratings are per user
- User management by the admin, dark/light mode
- `Flask` + `SQLite` (covers are stored in the DB → one file = complete backup)

## Running with Docker

```sh
cp .env.example .env      # set `SECRET_KEY` and `ADMIN_PASSWORD`
docker compose up -d --build
```

→ http://localhost:8000, log in with `ADMIN_USER`/`ADMIN_PASSWORD` from `.env`.
The database is created empty on first start and lives in the `booklog-data` volume
(`/data/books.db`). To start over: `docker compose down -v`.

## Development (uv)

```sh
uv sync
ADMIN_PASSWORD=admin uv run flask --app app run --debug   # creates `books.db`
uv run pytest
```

## Demo data (optional)

`demo.py` fills a database with two sample users (`demo:demo`, `anna:anna`) and
12 books incl. covers – 10 books per user, 8 of them owned and 6 read:

```sh
uv run python demo.py                          # locally (`DB_PATH`, default `books.db`)
docker compose exec booklog python demo.py     # inside the running container
```

- Takes ~1 minute and needs internet access: book data and covers come from OpenLibrary,
  at most one request per second in line with their fair-use rules.
- Safe to run repeatedly: existing users and books are left unchanged.
- The admin comes from `ADMIN_USER`/`ADMIN_PASSWORD` as always.
- The demo books are defined in `DEMO_BOOKS` in `demo.py`.
