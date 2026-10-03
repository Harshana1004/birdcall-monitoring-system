import {
  useEffect,
  useState,
} from "react";

import { useSearchParams } from "react-router-dom";

import { listDetections } from "../api/activityApi";
import { listDevices } from "../api/devicesApi";
import DetectionTable from "../components/DetectionTable";
import {
  Alert,
  LoadingState,
  PageHeader,
  Pagination,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { localInputToIso } from "../utils/format";


const PAGE_SIZE = 25;


function DetectionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Filters live in the URL so a filtered view can be bookmarked.
  const filters = {
    device: searchParams.get("device") ?? "",
    species: searchParams.get("species") ?? "",
    from: searchParams.get("from") ?? "",
    to: searchParams.get("to") ?? "",
    confidence: searchParams.get("confidence") ?? "",
    manual: searchParams.get("manual") === "1",
    page: Number(searchParams.get("page") ?? 1),
  };

  // Typing in the species box only queries after a short pause.
  const [speciesInput, setSpeciesInput] = useState(filters.species);

  useEffect(() => {
    setSpeciesInput(filters.species);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get("species")]);

  useEffect(() => {
    if (speciesInput === filters.species) {
      return undefined;
    }

    const timer = setTimeout(() => setFilter("species", speciesInput), 400);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [speciesInput]);


  function setFilter(field, value) {
    const next = new URLSearchParams(searchParams);

    if (value === "" || value === false || value === null) {
      next.delete(field);
    } else {
      next.set(field, value === true ? "1" : String(value));
    }

    if (field !== "page") {
      next.delete("page");
    }

    setSearchParams(next, { replace: field !== "page" });
  }


  const devices = useApi(() => listDevices(), []);

  const { data, error, isLoading } = useApi(
    () =>
      listDetections({
        page: filters.page,
        page_size: PAGE_SIZE,
        device_id: filters.device || undefined,
        species: filters.species || undefined,
        date_from: localInputToIso(filters.from),
        date_to: localInputToIso(filters.to),
        minimum_confidence: filters.confidence || undefined,
        include_manual: filters.manual,
      }),
    [searchParams.toString()]
  );

  const hasFilters = Boolean(
    filters.device || filters.species || filters.from || filters.to || filters.confidence || filters.manual
  );


  return (
    <main className="page">
      <PageHeader
        eyebrow="History"
        title="Detections"
        description="Every species identification from your devices, newest first. Use the filters to look back over any period."
      />

      <section className="card">
        <div className="filters">
          <div className="field">
            <label htmlFor="f-device">Device</label>
            <select id="f-device" className="select" value={filters.device}
              onChange={(event) => setFilter("device", event.target.value)}>
              <option value="">All devices</option>
              {(devices.data?.items ?? []).map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name} ({device.device_code})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-species">Species</label>
            <input id="f-species" className="input" placeholder="e.g. magpie or Copsychus"
              value={speciesInput} onChange={(event) => setSpeciesInput(event.target.value)} />
          </div>

          <div className="field">
            <label htmlFor="f-from">From</label>
            <input id="f-from" className="input" type="datetime-local"
              value={filters.from} onChange={(event) => setFilter("from", event.target.value)} />
          </div>

          <div className="field">
            <label htmlFor="f-to">To</label>
            <input id="f-to" className="input" type="datetime-local"
              value={filters.to} onChange={(event) => setFilter("to", event.target.value)} />
          </div>

          <div className="field">
            <label htmlFor="f-confidence">Min. confidence</label>
            <select id="f-confidence" className="select" value={filters.confidence}
              onChange={(event) => setFilter("confidence", event.target.value)}>
              <option value="">Any</option>
              <option value="0.5">50%+</option>
              <option value="0.7">70%+</option>
              <option value="0.9">90%+</option>
            </select>
          </div>
        </div>

        <div className="row" style={{ marginBottom: 16 }}>
          <label className="checkbox">
            <input type="checkbox" checked={filters.manual}
              onChange={(event) => setFilter("manual", event.target.checked)} />
            Include my manual analyses
          </label>
          <span className="spacer" />
          {data && (
            <span className="small muted">
              {data.pagination.total_items} detection{data.pagination.total_items === 1 ? "" : "s"}
            </span>
          )}
          {hasFilters && (
            <button type="button" className="button button-ghost button-small"
              onClick={() => setSearchParams({}, { replace: true })}>
              Clear filters
            </button>
          )}
        </div>

        <Alert>{error}</Alert>

        {isLoading && !data && <LoadingState label="Loading detections…" />}

        {data && data.items.length === 0 && (
          <div className="empty-detection">
            {hasFilters
              ? "No detections match these filters."
              : "No detections yet. They appear here as soon as your devices upload bird calls."}
          </div>
        )}

        {data && data.items.length > 0 && (
          <div style={{ opacity: isLoading ? 0.6 : 1 }}>
            <DetectionTable detections={data.items} />
          </div>
        )}

        <Pagination
          pagination={data?.pagination}
          onPageChange={(page) => setFilter("page", page)}
        />
      </section>
    </main>
  );
}


export default DetectionsPage;
