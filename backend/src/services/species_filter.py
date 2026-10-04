"""
Location-based species filtering for BirdNET.

BirdNET's acoustic model knows ~6,500 species worldwide. Its geo
model predicts which of them occur at a latitude/longitude in a given
week; passing that list to the acoustic model removes out-of-range
answers (e.g. a European species "heard" in Kandy). It does not
change the scores of the species that remain.

A recording's location is resolved, most specific first:

    recording latitude/longitude  (sent by the device, optional)
    device latitude/longitude     (set on the device page, optional)
    device region                 (district or province, optional)
    BIRDNET_DEFAULT_REGION        (whole of Sri Lanka)

Districts are sampled at an approximate centre point; a province is
the union of its districts and the country the union of all 25, so
nothing that occurs anywhere in the area is left out.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.regions import REGIONS, region_label


logger = logging.getLogger(
    __name__
)


# ============================================================
# Location resolution
# ============================================================


@dataclass(
    frozen=True,
    slots=True,
)
class FilterLocation:
    points: tuple[tuple[float, float], ...]
    label: str


def resolve_location(
    *,
    recording_latitude: Decimal | float | None = None,
    recording_longitude: Decimal | float | None = None,
    device_latitude: Decimal | float | None = None,
    device_longitude: Decimal | float | None = None,
    device_region_code: str | None = None,
) -> FilterLocation:
    """
    The most specific location available (see module docstring).
    """

    for latitude, longitude, source in (
        (recording_latitude, recording_longitude, "recording"),
        (device_latitude, device_longitude, "device"),
    ):
        if latitude is not None and longitude is not None:
            lat = round(float(latitude), 2)
            lon = round(float(longitude), 2)

            return FilterLocation(
                points=((lat, lon),),
                label=f"{lat:.2f}, {lon:.2f} ({source} coordinates)",
            )

    region = REGIONS.get(
        device_region_code or ""
    ) or REGIONS[settings.birdnet_default_region]

    return FilterLocation(
        points=region.points,
        label=region_label(region),
    )


def birdnet_week(
    moment: datetime,
) -> int:
    """
    BirdNET's 48-week year (4 "weeks" per month), in local time.
    """

    local = moment.astimezone(
        ZoneInfo(settings.default_timezone)
    )

    return (
        (local.month - 1) * 4
        + min(3, (local.day - 1) // 7)
        + 1
    )


# ============================================================
# Species lists from the BirdNET geo model
# ============================================================


# BirdNET classes for non-bird sounds. They do not depend on location
# (the geo model never lists them), so the filter always lets them
# through and BirdNET can still label a snippet as e.g. people or an
# engine instead of forcing a bird.
NON_LOCATION_CLASSES = frozenset({
    "Dog_Dog",
    "Engine_Engine",
    "Environmental_Environmental",
    "Fireworks_Fireworks",
    "Gun_Gun",
    "Human non-vocal_Human non-vocal",
    "Human vocal_Human vocal",
    "Human whistle_Human whistle",
    "Noise_Noise",
    "Power tools_Power tools",
    "Siren_Siren",
})


@dataclass(
    frozen=True,
    slots=True,
)
class SpeciesFilter:
    species: frozenset[str]
    description: str


class SpeciesFilterService:
    """
    Builds species lists with BirdNET's geo model. One model and one
    open session are kept per process; lists are cached per
    (sample points, week).
    """

    _geo_model: Any | None = None
    _geo_session: Any | None = None
    _cache: dict[
        tuple[tuple[tuple[float, float], ...], int | None],
        frozenset[str],
    ] = {}
    _lock = threading.Lock()

    def species_filter(
        self,
        location: FilterLocation,
        when: datetime | None,
        acoustic_species: Iterable[str],
    ) -> SpeciesFilter | None:
        """
        The filter for `location` in the week of `when` (all year
        if None or if week filtering is off), or None when location
        filtering is disabled or the list came out empty.
        """

        if not settings.birdnet_location_filter:
            return None

        week = (
            birdnet_week(when)
            if when is not None and settings.birdnet_location_use_week
            else None
        )

        acoustic = frozenset(acoustic_species)
        species = self._species_for(
            location.points,
            week,
        ) & acoustic

        if not species:
            logger.warning(
                "Location filter for %s produced no species; "
                "running BirdNET unfiltered.",
                location.label,
            )
            return None

        season = (
            f"week {week}/48"
            if week is not None
            else "all year"
        )

        return SpeciesFilter(
            species=species | (NON_LOCATION_CLASSES & acoustic),
            description=(
                f"{location.label}, {season}: "
                f"{len(species)} species"
            ),
        )

    def _species_for(
        self,
        points: tuple[tuple[float, float], ...],
        week: int | None,
    ) -> frozenset[str]:
        # At most 48 weeks x (36 regions + coordinate sets); small.
        with self._lock:
            key = (points, week)
            cached = self._cache.get(key)

            if cached is not None:
                return cached

            session = self._get_session()
            species: set[str] = set()

            for latitude, longitude in points:
                result = session.run(
                    latitude,
                    longitude,
                    week=week,
                )
                species.update(
                    result.to_dataframe()["species_name"]
                )

            self._cache[key] = frozenset(species)
            return self._cache[key]

    @classmethod
    def _get_session(
        cls,
    ) -> Any:
        # Called with _lock held.
        if cls._geo_session is not None:
            return cls._geo_session

        import birdnet

        logger.info(
            "Loading BirdNET geo model %s.",
            settings.birdnet_model_version,
        )

        cls._geo_model = birdnet.load(
            "geo",
            settings.birdnet_model_version,
            settings.birdnet_backend,
        )

        # Kept open for the life of the process (an in-process
        # model; no worker processes or pipes).
        session = cls._geo_model.predict_session(
            min_confidence=settings.birdnet_location_min_confidence,
        )
        session.__enter__()
        cls._geo_session = session

        return session


species_filter_service = SpeciesFilterService()


async def location_species_filter(
    location: FilterLocation,
    when: datetime | None,
) -> SpeciesFilter | None:
    """
    The species filter for a recording, or None to run BirdNET
    unfiltered (disabled, or the filter could not be built -- a
    filter problem never fails the recording).
    """

    if not settings.birdnet_location_filter:
        return None

    from src.services.birdnet import BirdNetService

    try:
        return await asyncio.to_thread(
            lambda: species_filter_service.species_filter(
                location,
                when,
                BirdNetService.species_labels(),
            )
        )

    except Exception:
        logger.exception(
            "Could not build the BirdNET location filter for %s; "
            "running unfiltered.",
            location.label,
        )
        return None
