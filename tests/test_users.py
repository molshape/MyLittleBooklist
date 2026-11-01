from flask.testing import FlaskClient

from tests.helpers import login, post


def test_user_management_is_admin_only(client: FlaskClient) -> None:
    login(client, "admin", "secret")
    post(client, "/users", username="bob", password="bobpw")
    post(client, "/logout")
    login(client, "bob", "bobpw")
    assert client.get("/users").status_code == 403
