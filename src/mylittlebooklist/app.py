"""My Little Booklist – a small home library manager."""

import os
import secrets
from datetime import timedelta

from flask import Flask, request
from flask_babel import Babel, get_locale

from mylittlebooklist import database, openlibrary

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)
if not os.environ.get("SECRET_KEY"):
    app.logger.warning("SECRET_KEY not set – sessions only last until the next restart.")

# UI language follows the browser; every folder in translations/ is picked up automatically
babel: Babel = Babel(
    app,
    locale_selector=lambda: request.accept_languages.best_match(
        [str(locale) for locale in babel.list_translations()]
    ),
)
app.jinja_env.globals["get_locale"] = get_locale

app.teardown_appcontext(database.close_db)
app.add_template_filter(openlibrary.format_isbn, "isbn")

# Routes register themselves on app, so they can only be imported once it exists
from mylittlebooklist.routes import auth, books, users  # noqa: E402,F401

with app.app_context():
    database.init_db()
