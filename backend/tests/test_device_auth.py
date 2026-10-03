"""
Device API key check on POST /api/v1/recordings.

No database needed: the key dependency runs before the upload is
parsed, so a rejected request never reaches PostgreSQL, and an
accepted empty request stops at form validation (422).

    cd backend
    python -m pytest tests/test_device_auth.py -v
"""

import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.server import app

UPLOAD_URL = "/api/v1/recordings"
KEY = "test-device-key-123"


@pytest.fixture
def client():
    # Not used as a context manager, so the app's lifespan (which
    # checks the database) does not run.
    return TestClient(app)


@pytest.fixture
def key_required(monkeypatch):
    monkeypatch.setattr(settings, "device_api_key", KEY)


def test_missing_key_is_rejected(client, key_required):
    response = client.post(UPLOAD_URL)

    assert response.status_code == 401
    assert "invalid_device_key" in response.text


def test_wrong_key_is_rejected(client, key_required):
    response = client.post(
        UPLOAD_URL, headers={"X-Device-Key": "wrong-key"}
    )

    assert response.status_code == 401


def test_correct_key_reaches_validation(client, key_required):
    response = client.post(
        UPLOAD_URL, headers={"X-Device-Key": KEY}
    )

    # Authenticated; rejected only because the form is empty.
    assert response.status_code == 422


def test_no_key_configured_skips_check(client, monkeypatch):
    monkeypatch.setattr(settings, "device_api_key", None)

    response = client.post(UPLOAD_URL)

    assert response.status_code == 422


def test_other_endpoints_stay_open(client, key_required):
    # Only the device upload is protected.
    response = client.get("/health")

    assert response.status_code == 200
