import { useState } from "react";

import { Link } from "react-router-dom";

import { listUsers, updateUser } from "../api/activityApi";
import { errorMessage } from "../api/client";
import {
  assignDeviceOwner,
  createDevice,
  deleteDevice,
  listDevices,
  regenerateClaimCode,
  updateDevice,
} from "../api/devicesApi";
import { useAuth } from "../auth/AuthContext";
import { Alert, LoadingState, PageHeader } from "../components/ui";
import RegionSelect from "../components/RegionSelect";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatNumber, formatRelative } from "../utils/format";


function ClaimCodeBox({ deviceCode, claimCode, onDismiss }) {
  const [copied, setCopied] = useState(false);


  async function copy() {
    try {
      await navigator.clipboard.writeText(claimCode);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }


  return (
    <div className="stack" style={{ gap: 10, marginBottom: 16 }}>
      <div className="claim-code">
        <div>
          <div className="small muted">
            Claim code for <span className="mono">{deviceCode}</span>
          </div>
          <div className="code">{claimCode}</div>
        </div>
        <div className="row">
          <button type="button" className="button button-secondary button-small" onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </button>
          <button type="button" className="button button-ghost button-small" onClick={onDismiss}>
            Done
          </button>
        </div>
      </div>
      <div className="small faint">
        Shown only once — the server keeps just a hash. Give it to the device's
        owner with the device code (or print it on the device label).
      </div>
    </div>
  );
}


// ------------------------------------------------------------
// Devices
// ------------------------------------------------------------

function NewDeviceForm({ onCreated }) {
  const [form, setForm] = useState({ deviceCode: "", name: "", description: "", regionCode: "" });
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);

    try {
      onCreated(
        await createDevice({
          deviceCode: form.deviceCode.trim(),
          name: form.name.trim(),
          description: form.description.trim(),
          regionCode: form.regionCode,
        })
      );
      setForm({ deviceCode: "", name: "", description: "", regionCode: "" });
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not register the device."));
    } finally {
      setIsSaving(false);
    }
  }


  return (
    <form className="form" onSubmit={handleSubmit} style={{ marginBottom: 20 }}>
      <Alert>{error}</Alert>
      <div className="form-row">
        <div className="field">
          <label htmlFor="new-code">Device code</label>
          <input id="new-code" className="input mono" placeholder="NODE-002" required maxLength={50}
            value={form.deviceCode}
            onChange={(event) => setForm({ ...form, deviceCode: event.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="new-name">Name</label>
          <input id="new-name" className="input" placeholder="Sinharaja canopy node" required maxLength={120}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="new-description">Description (optional)</label>
          <input id="new-description" className="input" maxLength={2000}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="new-region">Province or district (optional)</label>
          <RegionSelect id="new-region" value={form.regionCode}
            onChange={(regionCode) => setForm({ ...form, regionCode })} />
        </div>
      </div>
      <div>
        <button type="submit" className="button button-primary" disabled={isSaving}>
          {isSaving ? "Registering…" : "Register device"}
        </button>
      </div>
    </form>
  );
}


function DeviceRow({ device, onChanged, onClaimCode, onError }) {
  const [ownerEmail, setOwnerEmail] = useState("");
  const [mode, setMode] = useState(null); // "assign" | "delete" | null
  const [isBusy, setIsBusy] = useState(false);


  async function run(action) {
    setIsBusy(true);
    onError(null);

    try {
      await action();
      setMode(null);
    } catch (requestError) {
      onError(errorMessage(requestError, "The action failed."));
    } finally {
      setIsBusy(false);
    }
  }


  return (
    <tr>
      <td>
        <Link to={`/devices/${device.id}`}>{device.name}</Link>
        <div className="small faint mono">{device.device_code}</div>
        {device.is_shared && (
          <span className="badge badge-green" style={{ marginTop: 4 }}
            title="Every signed-in account can view this device">
            Shared
          </span>
        )}
      </td>
      <td>
        {device.owner ? (
          <span>{device.owner.email}</span>
        ) : (
          <span className="badge">Unclaimed</span>
        )}
      </td>
      <td>{formatNumber(device.recording_count)}</td>
      <td>{device.last_recording_at ? formatRelative(device.last_recording_at) : "—"}</td>
      <td>
        {mode === null && (
          <div className="row" style={{ gap: 6 }}>
            <button type="button" className="button button-secondary button-small" disabled={isBusy}
              onClick={() => run(async () => onClaimCode(await regenerateClaimCode(device.id)))}>
              New claim code
            </button>
            <button type="button" className="button button-secondary button-small" disabled={isBusy}
              title={device.is_shared
                ? "Only the owner and admins will see this device"
                : "Every signed-in account will see this device (read-only)"}
              onClick={() => run(async () =>
                onChanged(await updateDevice(device.id, { is_shared: !device.is_shared })))}>
              {device.is_shared ? "Stop sharing" : "Share"}
            </button>
            <button type="button" className="button button-secondary button-small" disabled={isBusy}
              onClick={() => setMode("assign")}>
              {device.owner ? "Reassign" : "Assign"}
            </button>
            {device.owner && (
              <button type="button" className="button button-ghost button-small" disabled={isBusy}
                onClick={() => run(async () => onChanged(await assignDeviceOwner(device.id, null)))}>
                Unassign
              </button>
            )}
            <button type="button" className="button button-danger button-small" disabled={isBusy}
              onClick={() => setMode("delete")}>
              Delete
            </button>
          </div>
        )}

        {mode === "assign" && (
          <form className="row" style={{ gap: 6 }}
            onSubmit={(event) => {
              event.preventDefault();
              run(async () => onChanged(await assignDeviceOwner(device.id, ownerEmail.trim())));
            }}>
            <input className="input" type="email" required placeholder="owner@example.com"
              style={{ width: 220, padding: "6px 10px" }}
              value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} />
            <button type="submit" className="button button-primary button-small" disabled={isBusy}>Assign</button>
            <button type="button" className="button button-ghost button-small" onClick={() => setMode(null)}>Cancel</button>
          </form>
        )}

        {mode === "delete" && (
          <div className="row" style={{ gap: 6 }}>
            <span className="small" style={{ color: "var(--danger)" }}>
              Delete with all {formatNumber(device.recording_count)} recordings?
            </span>
            <button type="button" className="button button-danger button-small" disabled={isBusy}
              onClick={() => run(async () => { await deleteDevice(device.id); onChanged(null, device.id); })}>
              Delete
            </button>
            <button type="button" className="button button-ghost button-small" onClick={() => setMode(null)}>Cancel</button>
          </div>
        )}
      </td>
    </tr>
  );
}


function DevicesTab() {
  const devices = useApi(() => listDevices(), []);
  const [claim, setClaim] = useState(null);
  const [error, setError] = useState(null);


  function replaceDevice(updated, deletedId) {
    devices.setData((current) => ({
      ...current,
      items: deletedId
        ? current.items.filter((item) => item.id !== deletedId)
        : current.items.map((item) => (item.id === updated.id ? updated : item)),
    }));
  }


  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h2>Register a device</h2>
          <p>Creates the device and its claim code; the owner then adds it from their Devices page.</p>
        </div>
      </div>

      <NewDeviceForm
        onCreated={(created) => {
          setClaim({ deviceCode: created.device.device_code, claimCode: created.claim_code });
          devices.reload();
        }}
      />

      {claim && <ClaimCodeBox {...claim} onDismiss={() => setClaim(null)} />}

      <Alert>{error || devices.error}</Alert>

      {devices.isLoading && !devices.data && <LoadingState />}

      {devices.data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Owner</th>
                <th>Snippets</th>
                <th>Last upload</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.data.items.map((device) => (
                <DeviceRow
                  key={device.id}
                  device={device}
                  onChanged={replaceDevice}
                  onError={setError}
                  onClaimCode={(result) =>
                    setClaim({ deviceCode: result.device_code, claimCode: result.claim_code })
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}


// ------------------------------------------------------------
// Users
// ------------------------------------------------------------

function UsersTab() {
  const { user: me } = useAuth();
  const users = useApi(() => listUsers(), []);
  const [error, setError] = useState(null);


  async function toggle(user, field) {
    setError(null);

    try {
      const updated = await updateUser(user.id, { [field]: !user[field] });
      users.setData((current) => ({
        ...current,
        items: current.items.map((item) => (item.id === updated.id ? updated : item)),
      }));
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not update the user."));
    }
  }


  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h2>Users</h2>
          <p>Admins see every device and can manage devices and users.</p>
        </div>
      </div>

      <Alert>{error || users.error}</Alert>

      {users.isLoading && !users.data && <LoadingState />}

      {users.data && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Joined</th>
                <th>Last sign-in</th>
                <th>Role</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div>{user.display_name || "—"}</div>
                    <div className="small faint">{user.email}</div>
                  </td>
                  <td>{formatDateTime(user.created_at)}</td>
                  <td>{user.last_login_at ? formatRelative(user.last_login_at) : "—"}</td>
                  <td>
                    <button type="button"
                      className={`button button-small ${user.is_admin ? "button-primary" : "button-secondary"}`}
                      onClick={() => toggle(user, "is_admin")}
                      title={user.is_admin ? "Remove admin rights" : "Make admin"}>
                      {user.is_admin ? "Admin" : "User"}
                    </button>
                  </td>
                  <td>
                    <button type="button"
                      className={`button button-small ${user.is_active ? "button-secondary" : "button-danger"}`}
                      disabled={user.id === me?.id}
                      onClick={() => toggle(user, "is_active")}
                      title={user.is_active ? "Disable this account" : "Re-enable this account"}>
                      {user.is_active ? "Active" : "Disabled"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}


function AdminPage() {
  const [tab, setTab] = useState("devices");

  return (
    <main className="page">
      <PageHeader
        eyebrow="Administration"
        title="Admin"
        description="Register devices, issue claim codes and manage user accounts."
      />

      <div className="tabs" role="tablist">
        {[["devices", "Devices"], ["users", "Users"]].map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key}
            className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "devices" ? <DevicesTab /> : <UsersTab />}
    </main>
  );
}


export default AdminPage;
