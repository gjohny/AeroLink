import { useState } from "react";
import "../settings.css";

async function postAccountAction(endpoint, payload) {
  const response = await fetch(`/api/auth/${endpoint}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Request failed. Please try again.");
  return data;
}

export default function AccountSettings({ user, onAccountDeleted }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changing, setChanging] = useState(false);
  const [changeMessage, setChangeMessage] = useState("");
  const [changeError, setChangeError] = useState("");
  const [showDelete, setShowDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  async function handleChangePassword(event) {
    event.preventDefault();
    setChangeError("");
    setChangeMessage("");
    if (newPassword !== confirmPassword) {
      setChangeError("New passwords do not match.");
      return;
    }
    if (newPassword.length < 10) {
      setChangeError("New password must be at least 10 characters.");
      return;
    }
    setChanging(true);
    try {
      const result = await postAccountAction("change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setChangeMessage(result.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      setChangeError(error.message);
    } finally {
      setChanging(false);
    }
  }

  async function handleDelete(event) {
    event.preventDefault();
    setDeleteError("");
    if (deleteConfirmation !== "DELETE") {
      setDeleteError("Type DELETE exactly to confirm.");
      return;
    }
    setDeleting(true);
    try {
      await postAccountAction("delete-account", {
        password: deletePassword,
        confirmation: deleteConfirmation,
      });
      onAccountDeleted();
    } catch (error) {
      setDeleteError(error.message);
      setDeleting(false);
    }
  }

  return (
    <section className="account-settings-page">
      <header className="account-settings-header">
        <span className="account-settings-eyebrow">ACCOUNT &amp; SECURITY</span>
        <h1>Account Settings</h1>
        <p>Manage your AeroLink account security.</p>
      </header>

      <div className="account-settings-grid">
        <div className="account-settings-card">
          <div className="account-settings-heading">
            <span className="account-settings-icon" aria-hidden="true">
                <svg
                    width="28"
                    height="28"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <rect x="5" y="10" width="14" height="11" rx="2" />
                    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                </svg>
                </span>
            <div>
              <h2>Change Password</h2>
              <p>Use a new password with at least 10 characters.</p>
            </div>
          </div>
          <form onSubmit={handleChangePassword} className="account-settings-form">
            <label htmlFor="account-current">Current Password</label>
            <input id="account-current" type="password" autoComplete="current-password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Enter your current password" />
            <label htmlFor="account-new">New Password</label>
            <input id="account-new" type="password" autoComplete="new-password" minLength={10} required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="At least 10 characters" />
            <label htmlFor="account-confirm">Confirm New Password</label>
            <input id="account-confirm" type="password" autoComplete="new-password" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Re-enter your new password" />
            {changeError && <p className="account-settings-error" role="alert">{changeError}</p>}
            {changeMessage && <p className="account-settings-success" role="status">{changeMessage}</p>}
            <button type="submit" className="account-settings-primary" disabled={changing}>
              {changing ? "Updating..." : "Update Password →"}
            </button>
          </form>
        </div>

        <div className="account-settings-card account-settings-danger-card">
          <div className="account-settings-heading">
            <span
                className="account-settings-icon account-settings-danger-icon"
                aria-hidden="true"
                >
                <svg
                    width="28"
                    height="28"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <path d="M10.3 3.9 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
                    <path d="M12 9v4" />
                    <path d="M12 17h.01" />
                </svg>
            </span>
            <div>
              <h2>Delete Account</h2>
              <p>Permanently remove your account.</p>
            </div>
          </div>
          {!showDelete ? (
            <button type="button" className="account-settings-danger-button" onClick={() => setShowDelete(true)}>
              Delete Account
            </button>
          ) : (
            <form className="account-settings-form account-settings-delete-form" onSubmit={handleDelete}>
              <p className="account-settings-warning">
                This action is permanent. Enter your password and type <strong>DELETE</strong> to confirm.
              </p>
              <label htmlFor="account-delete-password">Current Password</label>
              <input id="account-delete-password" type="password" autoComplete="current-password" required value={deletePassword} onChange={(e) => setDeletePassword(e.target.value)} placeholder="Enter your password" />
              <label htmlFor="account-delete-confirm">Type DELETE to confirm</label>
              <input id="account-delete-confirm" type="text" autoComplete="off" required value={deleteConfirmation} onChange={(e) => setDeleteConfirmation(e.target.value)} placeholder="DELETE" />
              {deleteError && <p className="account-settings-error" role="alert">{deleteError}</p>}
              <div className="account-settings-delete-actions">
                <button type="button" className="account-settings-cancel" disabled={deleting} onClick={() => {
                  setShowDelete(false);
                  setDeletePassword("");
                  setDeleteConfirmation("");
                  setDeleteError("");
                }}>Cancel</button>
                <button type="submit" className="account-settings-danger-button" disabled={deleting || deleteConfirmation !== "DELETE"}>
                  {deleting ? "Deleting..." : "Permanently Delete Account"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
