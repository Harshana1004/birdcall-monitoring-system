"""
Sri Lankan provinces and districts (ISO 3166-2:LK codes) with sample
points for BirdNET's geo model (src/services/species_filter.py).

Kept free of other backend imports so settings validation can use it.
"""

from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# Regions (ISO 3166-2:LK codes)
# ============================================================


@dataclass(
    frozen=True,
    slots=True,
)
class Region:
    code: str
    name: str
    kind: str  # "country" | "province" | "district"
    province_code: str | None
    # (latitude, longitude) sample points.
    points: tuple[tuple[float, float], ...]


PROVINCES: dict[str, str] = {
    "LK-1": "Western",
    "LK-2": "Central",
    "LK-3": "Southern",
    "LK-4": "Northern",
    "LK-5": "Eastern",
    "LK-6": "North Western",
    "LK-7": "North Central",
    "LK-8": "Uva",
    "LK-9": "Sabaragamuwa",
}

# code: (name, approximate centre latitude, longitude). The province
# is the first digit of the code.
DISTRICTS: dict[str, tuple[str, float, float]] = {
    "LK-11": ("Colombo", 6.88, 80.00),
    "LK-12": ("Gampaha", 7.08, 80.03),
    "LK-13": ("Kalutara", 6.58, 80.15),
    "LK-21": ("Kandy", 7.30, 80.70),
    "LK-22": ("Matale", 7.65, 80.68),
    "LK-23": ("Nuwara Eliya", 6.97, 80.70),
    "LK-31": ("Galle", 6.22, 80.25),
    "LK-32": ("Matara", 6.10, 80.53),
    "LK-33": ("Hambantota", 6.27, 81.10),
    "LK-41": ("Jaffna", 9.66, 80.10),
    "LK-42": ("Kilinochchi", 9.38, 80.40),
    "LK-43": ("Mannar", 8.85, 80.05),
    "LK-44": ("Vavuniya", 8.83, 80.48),
    "LK-45": ("Mullaitivu", 9.17, 80.73),
    "LK-51": ("Batticaloa", 7.73, 81.55),
    "LK-52": ("Ampara", 7.20, 81.62),
    "LK-53": ("Trincomalee", 8.55, 81.08),
    "LK-61": ("Kurunegala", 7.65, 80.30),
    "LK-62": ("Puttalam", 8.03, 79.92),
    "LK-71": ("Anuradhapura", 8.30, 80.45),
    "LK-72": ("Polonnaruwa", 7.93, 81.03),
    "LK-81": ("Badulla", 7.00, 81.08),
    "LK-82": ("Monaragala", 6.78, 81.30),
    "LK-91": ("Ratnapura", 6.62, 80.55),
    "LK-92": ("Kegalle", 7.20, 80.33),
}


def _build_regions() -> dict[str, Region]:
    regions: dict[str, Region] = {}

    for code, (name, latitude, longitude) in DISTRICTS.items():
        regions[code] = Region(
            code=code,
            name=name,
            kind="district",
            province_code=code[:4],
            points=((latitude, longitude),),
        )

    for code, name in PROVINCES.items():
        regions[code] = Region(
            code=code,
            name=name,
            kind="province",
            province_code=None,
            points=tuple(
                point
                for district in regions.values()
                if district.province_code == code
                for point in district.points
            ),
        )

    regions["LK"] = Region(
        code="LK",
        name="Sri Lanka",
        kind="country",
        province_code=None,
        points=tuple(
            regions[code].points[0]
            for code in DISTRICTS
        ),
    )

    return regions


REGIONS: dict[str, Region] = _build_regions()


def region_label(
    region: Region,
) -> str:
    if region.kind == "district":
        return f"{region.name} District"

    if region.kind == "province":
        return f"{region.name} Province"

    return region.name


def normalize_region_code(
    value: str | None,
) -> str | None:
    """
    Upper-cased region code, or None for blank. Raises ValueError
    for unknown codes.
    """

    if value is None or not value.strip():
        return None

    code = value.strip().upper()

    if code not in REGIONS:
        raise ValueError(
            f"Unknown region '{value}'. Use an ISO 3166-2:LK "
            "province (LK-1 ... LK-9) or district (LK-11 ... LK-92) "
            "code, or LK for the whole country."
        )

    return code
