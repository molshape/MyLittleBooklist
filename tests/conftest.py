import os
import tempfile
from pathlib import Path

os.environ.update(
    DB_PATH=os.path.join(tempfile.mkdtemp(), "test.db"),
    ADMIN_USER="admin",
    ADMIN_PASSWORD="secret",
    SECRET_KEY="test",
)

import pytest  # noqa: E402
from flask.testing import FlaskClient  # noqa: E402

from mylittlebooklist import database  # noqa: E402
from mylittlebooklist.app import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    with app.app_context():
        database.init_db()


@pytest.fixture
def client() -> FlaskClient:
    app.config["TESTING"] = True
    return app.test_client()
