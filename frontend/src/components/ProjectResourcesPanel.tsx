import { useCallback, useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCalendarPlus,
  faPenToSquare,
  faPlus,
  faTrash,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { Equipment, ProjectResourcesWorkspace } from "../types";

type Props = {
  projectId: string;
  title?: string;
};

type ModalKind = "requirement" | "booking" | null;

function toDateTimeInput(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function formatWindow(startAt: string, endAt: string): string {
  return `${new Date(startAt).toLocaleDateString()} ${new Date(startAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - ${new Date(endAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

export function ProjectResourcesPanel({ projectId, title = "Equipment" }: Props) {
  const [workspace, setWorkspace] = useState<ProjectResourcesWorkspace | null>(null);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [modal, setModal] = useState<ModalKind>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [requirementEquipmentId, setRequirementEquipmentId] = useState("");
  const [requirementPriority, setRequirementPriority] = useState("important");
  const [requirementPurpose, setRequirementPurpose] = useState("");
  const [requirementNotes, setRequirementNotes] = useState("");

  const [bookingEquipmentId, setBookingEquipmentId] = useState("");
  const [bookingStartAt, setBookingStartAt] = useState("");
  const [bookingEndAt, setBookingEndAt] = useState("");
  const [bookingPurpose, setBookingPurpose] = useState("");
  const [bookingNotes, setBookingNotes] = useState("");

  const loadPanel = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [workspaceRes, equipmentRes] = await Promise.all([
        api.getProjectResources(projectId),
        api.listEquipment(1, 200),
      ]);
      setWorkspace(workspaceRes);
      setEquipment(equipmentRes.items.filter((item) => item.is_active));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load equipment.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadPanel();
  }, [loadPanel]);

  const openBlockers = workspace?.blockers.filter((item) => item.status === "open") ?? [];
  const activeBookings = workspace?.bookings.filter((item) => ["requested", "approved", "active"].includes(item.status)) ?? [];
  const availableEquipment = useMemo(
    () => equipment.filter((item) => !workspace?.requirements.some((entry) => entry.equipment_id === item.id)),
    [equipment, workspace?.requirements]
  );

  function resetForm() {
    setEditingId(null);
    setRequirementEquipmentId("");
    setRequirementPriority("important");
    setRequirementPurpose("");
    setRequirementNotes("");
    setBookingEquipmentId("");
    setBookingStartAt("");
    setBookingEndAt("");
    setBookingPurpose("");
    setBookingNotes("");
  }

  function openRequirementModal(requirementId?: string) {
    resetForm();
    setModal("requirement");
    if (!requirementId || !workspace) return;
    const item = workspace.requirements.find((entry) => entry.id === requirementId);
    if (!item) return;
    setEditingId(item.id);
    setRequirementEquipmentId(item.equipment_id);
    setRequirementPriority(item.priority);
    setRequirementPurpose(item.purpose);
    setRequirementNotes(item.notes || "");
  }

  function openBookingModal(bookingId?: string) {
    resetForm();
    setModal("booking");
    if (!bookingId || !workspace) return;
    const item = workspace.bookings.find((entry) => entry.id === bookingId);
    if (!item) return;
    setEditingId(item.id);
    setBookingEquipmentId(item.equipment_id);
    setBookingStartAt(toDateTimeInput(item.start_at));
    setBookingEndAt(toDateTimeInput(item.end_at));
    setBookingPurpose(item.purpose);
    setBookingNotes(item.notes || "");
  }

  async function saveRequirement() {
    if (!projectId || !requirementEquipmentId || !requirementPurpose.trim()) return;
    try {
      setBusy(true);
      if (editingId) {
        await api.updateProjectEquipmentRequirement(projectId, editingId, {
          priority: requirementPriority,
          purpose: requirementPurpose.trim(),
          notes: requirementNotes.trim() || null,
        });
      } else {
        await api.createProjectEquipmentRequirement(projectId, {
          equipment_id: requirementEquipmentId,
          priority: requirementPriority,
          purpose: requirementPurpose.trim(),
          notes: requirementNotes.trim() || null,
        });
      }
      setModal(null);
      resetForm();
      await loadPanel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save requirement.");
    } finally {
      setBusy(false);
    }
  }

  async function saveBooking() {
    if (!projectId || !bookingEquipmentId || !bookingStartAt || !bookingEndAt || !bookingPurpose.trim()) return;
    try {
      setBusy(true);
      const payload = {
        equipment_id: bookingEquipmentId,
        project_id: projectId,
        start_at: new Date(bookingStartAt).toISOString(),
        end_at: new Date(bookingEndAt).toISOString(),
        purpose: bookingPurpose.trim(),
        notes: bookingNotes.trim() || null,
      };
      if (editingId) {
        await api.updateEquipmentBooking(editingId, {
          start_at: payload.start_at,
          end_at: payload.end_at,
          purpose: payload.purpose,
          notes: payload.notes,
        });
      } else {
        await api.createEquipmentBooking(payload);
      }
      setModal(null);
      resetForm();
      await loadPanel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save booking.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteRequirement(requirementId: string) {
    if (!window.confirm("Delete this requirement?")) return;
    try {
      setBusy(true);
      await api.deleteProjectEquipmentRequirement(projectId, requirementId);
      await loadPanel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete requirement.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelBooking(bookingId: string) {
    try {
      setBusy(true);
      await api.updateEquipmentBooking(bookingId, { status: "cancelled" });
      await loadPanel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel booking.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !workspace) {
    return <div className="card teaching-card"><strong>{title}</strong></div>;
  }

  return (
    <div className="card teaching-card resources-panel-card">
      <div className="proposal-card-head">
        <span className="teaching-section-label">
          <strong>{title}</strong>
          <span className="delivery-tab-count">{workspace?.requirements.length ?? 0} req</span>
          <span className="delivery-tab-count">{activeBookings.length} booking{activeBookings.length !== 1 ? "s" : ""}</span>
          {openBlockers.length > 0 ? <span className="delivery-tab-count">{openBlockers.length} blocker{openBlockers.length !== 1 ? "s" : ""}</span> : null}
        </span>
        <div className="resources-card-actions">
          <button type="button" className="ghost icon-text-button small" onClick={() => openBookingModal()}>
            <FontAwesomeIcon icon={faCalendarPlus} /> Booking
          </button>
          <button type="button" className="meetings-new-btn" onClick={() => openRequirementModal()}>
            <FontAwesomeIcon icon={faPlus} /> Add
          </button>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="resources-panel-stack">
        <div>
          <div className="resources-panel-subhead">Requirements</div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr><th>Equipment</th><th>Priority</th><th>Purpose</th><th /></tr>
              </thead>
              <tbody>
                {workspace?.requirements.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.equipment.name}</strong></td>
                    <td><span className="chip small">{item.priority}</span></td>
                    <td>{item.purpose}</td>
                    <td className="teaching-row-actions">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openRequirementModal(item.id)}>
                        <FontAwesomeIcon icon={faPenToSquare} />
                      </button>
                      <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteRequirement(item.id)}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </td>
                  </tr>
                ))}
                {!workspace?.requirements.length ? <tr><td colSpan={4}>No requirements</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="resources-panel-subhead">Bookings</div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr><th>Equipment</th><th>Window</th><th>Status</th><th /></tr>
              </thead>
              <tbody>
                {workspace?.bookings.slice(0, 5).map((item) => (
                  <tr key={item.id} className={item.status === "cancelled" ? "resources-row-muted" : ""}>
                    <td><strong>{item.equipment.name}</strong></td>
                    <td>{formatWindow(item.start_at, item.end_at)}</td>
                    <td><span className="chip small">{item.status}</span></td>
                    <td className="teaching-row-actions">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openBookingModal(item.id)}>
                        <FontAwesomeIcon icon={faPenToSquare} />
                      </button>
                      {item.status === "requested" || item.status === "approved" ? (
                        <button type="button" className="ghost icon-text-button small danger-text" onClick={() => void cancelBooking(item.id)}>
                          Cancel
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {!workspace?.bookings.length ? <tr><td colSpan={4}>No bookings</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="resources-panel-subhead">Blockers</div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr><th>Equipment</th><th>Reason</th><th>Days</th></tr>
              </thead>
              <tbody>
                {openBlockers.slice(0, 5).map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.equipment.name}</strong></td>
                    <td>{item.reason.split("_").join(" ")}</td>
                    <td>{item.blocked_days}</td>
                  </tr>
                ))}
                {!openBlockers.length ? <tr><td colSpan={3}>No blockers</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {modal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card settings-modal-card">
            <div className="modal-head">
              <h3>{modal === "requirement" ? (editingId ? "Edit Requirement" : "Add Requirement") : (editingId ? "Edit Booking" : "Add Booking")}</h3>
              <div className="modal-head-actions">
                <button type="button" className="meetings-new-btn" disabled={busy} onClick={() => void (modal === "requirement" ? saveRequirement() : saveBooking())}>
                  {busy ? "Saving..." : "Save"}
                </button>
                <button type="button" className="ghost docs-action-btn" onClick={() => setModal(null)} title="Close">
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>
            {modal === "requirement" ? (
              <div className="form-grid">
                <label>
                  Equipment
                  <select value={requirementEquipmentId} onChange={(event) => setRequirementEquipmentId(event.target.value)} disabled={Boolean(editingId)}>
                    <option value="">Select</option>
                    {(editingId ? equipment : availableEquipment).map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Priority
                  <select value={requirementPriority} onChange={(event) => setRequirementPriority(event.target.value)}>
                    <option value="optional">Optional</option>
                    <option value="important">Important</option>
                    <option value="critical">Critical</option>
                  </select>
                </label>
                <label className="full-span">
                  Purpose
                  <input value={requirementPurpose} onChange={(event) => setRequirementPurpose(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={4} value={requirementNotes} onChange={(event) => setRequirementNotes(event.target.value)} />
                </label>
              </div>
            ) : (
              <div className="form-grid">
                <label>
                  Equipment
                  <select value={bookingEquipmentId} onChange={(event) => setBookingEquipmentId(event.target.value)}>
                    <option value="">Select</option>
                    {equipment.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Purpose
                  <input value={bookingPurpose} onChange={(event) => setBookingPurpose(event.target.value)} />
                </label>
                <label>
                  Start
                  <input type="datetime-local" value={bookingStartAt} onChange={(event) => setBookingStartAt(event.target.value)} />
                </label>
                <label>
                  End
                  <input type="datetime-local" value={bookingEndAt} onChange={(event) => setBookingEndAt(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={4} value={bookingNotes} onChange={(event) => setBookingNotes(event.target.value)} />
                </label>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
