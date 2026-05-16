# -*- coding: utf-8 -*-

import pytest
from pathlib import Path


def pytest_configure(config):
    """Ensure a minimal config.yaml exists so app modules can be imported."""
    if not Path('config.yaml').exists():
        Path('config.yaml').write_text('DEFAULT_MOBILE_REGION:\nDEVICES: {}\n')


@pytest.fixture
def fresh_db(monkeypatch):
    """Redirect all DB operations to a fresh in-memory SQLite database."""
    from app.db import BaseDB, SIMCardDB, PendingSMSDB, SmsDB

    monkeypatch.setattr(BaseDB, '_DB_FILE_NAME', ':memory:')

    th_local = BaseDB._threading_local
    if hasattr(th_local, 'db'):
        th_local.db.close()
        del th_local.db

    # Create all tables in the new in-memory connection.
    for cls in (SIMCardDB, PendingSMSDB, SmsDB):
        cls()

    yield

    if hasattr(th_local, 'db'):
        th_local.db.close()
        del th_local.db


@pytest.fixture
def flask_app(fresh_db):
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()
