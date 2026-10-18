import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    # app.py runs init_db()/seed_db() at import time, so DB_PATH must point at
    # the temp file before `app` is first imported — never import it at module
    # level in a test file.
    import database.db as db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))

    from app import app as flask_app

    monkeypatch.setitem(flask_app.config, "TESTING", True)

    # The imported module is cached, so every test needs its own fresh schema
    # and demo user in its own temp database.
    db.init_db()
    db.seed_db()

    yield flask_app
