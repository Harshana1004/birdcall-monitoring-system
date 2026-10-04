from fastapi import APIRouter
from pydantic import BaseModel

from src.core.regions import REGIONS, region_label


router = APIRouter(
    prefix="/api/v1/regions",
    tags=["Regions"],
)


class RegionResponse(BaseModel):
    code: str
    name: str
    label: str
    kind: str
    province_code: str | None


@router.get(
    "",
    response_model=list[RegionResponse],
)
async def list_regions() -> list[RegionResponse]:
    """
    Sri Lanka, its provinces and its districts (ISO 3166-2:LK codes),
    for a device's region_code. Each province is followed by its
    districts.
    """

    ordered = [REGIONS["LK"]]

    for province in (r for r in REGIONS.values() if r.kind == "province"):
        ordered.append(province)
        ordered.extend(
            sorted(
                (
                    r
                    for r in REGIONS.values()
                    if r.province_code == province.code
                ),
                key=lambda r: r.name,
            )
        )

    return [
        RegionResponse(
            code=r.code,
            name=r.name,
            label=region_label(r),
            kind=r.kind,
            province_code=r.province_code,
        )
        for r in ordered
    ]
