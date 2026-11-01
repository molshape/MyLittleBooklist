"""User management for admins."""

import sqlite3

from flask import abort, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _
from werkzeug.security import generate_password_hash

from mylittlebooklist.app import app
from mylittlebooklist.database import db, remove_orphans
from mylittlebooklist.routes.auth import admin_required


@app.route("/users", methods=["GET", "POST"])
@admin_required
def users() -> ResponseReturnValue:
    if request.method == "POST":
        name, password = request.form.get("username", "").strip(), request.form.get("password", "")
        if not name or len(password) < 4:
            flash(_("Enter a username and a password (at least 4 characters)."), "error")
        else:
            try:
                db().execute(
                    "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                    (name, generate_password_hash(password), int("is_admin" in request.form)),
                )
                db().commit()
                flash(_("User “%(name)s” created.", name=name), "ok")
            except sqlite3.IntegrityError:
                flash(_("Username already exists."), "error")
        return redirect(url_for("users"))
    rows = (
        db()
        .execute(
            """SELECT u.id, u.username, u.is_admin, COUNT(ub.book_id) AS books
           FROM users u LEFT JOIN user_books ub ON ub.user_id = u.id
           GROUP BY u.id ORDER BY u.username COLLATE NOCASE"""
        )
        .fetchall()
    )
    return render_template("users.html", users=rows)


@app.post("/users/<int:user_id>/<action>")
@admin_required
def user_action(user_id: int, action: str) -> ResponseReturnValue:
    if user_id == g.user["id"] and action in ("delete", "toggle_admin"):
        flash(_("You cannot delete yourself or remove your own admin rights."), "error")
    elif action == "delete":
        db().execute("DELETE FROM users WHERE id = ?", (user_id,))
        remove_orphans()
        flash(_("User deleted."), "ok")
    elif action == "toggle_admin":
        db().execute("UPDATE users SET is_admin = 1 - is_admin WHERE id = ?", (user_id,))
    elif action == "password":
        password = request.form.get("password", "")
        if len(password) < 4:
            flash(_("Password must be at least 4 characters long."), "error")
        else:
            db().execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(password), user_id),
            )
            flash(_("Password reset."), "ok")
    else:
        abort(404)
    db().commit()
    return redirect(url_for("users"))
