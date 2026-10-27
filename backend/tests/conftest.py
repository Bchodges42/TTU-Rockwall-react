"""Shared fixtures: every test gets its own database file and no network access."""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.database_service import db_session


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("ROCKWALL_DB_PATH", str(tmp_path / "rockwall.db"))
    monkeypatch.setenv("ROCKWALL_TIMEZONE", "America/Chicago")
    monkeypatch.setenv("ROCKWALL_COOKIE_SECURE", "0")
    monkeypatch.setenv("ROCKWALL_HOURS_SYNC", "0")
    monkeypatch.delenv("ROCKWALL_SMTP_HOST", raising=False)
    monkeypatch.setenv("ROCKWALL_PUBLIC_URL", "https://climb.example.test")


def open_all_week(opens="06:00", closes="22:00"):
    """Tests run at any hour on any weekday; give them a wall that is open every day."""
    with db_session(write=True) as db:
        db.execute("UPDATE operating_hours SET opens=?,closes=?", (opens, closes))


@pytest.fixture
def client():
    with TestClient(app) as client:
        open_all_week()
        yield client
