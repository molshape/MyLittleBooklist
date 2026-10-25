CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0
);

-- Gemeinsamer Katalog: jedes Buch existiert einmal, Beschreibung gilt für alle.
CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT '',
    year        INTEGER,
    isbn        TEXT UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    cover       BLOB,
    cover_mime  TEXT
);

-- Sammlung eines Users inkl. persönlicher Bewertung (1–5, NULL = keine) und Flags.
CREATE TABLE IF NOT EXISTS user_books (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id  INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    rating   INTEGER CHECK (rating BETWEEN 1 AND 5),
    is_read  INTEGER NOT NULL DEFAULT 0,
    is_owned INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, book_id)
);
