"""
BirdNET location filter: regions, location resolution, BirdNET weeks,
the device region API, and that recording processing passes the
resolved species list to BirdNET and records it.

Runs against the database in backend/.env (migrated to head);
everything created is deleted at the end. Neither BirdNET model is
loaded: the geo-model lookup and BirdNET itself are replaced by stubs.

    cd backend
    python -m pytest tests/test_species_filter.py -v
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
import src.services.recordings as recordings_service
from src.core.config import settings
from src.core.regions import DISTRICTS, PROVINCES, REGIONS, normalize_region_code
from src.database import AsyncSessionLocal
from src.models import Device, Recording, User
from src.server import app
from src.services.birdnet import BirdNetPrediction
from src.services.species_filter import (
    NON_LOCATION_CLASSES,
    SpeciesFilter,
    SpeciesFilterService,
    birdnet_week,
    resolve_location,
)


SUFFIX = uuid.uuid4().hex[:8]
DEVICE_CODE = f"TEST-SF-{SUFFIX.upper()}"


# ============================================================
# Pure functions
# ============================================================


def test_region_table():
    assert len(PROVINCES) == 9 and len(DISTRICTS) == 25
    assert len(REGIONS) == 1 + 9 + 25

    for code in PROVINCES:
        districts = [r for r in REGIONS.values() if r.province_code == code]
        assert districts, code
        assert len(REGIONS[code].points) == len(districts)

    assert len(REGIONS["LK"].points) == 25

    for region in REGIONS.values():
        for latitude, longitude in region.points:
            # Inside Sri Lanka's bounding box.
            assert 5.9 <= latitude <= 9.9 and 79.6 <= longitude <= 81.9


def test_normalize_region_code():
    assert normalize_region_code(" lk-21 ") == "LK-21"
    assert normalize_region_code("") is None
    assert normalize_region_code(None) is None
    with pytest.raises(ValueError):
        normalize_region_code("LK-99")


def test_resolve_location_priority():
    kandy = dict(device_region_code="LK-21")

    assert resolve_location(**kandy).label == "Kandy District"
    assert resolve_location(device_region_code="LK-8").label == "Uva Province"
    assert resolve_location().label == "Sri Lanka"
    assert len(resolve_location().points) == 25

    device_point = resolve_location(device_latitude=7.2906, device_longitude=80.6337, **kandy)
    assert device_point.points == ((7.29, 80.63),)
    assert "device coordinates" in device_point.label

    recording_point = resolve_location(
        recording_latitude=6.4, recording_longitude=80.45,
        device_latitude=7.29, device_longitude=80.63, **kandy,
    )
    assert recording_point.points == ((6.4, 80.45),)
    assert "recording coordinates" in recording_point.label

    # Half a coordinate pair is ignored.
    assert resolve_location(device_latitude=7.29, **kandy).label == "Kandy District"


def test_birdnet_week():
    utc = timezone.utc
    assert birdnet_week(datetime(2026, 1, 1, 12, tzinfo=utc)) == 1
    assert birdnet_week(datetime(2026, 1, 8, 12, tzinfo=utc)) == 2
    assert birdnet_week(datetime(2026, 1, 31, 12, tzinfo=utc)) == 4
    assert birdnet_week(datetime(2026, 10, 5, 12, tzinfo=utc)) == 37
    assert birdnet_week(datetime(2026, 12, 31, 12, tzinfo=utc)) == 48
    # 20:00 UTC on 31 Dec is already 1 Jan in Sri Lanka (UTC+5:30).
    assert birdnet_week(datetime(2026, 12, 31, 20, tzinfo=utc)) == 1


def test_filter_keeps_non_bird_classes(monkeypatch):
    service = SpeciesFilterService()
    monkeypatch.setattr(
        service, "_species_for",
        lambda points, week: frozenset({"Gallus lafayettii_Sri Lanka Junglefowl", "Not_InModel"}),
    )
    acoustic = {"Gallus lafayettii_Sri Lanka Junglefowl", "Turdus merula_Eurasian Blackbird", *NON_LOCATION_CLASSES}

    result = service.species_filter(
        resolve_location(device_region_code="LK-21"),
        datetime(2026, 10, 5, 6, tzinfo=timezone.utc),
        acoustic,
    )

    assert result.species == {"Gallus lafayettii_Sri Lanka Junglefowl", *NON_LOCATION_CLASSES}
    # The count is location species only.
    assert result.description == "Kandy District, week 37/48: 1 species"


# ============================================================
# API and processing
# ============================================================


async def _noop_processing(recording_id):
    return None


@pytest.fixture(scope="module")
def ctx():
    monkey = pytest.MonkeyPatch()
    monkey.setattr(recordings_api, "process_recording_background", _noop_processing)
    monkey.setattr(settings, "device_api_key", None)
    with TestClient(app) as client:
        state = {"client": client, "portal": client.portal}
        try:
            yield state
        finally:
            state["portal"].call(_cleanup)
    monkey.undo()


async def _cleanup() -> None:
    async with AsyncSessionLocal() as session:
        files = (
            await session.scalars(
                select(Recording.file_path)
                .join(Device, Recording.device_id == Device.id)
                .where(Device.device_code == DEVICE_CODE)
            )
        ).all()
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


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wav_bytes() -> bytes:
    t = np.arange(16000) / 16000
    buffer = io.BytesIO()
    sf.write(buffer, 0.3 * np.sin(2 * np.pi * 3000 * t), 16000, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def test_regions_endpoint(ctx):
    regions = ctx["client"].get("/api/v1/regions").json()
    assert len(regions) == 35
    assert regions[0]["code"] == "LK"
    # Each province is followed by its districts.
    assert regions[1]["code"] == "LK-1" and regions[1]["label"] == "Western Province"
    assert {r["code"] for r in regions[2:5]} == {"LK-11", "LK-12", "LK-13"}


def test_device_region_and_processing(ctx):
    client, portal = ctx["client"], ctx["portal"]

    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"admin-{SUFFIX}@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    portal.call(_make_admin, f"admin-{SUFFIX}@example.com")

    bad = client.post(
        "/api/v1/devices",
        json={"device_code": DEVICE_CODE, "name": "x", "region_code": "LK-99"},
        headers=bearer(token),
    )
    assert bad.status_code == 422

    created = client.post(
        "/api/v1/devices",
        json={"device_code": DEVICE_CODE, "name": "Kandy node", "region_code": "lk-21"},
        headers=bearer(token),
    )
    assert created.status_code == 201, created.text
    device = created.json()["device"]
    assert device["region_code"] == "LK-21"
    assert device["region_name"] == "Kandy District"

    to_province = client.patch(
        f"/api/v1/devices/{device['id']}", json={"region_code": "LK-2"}, headers=bearer(token)
    )
    assert to_province.json()["region_name"] == "Central Province"

    cleared = client.patch(
        f"/api/v1/devices/{device['id']}", json={"region_code": None}, headers=bearer(token)
    )
    assert cleared.json()["region_code"] is None and cleared.json()["region_name"] is None

    client.patch(f"/api/v1/devices/{device['id']}", json={"region_code": "LK-21"}, headers=bearer(token))

    started = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    upload = client.post(
        "/api/v1/recordings",
        data={
            "device_id": device["id"],
            "client_upload_id": str(uuid.uuid4()),
            "capture_session_id": str(uuid.uuid4()),
            "snippet_sequence": "0",
            "capture_started_at": started.isoformat(),
            "roi_start_seconds": "1.0",
            "roi_end_seconds": "2.0",
            "edge_processing_version": "test",
            "edge_processing_metadata": "{}",
        },
        files={"audio_file": ("roi.wav", wav_bytes(), "audio/wav")},
    )
    assert upload.status_code == 201, upload.text
    recording_id = uuid.UUID(upload.json()["recording"]["id"])

    # Run the real processing with the geo model and BirdNET stubbed.
    seen = {}

    async def fake_filter(location, when):
        seen["location"], seen["when"] = location, when
        return SpeciesFilter(
            species=frozenset({"Gallus lafayettii_Sri Lanka Junglefowl"}),
            description=f"{location.label}, week 37/48: 1 species",
        )

    class FakeBirdNet:
        async def analyze(self, audio_path, species_list=None):
            seen["species_list"] = species_list
            return [BirdNetPrediction("Gallus lafayettii", "Sri Lanka Junglefowl", 0.9, 0.0, 1.0)]

    async def process():
        async with AsyncSessionLocal() as session:
            await recordings_service.RecordingService(session, FakeBirdNet()).process_recording(recording_id)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(recordings_service, "location_species_filter", fake_filter)
    try:
        portal.call(process)
    finally:
        monkey.undo()

    assert seen["location"].label == "Kandy District"
    assert seen["species_list"] == frozenset({"Gallus lafayettii_Sri Lanka Junglefowl"})
    assert abs((seen["when"] - (started + timedelta(seconds=1))).total_seconds()) < 1

    item = client.get(f"/api/v1/devices/{device['id']}/recordings", headers=bearer(token)).json()["items"][0]
    assert item["processing_status"] == "completed"
    assert item["species_filter"] == "Kandy District, week 37/48: 1 species"
    assert item["detections"][0]["common_name"] == "Sri Lanka Junglefowl"
