import { useEffect, useState } from "react";

import { getRegions } from "../api/devicesApi";


/**
 * Province / district picker for a device's region_code. "" means
 * no region (BirdNET then uses all of Sri Lanka).
 */
export default function RegionSelect({ id, value, onChange, disabled }) {
  const [regions, setRegions] = useState([]);
  const [failed, setFailed] = useState(false);


  useEffect(() => {
    let active = true;

    getRegions()
      .then((data) => active && setRegions(data))
      .catch(() => active && setFailed(true));

    return () => {
      active = false;
    };
  }, []);


  const provinces = regions.filter((region) => region.kind === "province");

  return (
    <select id={id} className="select" value={value ?? ""} disabled={disabled || failed}
      onChange={(event) => onChange(event.target.value)}>
      <option value="">{failed ? "Regions unavailable" : "Not set (all of Sri Lanka)"}</option>
      {provinces.map((province) => (
        <optgroup key={province.code} label={province.label}>
          <option value={province.code}>{province.label} (whole province)</option>
          {regions
            .filter((region) => region.province_code === province.code)
            .map((district) => (
              <option key={district.code} value={district.code}>{district.label}</option>
            ))}
        </optgroup>
      ))}
    </select>
  );
}
