from flask.testing import FlaskClient


def test_language_follows_browser(client: FlaskClient) -> None:
    r = client.get("/login")
    assert '<html lang="en">' in r.text and "Log in" in r.text
    r = client.get("/login", headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
    assert '<html lang="de">' in r.text and "Anmelden" in r.text
    assert (
        "Log in" in client.get("/login", headers={"Accept-Language": "eo"}).text
    )  # unknown -> English
