import { useState } from "react";

import { changePassword, updateMe } from "../api/authApi";
import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Alert, PageHeader } from "../components/ui";
import { formatDateTime } from "../utils/format";


const MIN_PASSWORD_LENGTH = 8;


function ProfileCard() {
  const { user, setUser } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setIsSaving(true);

    try {
      setUser(await updateMe({ displayName: displayName.trim() }));
      setMessage("Profile saved.");
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not save your profile."));
    } finally {
      setIsSaving(false);
    }
  }


  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h2>Profile</h2>
          <p>How your name appears in AvianAcoustics.</p>
        </div>
      </div>

      <form className="form" onSubmit={handleSubmit}>
        <Alert kind="success">{message}</Alert>
        <Alert>{error}</Alert>

        <div className="field">
          <label htmlFor="display-name">Name</label>
          <input id="display-name" className="input" maxLength={120}
            value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </div>

        <div className="field">
          <span className="field-label">Email</span>
          <span>{user?.email}</span>
        </div>

        <div className="small faint">
          Member since {formatDateTime(user?.created_at)}
          {user?.is_admin && " · Administrator"}
        </div>

        <div>
          <button type="submit" className="button button-primary" disabled={isSaving}>
            {isSaving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </form>
    </section>
  );
}


function PasswordCard() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);


  async function handleSubmit(event) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    if (newPassword !== confirm) {
      setError("The new passwords do not match.");
      return;
    }

    setIsSaving(true);

    try {
      await changePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setMessage("Password changed.");
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not change your password."));
    } finally {
      setIsSaving(false);
    }
  }


  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h2>Change password</h2>
          <p>At least {MIN_PASSWORD_LENGTH} characters.</p>
        </div>
      </div>

      <form className="form" onSubmit={handleSubmit}>
        <Alert kind="success">{message}</Alert>
        <Alert>{error}</Alert>

        <div className="field">
          <label htmlFor="current-password">Current password</label>
          <input id="current-password" className="input" type="password" required
            autoComplete="current-password" value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)} />
        </div>

        <div className="field">
          <label htmlFor="new-password">New password</label>
          <input id="new-password" className="input" type="password" required
            autoComplete="new-password" value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)} />
        </div>

        <div className="field">
          <label htmlFor="confirm-password">Confirm new password</label>
          <input id="confirm-password" className="input" type="password" required
            autoComplete="new-password" value={confirm}
            onChange={(event) => setConfirm(event.target.value)} />
        </div>

        <div>
          <button type="submit" className="button button-primary" disabled={isSaving}>
            {isSaving ? "Changing…" : "Change password"}
          </button>
        </div>
      </form>
    </section>
  );
}


function AccountPage() {
  return (
    <main className="page">
      <PageHeader eyebrow="Account" title="Account settings" />

      <div className="grid grid-2">
        <ProfileCard />
        <PasswordCard />
      </div>
    </main>
  );
}


export default AccountPage;
