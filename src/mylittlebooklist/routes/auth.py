"""Login, session handling, CSRF protection and the account page."""

import secrets
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from werkzeug.security import check_password_hash, generate_password_hash

from mylittlebooklist.app import app
from mylittlebooklist.database import db


@app.before_request
def load_user_and_check_csrf() -> None:
    g.user = None
    if uid := session.get("uid"):
        g.user = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        token = session.get("csrf")
        if not token or not secrets.compare_digest(token, request.form.get("csrf", "")):
            abort(400, _("Invalid form token – please reload the page."))


@app.context_processor
def inject_csrf() -> dict[str, str]:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return {"csrf": session["csrf"]}


def login_required(view: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
    @wraps(view)
    @login_required
    def wrapped(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    if request.method == "POST":
        user = (
            db()
            .execute(
                "SELECT * FROM users WHERE username = ?",
                (request.form.get("username", "").strip(),),
            )
            .fetchone()
        )
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            # Fresh session on every login (prevents session fixation), valid for 30 days.
            session.clear()
            session.permanent = True
            session["uid"] = user["id"]
            session["csrf"] = secrets.token_urlsafe(32)
            nxt = request.args.get("next", "")
            return redirect(
                nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("gallery")
            )
        flash(_("Wrong username or password."), "error")
    return render_template("login.html")


@app.post("/logout")
def logout() -> ResponseReturnValue:
    session.clear()
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account() -> ResponseReturnValue:
    if request.method == "POST":
        new = request.form.get("new_password", "")
        if not check_password_hash(g.user["password_hash"], request.form.get("old_password", "")):
            flash(_("Current password is wrong."), "error")
        elif len(new) < 4:
            flash(_("New password must be at least 4 characters long."), "error")
        else:
            db().execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), g.user["id"]),
            )
            db().commit()
            flash(_("Password changed."), "ok")
            return redirect(url_for("gallery"))
    return render_template("account.html")
