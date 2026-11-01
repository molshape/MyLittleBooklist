from flask.testing import FlaskClient

from tests.helpers import login, post


def test_login_required(client: FlaskClient) -> None:
    assert client.get("/").status_code == 302


def test_login_needs_csrf_token(client: FlaskClient) -> None:
    assert (
        client.post("/login", data={"username": "admin", "password": "secret"}).status_code == 400
    )


def test_login_session_is_permanent(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    with client.session_transaction() as s:
        assert s.permanent


def test_new_login_renews_csrf_token(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    with client.session_transaction() as s:
        old_token = s["csrf"]
    post(client, "/users", username="bob", password="bobpw")
    client.post("/logout", data={"csrf": old_token})
    login(client, "bob", "bobpw")
    with client.session_transaction() as s:
        assert s["csrf"] != old_token
