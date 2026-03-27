import { useEffect, useRef, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { AuthUser, TelegramLinkState } from "../types";

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
  const [telegramState, setTelegramState] = useState<TelegramLinkState | null>(null);
  const [telegramStateLoaded, setTelegramStateLoaded] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void loadTelegramState();
  }, []);

  async function loadTelegramState() {
    try {
      const state = await api.getMyTelegramState();
      setTelegramState(state);
    } catch {
      setTelegramState(null);
    } finally {
      setTelegramStateLoaded(true);
    }
  }

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

  async function handleStartTelegramDiscovery() {
    setTelegramBusy(true);
    setError("");
    setStatus("");
    try {
      const result = await api.startMyTelegramDiscovery();
      setTelegramState((current) => ({
        linked: current?.linked || false,
        notifications_enabled: current?.notifications_enabled || false,
        bot_username: result.bot_username,
        chat_id: current?.chat_id || null,
        pending_chat_id: null,
        telegram_username: current?.telegram_username || null,
        telegram_first_name: current?.telegram_first_name || null,
        pending_code: result.code,
        pending_code_expires_at: result.expires_at,
      }));
      setStatus("Telegram link generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Telegram discovery.");
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleCompleteTelegramDiscovery() {
    setTelegramBusy(true);
    setError("");
    setStatus("");
    try {
      const state = await api.completeMyTelegramDiscovery();
      setTelegramState(state);
      onUpdated({
        ...currentUser,
        telegram_linked: state.linked,
        telegram_notifications_enabled: state.notifications_enabled,
      });
      setStatus("Telegram linked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete Telegram discovery.");
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleRefreshTelegram() {
    setTelegramBusy(true);
    setError("");
    setStatus("");
    try {
      const state = await api.getMyTelegramState();
      setTelegramState(state);
      setStatus(state.linked ? "Telegram linked." : "Telegram not linked.");
      onUpdated({
        ...currentUser,
        telegram_linked: state.linked,
        telegram_notifications_enabled: state.notifications_enabled,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh Telegram state.");
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleToggleTelegramNotifications(nextEnabled: boolean) {
    setTelegramBusy(true);
    setError("");
    setStatus("");
    try {
      const state = await api.updateMyTelegramPreferences({ notifications_enabled: nextEnabled });
      setTelegramState(state);
      onUpdated({
        ...currentUser,
        telegram_linked: state.linked,
        telegram_notifications_enabled: state.notifications_enabled,
      });
      setStatus("Telegram preferences updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update Telegram preferences.");
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleDisconnectTelegram() {
    setTelegramBusy(true);
    setError("");
    setStatus("");
    try {
      const state = await api.disconnectMyTelegram();
      setTelegramState(state);
      onUpdated({
        ...currentUser,
        telegram_linked: false,
        telegram_notifications_enabled: false,
      });
      setStatus("Telegram disconnected.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect Telegram.");
    } finally {
      setTelegramBusy(false);
    }
  }

  async function handleSendTelegramTest() {
    setTelegramBusy(true);
    setError("");
    setStatus("");
    try {
      await api.sendMyTelegramTestNotification();
      setStatus("Test notification sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send test notification.");
    } finally {
      setTelegramBusy(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleAvatarUpload(file);
  }

  const telegramLinked = Boolean(telegramState?.linked);
  const telegramPending = Boolean(telegramState?.pending_code);
  const telegramNotificationsEnabled = Boolean(telegramState?.notifications_enabled);
  const telegramStatusLabel = telegramLinked ? "Linked" : telegramPending ? "Pending" : "Not linked";
  const telegramAccountLabel = telegramState?.telegram_username
    ? `@${telegramState.telegram_username}`
    : telegramState?.telegram_first_name || "-";
  const botUsername = telegramState?.bot_username?.trim() || "";
  const telegramBotLabel = !telegramStateLoaded
    ? "Loading..."
    : botUsername
      ? `@${botUsername.replace(/^@/, "")}`
      : telegramState
        ? "Not configured"
        : "Unavailable";
  const telegramStartUrl = telegramState?.bot_username && telegramState?.pending_code
    ? `https://t.me/${telegramState.bot_username}?start=${telegramState.pending_code}`
    : null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <FocusLock returnFocus>
        <div
          className="modal-card settings-modal-card profile-settings-modal"
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

          {error ? <div className="profile-banner error-banner">{error}</div> : null}
          {status ? <div className="profile-banner success-banner">{status}</div> : null}

          <div className="profile-settings-shell">
            <section className="profile-section-card profile-identity-card">
              <div className="profile-section-head">
                <h4>Identity</h4>
              </div>
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
                <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()} disabled={savingProfile}>
                  {savingProfile ? "Saving..." : "Change Photo"}
                </button>
              </div>
              <div className="profile-identity-meta">
                <strong>{currentUser.display_name}</strong>
                <span>{currentUser.email}</span>
              </div>
              <div className="form-grid profile-identity-grid">
                <label>
                  Display Name
                  <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
                </label>
                <label>
                  Email
                  <input value={currentUser.email} readOnly />
                </label>
                <label>
                  Job Title
                  <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} placeholder="Research Engineer" />
                </label>
                <label>
                  Organization
                  <input value={organization} onChange={(e) => setOrganization(e.target.value)} placeholder="ACME Labs" />
                </label>
                <label className="full-span">
                  Phone
                  <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 555 123 4567" />
                </label>
              </div>
            </section>

            <div className="profile-side-stack">
              <section className="profile-section-card">
                <div className="profile-section-head">
                  <h4>Security</h4>
                  <button type="button" className="ghost" onClick={() => void handlePasswordChange()} disabled={changingPassword}>
                    {changingPassword ? "Saving..." : "Change Password"}
                  </button>
                </div>
                <div className="form-grid profile-security-grid">
                  <label>
                    Current Password
                    <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
                  </label>
                  <label>
                    New Password
                    <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                  </label>
                  <label className="full-span">
                    Confirm Password
                    <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
                  </label>
                </div>
              </section>

              <section className="profile-section-card">
                <div className="profile-section-head">
                  <h4>Telegram</h4>
                  <span className={`profile-status-pill ${telegramLinked ? "linked" : telegramPending ? "pending" : "idle"}`}>
                    {telegramStatusLabel}
                  </span>
                </div>
                <div className="profile-steps">
                  <div className={`profile-step ${!telegramPending && !telegramLinked ? "active" : ""}`}>
                    <span className="profile-step-index">1</span>
                    <span className="profile-step-label">Generate Link</span>
                  </div>
                  <div className={`profile-step ${telegramPending && !telegramLinked ? "active" : ""}`}>
                    <span className="profile-step-index">2</span>
                    <span className="profile-step-label">Open Bot</span>
                  </div>
                  <div className={`profile-step ${telegramPending && !telegramLinked ? "active" : ""}`}>
                    <span className="profile-step-index">3</span>
                    <span className="profile-step-label">Press Start</span>
                  </div>
                  <div className={`profile-step ${telegramPending && !telegramLinked ? "active" : ""}`}>
                    <span className="profile-step-index">4</span>
                    <span className="profile-step-label">Find Chat</span>
                  </div>
                  <div className={`profile-step ${telegramLinked ? "done" : ""}`}>
                    <span className="profile-step-index">5</span>
                    <span className="profile-step-label">Send Test</span>
                  </div>
                </div>
                <div className="profile-telegram-meta">
                  <div className="profile-telegram-meta-item">
                    <span>Bot</span>
                    <strong>{telegramBotLabel}</strong>
                  </div>
                  {telegramLinked ? (
                    <div className="profile-telegram-meta-item">
                      <span>Account</span>
                      <strong>{telegramAccountLabel}</strong>
                    </div>
                  ) : null}
                </div>
                {telegramPending ? (
                  <div className="profile-telegram-grid">
                    <label>
                      Start Link
                      <input value={telegramStartUrl || ""} readOnly />
                    </label>
                    <label>
                      Code
                      <input value={telegramState?.pending_code || ""} readOnly />
                    </label>
                  </div>
                ) : null}
                {telegramLinked ? (
                  <div className="profile-telegram-grid">
                    <label>
                      Chat ID
                      <input value={telegramState?.chat_id || ""} readOnly />
                    </label>
                    <label>
                      Notifications
                      <select
                        value={telegramNotificationsEnabled ? "enabled" : "disabled"}
                        disabled={telegramBusy}
                        onChange={(e) => void handleToggleTelegramNotifications(e.target.value === "enabled")}
                      >
                        <option value="disabled">Disabled</option>
                        <option value="enabled">Enabled</option>
                      </select>
                    </label>
                  </div>
                ) : null}
                <div className="profile-telegram-actions">
                  <button type="button" className="ghost" onClick={() => void handleRefreshTelegram()} disabled={telegramBusy}>
                    Refresh
                  </button>
                  {!telegramLinked ? (
                    <>
                      <button type="button" className="ghost" onClick={() => void handleStartTelegramDiscovery()} disabled={telegramBusy}>
                        {telegramBusy ? "Working..." : telegramPending ? "Regenerate Link" : "Generate Link"}
                      </button>
                      {telegramPending && telegramStartUrl ? (
                        <a
                          className="ghost profile-inline-link-btn"
                          href={telegramStartUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open Bot
                        </a>
                      ) : null}
                      {telegramPending ? (
                        <button type="button" className="ghost" onClick={() => void handleCompleteTelegramDiscovery()} disabled={telegramBusy}>
                          {telegramBusy ? "Working..." : "Find Chat"}
                        </button>
                      ) : null}
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => void handleSendTelegramTest()}
                        disabled={telegramBusy || !telegramNotificationsEnabled}
                      >
                        {telegramBusy ? "Working..." : "Send Test"}
                      </button>
                      <button type="button" className="ghost" onClick={() => void handleDisconnectTelegram()} disabled={telegramBusy}>
                        {telegramBusy ? "Working..." : "Disconnect"}
                      </button>
                    </>
                  )}
                </div>
              </section>
            </div>
          </div>

          <div className="modal-actions profile-modal-actions">
            <button type="button" className="ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="primary" onClick={() => void handleSave()} disabled={savingProfile}>
              {savingProfile ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </FocusLock>
    </div>
  );
}
