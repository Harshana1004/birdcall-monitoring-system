"""
End-to-end checks for accounts, device claiming and per-user access.

Runs the real app against the database in backend/.env (migrated to
head). Everything it creates uses a random suffix and is deleted at
the end. BirdNET is not run: the upload's background job is replaced
by a no-op and one detection is inserted directly.

    cd backend
    python -m pytest tests/test_accounts_and_access.py -v
"""

import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import src.api.recordings as recordings_api
from src.core.config import settings
from src.database import AsyncSessionLocal
from src.models import Detection, Device, Recording, User
from src.server import app

SUFFIX = uuid.uuid4().hex[:8]
PASSWORD = "correct-horse-battery"
DEVICE_CODE = f"TEST-{SUFFIX.upper()}"


def email(name: str) -> str:
    return f"{name}-{SUFFIX}@example.com"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _noop_processing(recording_id):
    return None


@pytest.fixture(scope="module")
def ctx():
    monkey = pytest.MonkeyPatch()
    monkey.setattr(recordings_api, "process_recording_background", _noop_processing)
    monkey.setattr(settings, "device_api_key", None)

    with TestClient(app) as client:
        state = {"client": client, "portal": client.portal, "files": []}
        try:
            yield state
        finally:
            state["portal"].call(_cleanup, state["files"])
    monkey.undo()


async def _cleanup(files: list[str]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Device).where(Device.device_code == DEVICE_CODE))
        await session.execute(delete(User).where(User.email.like(f"%-{SUFFIX}@example.com")))
        await session.commit()
    for path in files:
        Path(path).unlink(missing_ok=True)


async def _make_admin(user_email: str) -> None:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == user_email))
        user.is_admin = True
        await session.commit()


async def _add_detection(recording_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Detection(
                recording_id=recording_id,
                scientific_name="Copsychus saularis",
                common_name="Oriental Magpie-Robin",
                confidence=0.87,
                start_time_seconds=0.5,
                end_time_seconds=1.0,
                model_name="BirdNET",
                model_version="2.4",
            )
        )
        await session.commit()


def register(client, name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email(name), "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def wav_bytes(seconds: float = 1.0) -> bytes:
    rate = 16000
    t = np.arange(int(seconds * rate)) / rate
    buffer = io.BytesIO()
    sf.write(buffer, 0.3 * np.sin(2 * np.pi * 3000 * t), rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def test_full_flow(ctx):
    client, portal = ctx["client"], ctx["portal"]

    # ---- accounts ---------------------------------------------------
    assert client.get("/api/v1/devices").status_code == 401

    admin_token = register(client, "admin")
    portal.call(_make_admin, email("admin"))
    alice = register(client, "alice")
    bob = register(client, "bob")

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": email("ALICE"), "password": PASSWORD},
    )
    assert duplicate.status_code == 409

    short = client.post(
        "/api/v1/auth/register",
        json={"email": email("carol"), "password": "short"},
    )
    assert short.status_code == 422

    assert client.post(
        "/api/v1/auth/login", json={"email": email("alice"), "password": "wrong-password"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": email("nobody"), "password": PASSWORD}
    ).status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": email("Alice"), "password": PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["user"]["is_admin"] is False

    me = client.get("/api/v1/auth/me", headers=bearer(alice))
    assert me.json()["email"] == email("alice")
    assert client.get("/api/v1/auth/me", headers=bearer("not-a-token")).status_code == 401

    # ---- admin creates a device ------------------------------------
    assert client.post(
        "/api/v1/devices", json={"device_code": DEVICE_CODE, "name": "x"}, headers=bearer(alice)
    ).status_code == 403

    created = client.post(
        "/api/v1/devices",
        json={"device_code": DEVICE_CODE.lower(), "name": "Test node"},
        headers=bearer(admin_token),
    )
    assert created.status_code == 201, created.text
    device_id = created.json()["device"]["id"]
    claim_code = created.json()["claim_code"]
    assert created.json()["device"]["device_code"] == DEVICE_CODE
    assert created.json()["device"]["owner"] is None

    # ---- claiming ---------------------------------------------------
    wrong = client.post(
        "/api/v1/devices/claim",
        json={"device_code": DEVICE_CODE, "claim_code": "AAAA-BBBB-CCCC"},
        headers=bearer(bob),
    )
    assert wrong.status_code == 400

    claimed = client.post(
        "/api/v1/devices/claim",
        # Case/spacing of the claim code does not matter.
        json={"device_code": DEVICE_CODE.lower(), "claim_code": claim_code.lower().replace("-", " ")},
        headers=bearer(alice),
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["owner"]["email"] == email("alice")

    taken = client.post(
        "/api/v1/devices/claim",
        json={"device_code": DEVICE_CODE, "claim_code": claim_code},
        headers=bearer(bob),
    )
    assert taken.status_code == 409

    # ---- visibility of devices --------------------------------------
    alice_devices = client.get("/api/v1/devices", headers=bearer(alice)).json()["items"]
    assert [d["id"] for d in alice_devices] == [device_id]
    assert client.get("/api/v1/devices", headers=bearer(bob)).json()["items"] == []
    assert client.get(f"/api/v1/devices/{device_id}", headers=bearer(bob)).status_code == 404
    assert client.get(f"/api/v1/devices/{device_id}", headers=bearer(admin_token)).status_code == 200

    renamed = client.patch(
        f"/api/v1/devices/{device_id}", json={"name": "Garden node"}, headers=bearer(alice)
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Garden node"
    assert client.patch(
        f"/api/v1/devices/{device_id}", json={"device_code": "HACKED"}, headers=bearer(alice)
    ).status_code == 403
    assert client.patch(
        f"/api/v1/devices/{device_id}", json={"name": "Bob's now"}, headers=bearer(bob)
    ).status_code == 404

    # ---- a device upload, then a detection --------------------------
    started = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    upload = client.post(
        "/api/v1/recordings",
        data={
            "device_id": device_id,
            "client_upload_id": str(uuid.uuid4()),
            "capture_session_id": str(uuid.uuid4()),
            "snippet_sequence": "0",
            "capture_started_at": started.isoformat(),
            "roi_start_seconds": "12.0",
            "roi_end_seconds": "13.0",
            "edge_processing_version": "test",
            "edge_processing_metadata": "{}",
        },
        files={"audio_file": ("roi.wav", wav_bytes(), "audio/wav")},
    )
    assert upload.status_code == 201, upload.text
    recording = upload.json()["recording"]
    recording_id = recording["id"]
    ctx["files"].append(
        str(settings.audio_storage_directory / recording["stored_filename"])
    )
    portal.call(_add_detection, uuid.UUID(recording_id))

    timeline = client.get(
        f"/api/v1/devices/{device_id}/recordings", headers=bearer(alice)
    ).json()
    assert timeline["pagination"]["total_items"] == 1
    detection = timeline["items"][0]["detections"][0]
    # detected_at = capture start + ROI start (12 s) + BirdNET offset (0.5 s)
    expected = started + timedelta(seconds=12.5)
    assert datetime.fromisoformat(detection["detected_at"]) == expected

    feed = client.get("/api/v1/detections", headers=bearer(alice)).json()
    assert [item["recording_id"] for item in feed["items"]] == [recording_id]
    assert feed["items"][0]["device_code"] == DEVICE_CODE
    assert client.get("/api/v1/detections", headers=bearer(bob)).json()["items"] == []
    assert client.get(
        "/api/v1/detections", params={"species": "magpie"}, headers=bearer(alice)
    ).json()["pagination"]["total_items"] == 1

    audio = client.get(f"/api/v1/recordings/{recording_id}/audio", headers=bearer(alice))
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    assert client.get(f"/api/v1/recordings/{recording_id}/audio", headers=bearer(bob)).status_code == 404
    assert client.get(f"/api/v1/recordings/{recording_id}/audio").status_code == 401

    summary = client.get(f"/api/v1/devices/{device_id}/summary", headers=bearer(alice)).json()
    assert summary["recording_count"] == 1 and summary["detection_count"] == 1
    assert summary["top_species"][0]["common_name"] == "Oriental Magpie-Robin"
    assert sum(day["detection_count"] for day in summary["daily_activity"]) == 1

    dashboard = client.get("/api/v1/dashboard", headers=bearer(alice)).json()
    assert dashboard["device_count"] == 1
    assert dashboard["recording_count"] == 1 and dashboard["detection_count"] == 1
    assert dashboard["recent_detections"][0]["common_name"] == "Oriental Magpie-Robin"
    assert client.get("/api/v1/dashboard", headers=bearer(bob)).json()["recording_count"] == 0

    # ---- ownership changes ------------------------------------------
    released = client.delete(f"/api/v1/devices/{device_id}/owner", headers=bearer(alice))
    assert released.status_code == 200 and released.json()["owner"] is None
    assert client.get(f"/api/v1/devices/{device_id}", headers=bearer(alice)).status_code == 404

    assigned = client.put(
        f"/api/v1/devices/{device_id}/owner",
        json={"owner_email": email("bob")},
        headers=bearer(admin_token),
    )
    assert assigned.status_code == 200 and assigned.json()["owner"]["email"] == email("bob")
    assert client.get(f"/api/v1/recordings/{recording_id}", headers=bearer(bob)).status_code == 200

    new_code = client.post(
        f"/api/v1/devices/{device_id}/claim-code", headers=bearer(admin_token)
    ).json()["claim_code"]
    assert new_code != claim_code

    # ---- the reserved manual-upload device is protected ---------------
    listed = client.get("/api/v1/devices", headers=bearer(admin_token)).json()["items"]
    assert settings.manual_upload_device_code not in [d["device_code"] for d in listed]
    with_system = client.get(
        "/api/v1/devices", params={"include_system": True}, headers=bearer(admin_token)
    ).json()["items"]
    manual = [d for d in with_system if d["device_code"] == settings.manual_upload_device_code]
    if manual:
        manual_id = manual[0]["id"]
        assert client.delete(f"/api/v1/devices/{manual_id}", headers=bearer(admin_token)).status_code == 403
        assert client.post(f"/api/v1/devices/{manual_id}/claim-code", headers=bearer(admin_token)).status_code == 403
        assert client.put(
            f"/api/v1/devices/{manual_id}/owner", json={"owner_email": email("bob")}, headers=bearer(admin_token)
        ).status_code == 403

    # ---- admin user management and password change -------------------
    assert client.get("/api/v1/users", headers=bearer(alice)).status_code == 403
    users = client.get(
        "/api/v1/users", params={"search": SUFFIX}, headers=bearer(admin_token)
    ).json()
    assert users["pagination"]["total_items"] == 3

    assert client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "wrong-password", "new_password": "another-secret"},
        headers=bearer(alice),
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/me/password",
        json={"current_password": PASSWORD, "new_password": "another-secret"},
        headers=bearer(alice),
    ).status_code == 204
    assert client.post(
        "/api/v1/auth/login", json={"email": email("alice"), "password": "another-secret"}
    ).status_code == 200
