"""ISBN helpers and access to the OpenLibrary API."""

import json
import re
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import isbnlib

USER_AGENT = {"User-Agent": "MyLittleBooklist/0.1 (private home library)"}
COVER_PREFIX = "https://covers.openlibrary.org/"
# Never SVG or similar: covers are served from our origin, where scripts in them would run
COVER_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def normalize_isbn(raw: str | None) -> str | None:
    isbn = re.sub(r"[^0-9Xx]", "", raw or "").upper()
    return isbn if len(isbn) in (10, 13) else None


def format_isbn(isbn: str) -> str:
    """Hyphenated according to the official ISBN range table; invalid ISBNs unchanged."""
    try:
        return isbnlib.mask(isbn) or isbn
    except isbnlib.NotValidISBNError:
        return isbn


def lookup_isbn(isbn: str) -> dict[str, Any] | None:
    """Returns dict(title, author, year, cover_url), or None if unknown/offline."""
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        with urlopen(Request(url, headers=USER_AGENT), timeout=10) as resp:  # nosec B310
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


def fetch_cover(url: str | None) -> tuple[bytes | None, str | None]:
    """Downloads a cover from OpenLibrary; only this domain, so the server never fetches arbitrary URLs."""
    if not url or not url.startswith(COVER_PREFIX):
        return None, None
    try:
        with urlopen(Request(url, headers=USER_AGENT), timeout=15) as resp:  # nosec B310
            mime = resp.headers.get_content_type()
            return (resp.read(), mime) if mime in COVER_MIMES else (None, None)
    except (URLError, TimeoutError):
        return None, None
