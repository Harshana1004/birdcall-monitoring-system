import { useState } from "react";

import { Link, useSearchParams } from "react-router-dom";

import { errorMessage } from "../api/client";
import { claimDevice, listDevices } from "../api/devicesApi";
import { useAuth } from "../auth/AuthContext";
import {
  Alert,
  EmptyState,
  LoadingState,
  PageHeader,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { usePolling } from "../hooks/usePolling";
import { activityState, formatNumber, formatRelative } from "../utils/format";


function ClaimDeviceForm({ onClaimed, onCancel }) {
  const [deviceCode, setDeviceCode] = useState("");
  const [claimCode, setClaimCode] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      onClaimed(await claimDevice({ deviceCode: deviceCode.trim(), claimCode: claimCode.trim() }));
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not add the device."));
      setIsSubmitting(false);
    }
  }


  return (
    <section className="card" style={{ marginBottom: 20 }}>
      <div className="card-header">
        <div>
          <h2>Add a device</h2>
          <p>
            Enter the device code and claim code supplied with your device
            (for example on its label).
          </p>
        </div>
      </div>

      <form className="form" onSubmit={handleSubmit}>
        <Alert>{error}</Alert>

        <div className="form-row">
          <div className="field">
            <label htmlFor="device-code">Device code</label>
            <input
              id="device-code"
              className="input mono"
              placeholder="ESP32-DEV-01"
              required
              autoFocus
              value={deviceCode}
              onChange={(event) => setDeviceCode(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="claim-code">Claim code</label>
            <input
              id="claim-code"
              className="input mono"
              placeholder="XXXX-XXXX-XXXX"
              required
              autoComplete="off"
              value={claimCode}
              onChange={(event) => setClaimCode(event.target.value)}
            />
          </div>
        </div>

        <div className="row">
          <button type="submit" className="button button-primary" disabled={isSubmitting}>
            {isSubmitting ? "Adding…" : "Add device"}
          </button>
          <button type="button" className="button button-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}


const STATE_LABELS = {
  online: "Active in the last hour",
  idle: "Active today",
  offline: "No uploads in 24 h",
};


const REFRESH_SECONDS = 30;


function DeviceCard({ device, showOwner, isViewer }) {
  const state = activityState(device.last_recording_at);

  return (
    <Link to={`/devices/${device.id}`} className="device-card">
      <div className="row">
        <div style={{ minWidth: 0 }}>
          <h3>{device.name}</h3>
          <div className="small faint mono">{device.device_code}</div>
        </div>
        <span className="spacer" />
        {!device.is_active && <span className="badge badge-warning">Inactive</span>}
        {device.is_shared && (
          <span className="badge badge-green" title="Every signed-in account can view this device">
            {isViewer ? "Shared · view only" : "Shared"}
          </span>
        )}
      </div>

      <div className="device-metrics">
        <div className="device-metric">
          <strong>{formatNumber(device.detection_count)}</strong>
          <span>detections</span>
        </div>
        <div className="device-metric">
          <strong>{formatNumber(device.recording_count)}</strong>
          <span>snippets</span>
        </div>
        <div className="device-metric">
          <strong>{device.last_recording_at ? formatRelative(device.last_recording_at) : "—"}</strong>
          <span>last upload</span>
        </div>
      </div>

      <div className="row small muted">
        <span className={`status-dot ${state}`} />
        <span>{STATE_LABELS[state]}</span>
        {showOwner && (
          <>
            <span className="spacer" />
            <span className="faint">
              {device.owner ? device.owner.email : "Unclaimed"}
            </span>
          </>
        )}
      </div>
    </Link>
  );
}


function DevicesPage() {
  const { user, isAdmin } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [notice, setNotice] = useState(null);

  const showForm = searchParams.get("add") === "1";

  const { data, error, isLoading, reload } = useApi(() => listDevices(), []);

  usePolling(() => reload({ silent: true }), REFRESH_SECONDS * 1000);


  function setShowForm(show) {
    setSearchParams(show ? { add: "1" } : {}, { replace: true });
  }


  function handleClaimed(device) {
    setShowForm(false);
    setNotice(`${device.name} (${device.device_code}) was added to your account.`);
    reload();
  }


  const devices = data?.items ?? [];


  return (
    <main className="page">
      <PageHeader
        eyebrow={isAdmin ? "All devices" : "Your devices"}
        title="Devices"
        description="Monitoring nodes linked to your account, and any shared with everyone. Open one to see its recordings and detections."
        actions={
          !showForm && (
            <button type="button" className="button button-primary" onClick={() => setShowForm(true)}>
              + Add device
            </button>
          )
        }
      />

      <Alert kind="success">{notice}</Alert>
      {notice && <div style={{ height: 16 }} />}

      {showForm && (
        <ClaimDeviceForm onClaimed={handleClaimed} onCancel={() => setShowForm(false)} />
      )}

      <Alert>{error}</Alert>

      {isLoading && !data && <LoadingState label="Loading devices…" />}

      {data && devices.length === 0 && !showForm && (
        <EmptyState title="No devices yet" onAction={() => setShowForm(true)} actionLabel="Add a device">
          Bought an AvianAcoustics device? Add it with its device code and
          claim code.
        </EmptyState>
      )}

      {devices.length > 0 && (
        <div className="device-grid">
          {devices.map((device) => (
            <DeviceCard
              key={device.id}
              device={device}
              showOwner={isAdmin}
              isViewer={!isAdmin && device.owner?.id !== user?.id}
            />
          ))}
        </div>
      )}
    </main>
  );
}


export default DevicesPage;
