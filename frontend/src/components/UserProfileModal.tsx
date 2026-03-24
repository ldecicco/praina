import { useRef, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { AuthUser } from "../types";

type Props = {
  currentUser: AuthUser;
  onClose: () => void;
  onUpdated: (user: AuthUser) => void;
};

const API_BASE = import.meta.env.VITE_API_BASE || "";

function avatarSrc(user: AuthUser): string | null {
  if (!user.avatar_url) return null;
  return `${API_BASE}${user.avatar_url}`;
}

function userInitials(name: string): string {
  return name
    .split(" ")
    .map((p) => p[0]?.toUpperCase() || "")
    .slice(0, 2)
    .join("") || "U";
}

export function UserProfileModal({ currentUser, onClose, onUpdated }: Props) {
  const [displayName, setDisplayName] = useState(currentUser.display_name);
  const [jobTitle, setJobTitle] = useState(currentUser.job_title ?? "");
  const [organization, setOrganization] = useState(currentUser.organization ?? "");
  const [phone, setPhone] = useState(currentUser.phone ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [avatarPreview, setAvatarPreview] = useState<string | null>(avatarSrc(currentUser));
  const [savingProfile, setSavingProfile] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleSave() {
    if (!displayName.trim()) {
      setError("Display name is required.");
      return;
    }
    setSavingProfile(true);
    setError("");
    setStatus("");
    try {
      const updated = await api.updateMyProfile({
        display_name: displayName.trim(),
        job_title: jobTitle.trim() || null,
        organization: organization.trim() || null,
        phone: phone.trim() || null,
      });
      setStatus("Profile updated.");
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update profile.");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleAvatarUpload(file: File) {
    setSavingProfile(true);
    setError("");
    try {
      const result = await api.uploadMyAvatar(file);
      const newUrl = `${API_BASE}${result.avatar_url}`;
      setAvatarPreview(newUrl + "?t=" + Date.now());
      onUpdated({ ...currentUser, avatar_url: result.avatar_url });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload avatar.");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handlePasswordChange() {
    if (!currentPassword || !newPassword || !confirmPassword) {
      setError("All password fields are required.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    setChangingPassword(true);
    setError("");
    setStatus("");
    try {
      await api.changeMyPassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setStatus("Password updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update password.");
    } finally {
      setChangingPassword(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleAvatarUpload(file);
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <FocusLock returnFocus>
        <div
          className="modal-card"
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !savingProfile && !changingPassword) {
              e.preventDefault();
              void handleSave();
            }
          }}
        >
          <div className="modal-head">
            <h3>Profile</h3>
            <button type="button" className="ghost docs-action-btn" onClick={onClose} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
          </div>

          {error ? <p className="error">{error}</p> : null}
          {status ? <p className="success">{status}</p> : null}

          <div className="profile-avatar-section">
            <button
              type="button"
              className="profile-avatar-preview"
              onClick={() => fileInputRef.current?.click()}
              title="Change avatar"
            >
              {avatarPreview ? (
                <img src={avatarPreview} alt="Avatar" />
              ) : (
                <span className="profile-avatar-initials">{userInitials(currentUser.display_name)}</span>
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            <p className="muted small">Click to change photo</p>
          </div>

          <div className="form-grid" style={{ padding: "0 16px 16px" }}>
            <label>
              Display Name
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
            <label>
              Job Title
              <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="e.g. Research Engineer" />
            </label>
            <label>
              Organization
              <input value={organization} onChange={(e) => setOrganization(e.target.value)} placeholder="e.g. ACME Labs" />
            </label>
            <label>
              Phone
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 555 123 4567" />
            </label>
          </div>

          <div className="form-grid" style={{ padding: "0 16px 16px" }}>
            <label>
              Current Password
              <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
            </label>
            <label>
              New Password
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            </label>
            <label>
              Confirm Password
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            </label>
          </div>

          <div className="modal-actions" style={{ padding: "0 16px 16px", display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" className="ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="ghost" onClick={() => void handlePasswordChange()} disabled={changingPassword}>
              {changingPassword ? "Saving..." : "Change Password"}
            </button>
            <button type="button" className="primary" onClick={() => void handleSave()} disabled={savingProfile}>
              {savingProfile ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </FocusLock>
    </div>
  );
}
