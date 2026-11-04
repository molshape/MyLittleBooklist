# <img src="src/mylittlebooklist/static/logo.svg" alt="" height="48"> My Little Booklist

[![CI](https://github.com/molshape/MyLittleBooklist/actions/workflows/ci.yml/badge.svg)](https://github.com/molshape/MyLittleBooklist/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/tag/molshape/MyLittleBooklist?sort=semver&label=version)](https://github.com/molshape/MyLittleBooklist/tags)
[![License: MIT](https://img.shields.io/github/license/molshape/MyLittleBooklist)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
[![Docker image](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker&logoColor=white)](https://github.com/molshape/MyLittleBooklist/pkgs/container/mylittlebooklist)

A lightweight, self-hosted web app to track your personal reading history. Unlike traditional library managers that focus on shelf inventory, **My Little Booklist** is designed to be a simple archive of the books you have read or want to read – perfect for building a digital "Read" list without the overhead of full library management systems.

## Features

- **Reading History Focus:** \
    Manage your personal journey through books, not just the ones sitting on your shelf.
- **Automated Metadata via ISBN lookup:** \
    Add a book via ISBN and let the app fetch the title, author, year, description, and cover art automatically from [Open Library](https://openlibrary.org).
- **Cover Gallery & Search:** \
    Browse a visual gallery with detail pages and perform full-text search across all fields.
- **Shared & Personal Experience:** \
    Support for multiple users with a shared catalog: book data is entered once and shared, while each user maintains their own personal collection, 1–5 star ratings, and "_read_/_owned_" flags.
- **Personal Categories:** \
    Sort your books into your own categories, shown as collapsible shelves. A book can be on several shelves. Rename, merge or delete a category directly on its shelf.
- **Smart Filtering:** \
    Easily filter your collection by _read_/_unread_ or _owned_/_not owned_ status.
- **Seamless User Experience:**
    - Dark/light mode support.
    - Multilingual UI (currently English and German), automatically detected from your browser.
    - Admin-managed user accounts with individual password management.
- **Simple & Portable:** \
    Everything lives in a single **SQLite** file (including cover images). One file = a complete, easy-to-handle backup.

## Tech stack

[Flask](https://flask.palletsprojects.com/) · SQLite · [Pico CSS](https://picocss.com/) · [isbnlib](https://pypi.org/project/isbnlib/) · [Flask-Babel](https://python-babel.github.io/flask-babel/) · Gunicorn · Docker · [uv](https://docs.astral.sh/uv/)

## Quick start (Docker)

Requires Docker with Compose.

```sh
git clone https://github.com/molshape/MyLittleBooklist.git && cd MyLittleBooklist
cp .env.example .env      # set SECRET_KEY and ADMIN_PASSWORD
docker compose up -d
```

This downloads the prebuilt image of the latest release. To build from source instead, use `docker compose up -d --build`.

Open http://localhost:8000 and log in with `ADMIN_USER` / `ADMIN_PASSWORD` from `.env`.

The database is created empty on first start and lives in the `my-little-booklist-data` volume (`/data/books.db`). To start over, run `docker compose down -v` (⚠️ deletes all data).

## Configuration

All settings are read from environment variables (via `.env` with Docker):

| Variable         | Default                        | Description |
|------------------|--------------------------------|-------------|
| `SECRET_KEY`     | random on each start           | Signs session cookies. Set it, otherwise all users are logged out on every restart. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `ADMIN_USER`     | `admin`                        | Name of the first admin account. |
| `ADMIN_PASSWORD` | random, printed to the log     | Password of the first admin account. |
| `DB_PATH`        | `books.db` (`/data/books.db` in Docker) | Path to the SQLite database. |

The admin account is only created when the database has no users yet; changing `ADMIN_USER`/`ADMIN_PASSWORD` later has no effect on existing accounts.

## Backup and updates

The whole library – books, covers, users and ratings – is in the one SQLite file. With Docker, copy it out of the container:

```sh
docker compose cp my-little-booklist:/data/books.db ./books-backup.db
```

To update to the latest release:

```sh
docker compose pull && docker compose up -d
```

The database is migrated automatically on start. Before migrating, the app saves a backup next to it (`/data/books.db.v<version>.bak`).

## Demo data (optional)

To try the app with sample content, add two users (`demo`:`demo`, `anna`:`anna`) and 12 books including covers – 10 books per user, 8 of them owned, 6 read and 8 in categories:

```sh
docker compose exec my-little-booklist python -m mylittlebooklist.demo
```

- Takes about a minute and needs internet access: book data and covers come from Open Library, at most one request per second in line with their fair-use rules.
- Safe to run repeatedly: existing users and books are left unchanged.

## Development

Running the app locally, checks, project layout, schema changes and translations are described in [docs/development.md](docs/development.md).

## Contributing

Bug reports, fixes, small improvements and new translations are welcome – the app is kept deliberately simple, though. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

Book data and covers via [Open Library](https://openlibrary.org) (Internet Archive). Cover images remain the property of their respective rights holders.

Built with the help of [Claude Code](https://claude.com/claude-code).

## License

[MIT](LICENSE) © 2026 Axel Müller
