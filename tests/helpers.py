from flask.testing import FlaskClient
from werkzeug.test import TestResponse


def csrf(client: FlaskClient) -> str:
    client.get("/login")
    with client.session_transaction() as s:
        return str(s["csrf"])


def login(client: FlaskClient, user: str, password: str) -> TestResponse:
    return client.post(
        "/login", data={"username": user, "password": password, "csrf": csrf(client)}
    )


def post(client: FlaskClient, url: str, **data: str) -> TestResponse:
    with client.session_transaction() as s:
        data["csrf"] = s["csrf"]
    return client.post(url, data=data, follow_redirects=True)
