import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Link,
  useNavigate,
  useParams,
} from "react-router-dom";

import { errorMessage } from "../api/client";
import {
  getDevice,
  getDeviceRecordings,
  getDeviceSummary,
  releaseDevice,
  updateDevice,
} from "../api/devicesApi";
import { useAuth } from "../auth/AuthContext";
import { ActivityChart, SpeciesBars } from "../components/charts";
import RecordingAudio from "../components/RecordingAudio";
import RegionSelect from "../components/RegionSelect";
import {
  Alert,
  ConfidenceBadge,
  EmptyState,
  LiveIndicator,
  LoadingState,
  PageHeader,
  Pagination,
  StatCard,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useNewIds, usePolling } from "../hooks/usePolling";
import {
  activityState,
  formatDate,
  formatDateTime,
  formatNumber,
  formatRelative,
  formatSeconds,
  formatTime,
  localInputToIso,
} from "../utils/format";


const PAGE_SIZE = 15;
// The timeline refreshes itself so new uploads appear without a
// reload; faster while BirdNET is still working on a listed snippet.
const REFRESH_SECONDS = 10;
const PROCESSING_REFRESH_SECONDS = 5;
const TOTALS_REFRESH_SECONDS = 30;
const PROCESSING_STATES = new Set(["pending", "processing"]);

const STATUS_BADGES = {
  completed: null,
  pending: <span className="badge">Waiting for BirdNET</span>,
  processing: <span className="badge badge-lime">Classifying…</span>,
  failed: <span className="badge badge-danger">Classification failed</span>,
};


// ------------------------------------------------------------
// Edit details
// ------------------------------------------------------------

function EditDeviceForm({ device, onSaved, onCancel }) {
  const [form, setForm] = useState({
    name: device.name,
    description: device.description ?? "",
    regionCode: device.region_code ?? "",
    latitude: device.latitude ?? "",
    longitude: device.longitude ?? "",
  });
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);


  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }


  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);

    try {
      onSaved(
        await updateDevice(device.id, {
          name: form.name.trim(),
          description: form.description.trim() || null,
          region_code: form.regionCode || null,
          latitude: form.latitude === "" ? null : Number(form.latitude),
          longitude: form.longitude === "" ? null : Number(form.longitude),
        })
      );
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not save the device."));
      setIsSaving(false);
    }
  }


  return (
    <section className="card" style={{ marginBottom: 16 }}>
      <div className="card-header">
        <h2>Edit device</h2>
      </div>

      <form className="form" onSubmit={handleSubmit}>
        <Alert>{error}</Alert>

        <div className="field">
          <label htmlFor="device-name">Name</label>
          <input id="device-name" className="input" required maxLength={120}
            value={form.name} onChange={update("name")} />
        </div>

        <div className="field">
          <label htmlFor="device-description">Description</label>
          <textarea id="device-description" className="textarea" maxLength={2000}
            placeholder="Where is it installed? What is it listening for?"
            value={form.description} onChange={update("description")} />
        </div>

        <div className="field">
          <label htmlFor="device-region">Province or district</label>
          <RegionSelect id="device-region" value={form.regionCode}
            onChange={(regionCode) => setForm((current) => ({ ...current, regionCode }))} />
          <span className="small faint">
            BirdNET only considers species expected here in the week of each recording.
            Exact coordinates below, if set, take priority.
          </span>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="device-lat">Latitude (optional)</label>
            <input id="device-lat" className="input" type="number" step="any" min={-90} max={90}
              placeholder="6.4033" value={form.latitude} onChange={update("latitude")} />
          </div>
          <div className="field">
            <label htmlFor="device-lon">Longitude (optional)</label>
            <input id="device-lon" className="input" type="number" step="any" min={-180} max={180}
              placeholder="80.4561" value={form.longitude} onChange={update("longitude")} />
          </div>
        </div>

        <div className="row">
          <button type="submit" className="button button-primary" disabled={isSaving}>
            {isSaving ? "Saving…" : "Save changes"}
          </button>
          <button type="button" className="button button-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}


// ------------------------------------------------------------
// Recording timeline
// ------------------------------------------------------------

function TimelineItem({ recording, isNew }) {
  return (
    <article className={isNew ? "timeline-item is-new" : "timeline-item"}>
      <div className="timeline-time">
        <strong>{formatTime(recording.recorded_at)}</strong>
        <span>{formatDate(recording.recorded_at)}</span>
        <div className="small faint" style={{ marginTop: 4 }}>
          {formatSeconds(recording.duration_seconds)} snippet
        </div>
      </div>

      <div className="timeline-body">
        <div className="row">
          {recording.detections.length > 0 ? (
            <span className="badge badge-green">
              {recording.detections.length} detection{recording.detections.length === 1 ? "" : "s"}
            </span>
          ) : (
            recording.processing_status === "completed" && (
              <span className="badge">No species above threshold</span>
            )
          )}
          {STATUS_BADGES[recording.processing_status]}
          {isNew && <span className="badge badge-lime">New</span>}
          <span className="spacer" />
          <RecordingAudio recordingId={recording.id} compact />
        </div>

        {recording.detections.length > 0 && (
          <div className="detection-chips">
            {recording.detections.map((detection) => (
              <div className="detection-chip" key={detection.id}>
                <div style={{ minWidth: 0 }}>
                  <div className="species-name">{detection.common_name}</div>
                  <div className="species-sci">
                    {detection.scientific_name} · {formatTime(detection.detected_at)}
                  </div>
                </div>
                <ConfidenceBadge confidence={detection.confidence} />
              </div>
            ))}
          </div>
        )}

        {recording.species_filter && (
          <div className="small faint" title="BirdNET location filter used for these results">
            Species filter: {recording.species_filter}
          </div>
        )}

        {recording.processing_status === "failed" && recording.processing_error && (
          <div className="small" style={{ color: "var(--danger)" }}>
            {recording.processing_error}
          </div>
        )}
      </div>
    </article>
  );
}


function RecordingTimeline({ deviceId, species, onNewData }) {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    dateFrom: "",
    dateTo: "",
    species: "",
    minimumConfidence: "",
    onlyWithDetections: true,
  });


  const { data, error, isLoading, reload } = useApi(
    () =>
      getDeviceRecordings(deviceId, {
        page,
        page_size: PAGE_SIZE,
        date_from: localInputToIso(filters.dateFrom),
        date_to: localInputToIso(filters.dateTo),
        species: filters.species || undefined,
        minimum_confidence: filters.minimumConfidence || undefined,
        only_with_detections: filters.onlyWithDetections,
      }),
    [deviceId, page, filters]
  );


  const isProcessing = Boolean(
    data?.items.some((item) => PROCESSING_STATES.has(item.processing_status))
  );

  usePolling(
    () => reload({ silent: true }),
    (isProcessing ? PROCESSING_REFRESH_SECONDS : REFRESH_SECONDS) * 1000
  );

  const newIds = useNewIds(data?.items, `${page}|${JSON.stringify(filters)}`);

  // When something new arrives or BirdNET finishes a snippet, let the
  // page refresh its totals and charts too.
  const signature = data
    ? `${data.pagination.total_items}|${data.items[0]?.id ?? ""}|${isProcessing}`
    : null;
  const lastSignature = useRef(null);

  useEffect(() => {
    if (signature === null) {
      return;
    }

    if (lastSignature.current !== null && lastSignature.current !== signature) {
      onNewData?.();
    }
    lastSignature.current = signature;
  }, [signature, onNewData]);


  function setFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
    setPage(1);
  }


  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="card-header">
        <div>
          <h2>Recording timeline</h2>
          <p>Every ROI snippet this device uploaded, newest first, with BirdNET's results.</p>
        </div>
        <LiveIndicator seconds={isProcessing ? PROCESSING_REFRESH_SECONDS : REFRESH_SECONDS} />
      </div>

      <div className="filters">
        <div className="field">
          <label htmlFor="tl-from">From</label>
          <input id="tl-from" className="input" type="datetime-local"
            value={filters.dateFrom} onChange={(event) => setFilter("dateFrom", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="tl-to">To</label>
          <input id="tl-to" className="input" type="datetime-local"
            value={filters.dateTo} onChange={(event) => setFilter("dateTo", event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="tl-species">Species</label>
          <select id="tl-species" className="select" value={filters.species}
            onChange={(event) => setFilter("species", event.target.value)}>
            <option value="">All species</option>
            {species.map((item) => (
              <option key={item.scientific_name} value={item.scientific_name}>
                {item.common_name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="tl-confidence">Min. confidence</label>
          <select id="tl-confidence" className="select" value={filters.minimumConfidence}
            onChange={(event) => setFilter("minimumConfidence", event.target.value)}>
            <option value="">Any</option>
            <option value="0.5">50%+</option>
            <option value="0.7">70%+</option>
            <option value="0.9">90%+</option>
          </select>
        </div>
        <label className="checkbox" style={{ paddingBottom: 10 }}>
          <input type="checkbox" checked={filters.onlyWithDetections}
            onChange={(event) => setFilter("onlyWithDetections", event.target.checked)} />
          Only snippets with detections
        </label>
      </div>

      <Alert>{error}</Alert>

      {isLoading && !data && <LoadingState label="Loading recordings…" />}

      {data && data.items.length === 0 && (
        <div className="empty-detection">
          {filters.onlyWithDetections
            ? "No snippets with detections match these filters. Untick “Only snippets with detections” to see every upload."
            : "No snippets match these filters."}
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="timeline" style={{ opacity: isLoading ? 0.6 : 1 }}>
          {data.items.map((recording) => (
            <TimelineItem key={recording.id} recording={recording} isNew={newIds.has(recording.id)} />
          ))}
        </div>
      )}

      <Pagination pagination={data?.pagination} onPageChange={setPage} />
    </section>
  );
}


// ------------------------------------------------------------
// Page
// ------------------------------------------------------------

function DeviceDetailPage() {
  const { deviceId } = useParams();
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();

  const [isEditing, setIsEditing] = useState(false);
  const [confirmRelease, setConfirmRelease] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [isSharing, setIsSharing] = useState(false);

  const device = useApi(() => getDevice(deviceId), [deviceId]);
  const summary = useApi(() => getDeviceSummary(deviceId, 30), [deviceId]);

  const reloadDevice = device.reload;
  const reloadSummary = summary.reload;
  const refreshTotals = useCallback(() => {
    reloadDevice({ silent: true });
    reloadSummary({ silent: true });
  }, [reloadDevice, reloadSummary]);

  // Keeps "last upload" and the charts current even when the
  // timeline's filters hide new snippets.
  usePolling(refreshTotals, TOTALS_REFRESH_SECONDS * 1000);


  async function handleToggleShared() {
    setActionError(null);
    setIsSharing(true);

    try {
      device.setData(await updateDevice(deviceId, { is_shared: !device.data.is_shared }));
    } catch (requestError) {
      setActionError(errorMessage(requestError, "Could not change sharing."));
    } finally {
      setIsSharing(false);
    }
  }


  async function handleRelease() {
    setActionError(null);

    try {
      await releaseDevice(deviceId);
      navigate("/devices");
    } catch (requestError) {
      setActionError(errorMessage(requestError, "Could not remove the device."));
    }
  }


  if (device.isLoading && !device.data) {
    return (
      <main className="page">
        <LoadingState label="Loading device…" />
      </main>
    );
  }

  if (device.error) {
    return (
      <main className="page">
        <Alert>{device.error}</Alert>
        <Link to="/devices" className="button button-secondary">← Back to devices</Link>
      </main>
    );
  }

  const info = device.data;
  const stats = summary.data;
  const state = activityState(info.last_recording_at);
  const isOwner = info.owner?.id === user?.id;
  const canManage = isOwner || isAdmin;


  return (
    <main className="page">
      <Link to="/devices" className="small">All devices</Link>

      <PageHeader
        eyebrow={<span className="mono">{info.device_code}</span>}
        title={info.name}
        description={info.description || undefined}
        actions={
          canManage && (
          <>
            {isAdmin && (
              <button type="button" className="button button-secondary" disabled={isSharing}
                onClick={handleToggleShared}
                title={info.is_shared
                  ? "Only the owner and admins will see this device"
                  : "Every signed-in account will see this device (read-only)"}>
                {info.is_shared ? "Stop sharing" : "Share with everyone"}
              </button>
            )}
            <button type="button" className="button button-secondary" onClick={() => setIsEditing(true)}>
              Edit
            </button>
            {info.owner && (
              <button type="button" className="button button-danger" onClick={() => setConfirmRelease(true)}>
                Remove from account
              </button>
            )}
          </>
          )
        }
      />

      <div className="row small muted" style={{ marginTop: -16, marginBottom: 20 }}>
        <span className={`status-dot ${state}`} />
        <span>
          {info.last_recording_at
            ? `Last upload ${formatRelative(info.last_recording_at)} (${formatDateTime(info.last_recording_at)})`
            : "No uploads yet"}
        </span>
        {!info.is_active && <span className="badge badge-warning">Inactive</span>}
        {info.is_shared && (
          <span className="badge badge-green"
            title="Every signed-in account can view this device">
            {canManage ? "Shared with everyone" : "Shared with you · view only"}
          </span>
        )}
        {info.latitude != null && info.longitude != null ? (
          <span className="faint">
            · {Number(info.latitude).toFixed(4)}, {Number(info.longitude).toFixed(4)}
          </span>
        ) : (
          <span className="faint">· {info.region_name ?? "Location not set (all of Sri Lanka)"}</span>
        )}
        {isAdmin && (
          <span className="faint">· Owner: {info.owner ? info.owner.email : "unclaimed"}</span>
        )}
      </div>

      <Alert>{actionError}</Alert>

      {confirmRelease && (
        <div className="alert alert-warning" style={{ marginBottom: 16 }}>
          <div className="row">
            <span>
              Remove <strong>{info.name}</strong> from {isOwner ? "your" : "its owner's"} account?
              Its recordings are kept; it can be added again with its claim code.
            </span>
            <span className="spacer" />
            <button type="button" className="button button-danger button-small" onClick={handleRelease}>
              Remove
            </button>
            <button type="button" className="button button-ghost button-small" onClick={() => setConfirmRelease(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {isEditing && (
        <EditDeviceForm
          device={info}
          onSaved={(updated) => {
            device.setData(updated);
            setIsEditing(false);
          }}
          onCancel={() => setIsEditing(false)}
        />
      )}

      <div className="stats-grid">
        <StatCard label="Detections" value={formatNumber(stats?.detection_count ?? info.detection_count)} accent />
        <StatCard label="ROI snippets" value={formatNumber(stats?.recording_count ?? info.recording_count)} />
        <StatCard label="Species" value={formatNumber(stats?.species_count ?? 0)} />
        <StatCard
          label="Recording since"
          value={stats?.first_recording_at ? formatDate(stats.first_recording_at) : "—"}
        />
      </div>

      {stats && stats.recording_count === 0 ? (
        <EmptyState title="Waiting for the first upload">
          Once this device detects sound and uploads a snippet over 4G, its
          recordings and BirdNET results appear here.
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-2">
            <section className="card">
              <div className="card-header">
                <div>
                  <h2>Daily activity</h2>
                  <p>Last 30 days.</p>
                </div>
              </div>
              {stats ? <ActivityChart days={stats.daily_activity} /> : <LoadingState />}
            </section>

            <section className="card">
              <div className="card-header">
                <div>
                  <h2>Species heard</h2>
                  <p>Most frequently detected by this device.</p>
                </div>
              </div>
              {stats && stats.top_species.length === 0 && (
                <div className="empty-detection">No species detected yet.</div>
              )}
              {stats && stats.top_species.length > 0 && <SpeciesBars species={stats.top_species} />}
            </section>
          </div>

          <RecordingTimeline
            deviceId={deviceId}
            species={stats?.top_species ?? []}
            onNewData={refreshTotals}
          />
        </>
      )}
    </main>
  );
}


export default DeviceDetailPage;
