import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faCalendarPlus,
  faClockRotateLeft,
  faPenToSquare,
  faPlus,
  faTrash,
  faTriangleExclamation,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { AuthUser, Equipment, EquipmentBooking, EquipmentConflict, EquipmentDowntime, Lab, LabClosure, Project } from "../types";

type Props = {
  currentUser: AuthUser;
  onOpenProject: (projectId: string) => void;
};

type Tab = "labs" | "equipment" | "bookings" | "conflicts";
type ModalKind = "equipment" | "lab" | "booking" | "downtime" | "lab-closure" | null;
const SCHEDULE_START_HOUR = 8;
const SCHEDULE_END_HOUR = 21;

function startOfWeek(date: Date): Date {
  const next = new Date(date);
  const day = next.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  next.setDate(next.getDate() + diff);
  next.setHours(0, 0, 0, 0);
  return next;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function sameDay(left: Date, right: Date): boolean {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate();
}

function toDateTimeInput(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function formatRange(startAt: string, endAt: string): string {
  return `${new Date(startAt).toLocaleDateString()} ${new Date(startAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - ${new Date(endAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function formatDayTimeRange(startAt: string, endAt: string): string {
  return `${new Date(startAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - ${new Date(endAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function overlaps(startAt: Date, endAt: Date, rangeStart: Date, rangeEnd: Date): boolean {
  return startAt < rangeEnd && rangeStart < endAt;
}

function roundToNextHour(date: Date): Date {
  const next = new Date(date);
  next.setMinutes(0, 0, 0);
  if (date.getMinutes() > 0 || date.getSeconds() > 0 || date.getMilliseconds() > 0) {
    next.setHours(next.getHours() + 1);
  }
  return next;
}

export function ResourcesWorkspace({ currentUser, onOpenProject }: Props) {
  const [tab, setTab] = useState<Tab>("labs");
  const [selectedEquipmentId, setSelectedEquipmentId] = useState("");
  const [calendarWeekStart, setCalendarWeekStart] = useState(() => startOfWeek(new Date()));
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [labClosures, setLabClosures] = useState<LabClosure[]>([]);
  const [bookings, setBookings] = useState<EquipmentBooking[]>([]);
  const [conflicts, setConflicts] = useState<EquipmentConflict[]>([]);
  const [downtime, setDowntime] = useState<EquipmentDowntime[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [modal, setModal] = useState<ModalKind>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [equipmentFilterId, setEquipmentFilterId] = useState("");
  const [labFilterId, setLabFilterId] = useState("");
  const [bookingStatusFilter, setBookingStatusFilter] = useState("");
  const [bookingDateRange, setBookingDateRange] = useState("month");
  const [showWeekends, setShowWeekends] = useState(false);
  const [equipmentLabFilter, setEquipmentLabFilter] = useState("");

  const [equipmentName, setEquipmentName] = useState("");
  const [equipmentCategory, setEquipmentCategory] = useState("");
  const [equipmentModel, setEquipmentModel] = useState("");
  const [equipmentSerialNumber, setEquipmentSerialNumber] = useState("");
  const [equipmentLabId, setEquipmentLabId] = useState("");
  const [equipmentOwnerUserId, setEquipmentOwnerUserId] = useState("");
  const [equipmentStatus, setEquipmentStatus] = useState("active");
  const [equipmentUsageMode, setEquipmentUsageMode] = useState("exclusive");
  const [equipmentDescription, setEquipmentDescription] = useState("");
  const [equipmentAccessNotes, setEquipmentAccessNotes] = useState("");

  const [bookingEquipmentId, setBookingEquipmentId] = useState("");
  const [bookingProjectId, setBookingProjectId] = useState("");
  const [bookingStartAt, setBookingStartAt] = useState("");
  const [bookingEndAt, setBookingEndAt] = useState("");
  const [bookingPurpose, setBookingPurpose] = useState("");
  const [bookingNotes, setBookingNotes] = useState("");

  const [downtimeEquipmentId, setDowntimeEquipmentId] = useState("");
  const [downtimeStartAt, setDowntimeStartAt] = useState("");
  const [downtimeEndAt, setDowntimeEndAt] = useState("");
  const [downtimeReason, setDowntimeReason] = useState("maintenance");
  const [downtimeNotes, setDowntimeNotes] = useState("");

  const [labName, setLabName] = useState("");
  const [labBuilding, setLabBuilding] = useState("");
  const [labRoom, setLabRoom] = useState("");
  const [labNotes, setLabNotes] = useState("");
  const [labResponsibleUserId, setLabResponsibleUserId] = useState("");
  const [closureLabId, setClosureLabId] = useState("");
  const [closureStartAt, setClosureStartAt] = useState("");
  const [closureEndAt, setClosureEndAt] = useState("");
  const [closureReason, setClosureReason] = useState("personnel_unavailable");
  const [closureNotes, setClosureNotes] = useState("");

  const isSuperAdmin = currentUser.platform_role === "super_admin";

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    try {
      const [equipmentRes, labsRes, closuresRes, bookingsRes, conflictsRes, downtimeRes, usersRes, projectsRes] = await Promise.all([
        api.listEquipment(1, 200, "", "", ""),
        api.listLabs(1, 200),
        api.listLabClosures(1, 200, ""),
        api.listEquipmentBookings(1, 200, equipmentFilterId, "", ""),
        api.listEquipmentConflicts(equipmentFilterId ? { equipment_id: equipmentFilterId } : undefined),
        api.listEquipmentDowntime(1, 200, equipmentFilterId),
        api.listUserDiscovery(1, 200, ""),
        api.listProjects(1, 100),
      ]);
      setEquipment(equipmentRes.items);
      setLabs(labsRes.items);
      setLabClosures(closuresRes.items);
      setBookings(bookingsRes.items);
      setConflicts(conflictsRes);
      setDowntime(downtimeRes.items);
      setUsers(usersRes.items.filter((item) => item.is_active));
      setProjects(projectsRes.items);
      setSelectedEquipmentId((current) => {
        if (current && equipmentRes.items.some((item) => item.id === current)) return current;
        return equipmentRes.items[0]?.id || "";
      });
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load resources.");
    } finally {
      setLoading(false);
    }
  }, [equipmentFilterId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(""), 3000);
    return () => clearTimeout(timer);
  }, [status]);

  const activeBookings = bookings.filter((item) => ["requested", "approved", "active"].includes(item.status));
  const openConflicts = conflicts.length;
  const activeDowntime = downtime.filter((item) => new Date(item.end_at) >= new Date()).length;
  const projectMap = useMemo(() => new Map(projects.map((item) => [item.id, item])), [projects]);
  const filteredEquipment = useMemo(() => {
    let list = equipment;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((item) => item.name.toLowerCase().includes(q) || item.category?.toLowerCase().includes(q) || item.model?.toLowerCase().includes(q));
    }
    if (statusFilter) list = list.filter((item) => item.status === statusFilter);
    return list;
  }, [equipment, search, statusFilter]);
  const selectedEquipment = equipment.find((item) => item.id === selectedEquipmentId) ?? null;
  const selectedLabId = labFilterId || labs[0]?.id || "";
  const selectedLab = labs.find((item) => item.id === selectedLabId) ?? null;
  const selectedLabEquipment = useMemo(
    () => equipment.filter((item) => item.lab_id === selectedLabId).sort((left, right) => left.name.localeCompare(right.name)),
    [equipment, selectedLabId]
  );
  const selectedLabClosures = useMemo(
    () => labClosures.filter((item) => item.lab_id === selectedLabId),
    [labClosures, selectedLabId]
  );
  const selectedEquipmentBookings = useMemo(
    () => bookings.filter((item) => item.equipment_id === selectedEquipmentId),
    [bookings, selectedEquipmentId]
  );
  const selectedEquipmentDowntime = useMemo(
    () => downtime.filter((item) => item.equipment_id === selectedEquipmentId),
    [downtime, selectedEquipmentId]
  );
  const selectedEquipmentConflicts = useMemo(
    () => conflicts.filter((item) => item.equipment_id === selectedEquipmentId),
    [conflicts, selectedEquipmentId]
  );
  const selectedEquipmentUpcomingBookings = useMemo(
    () =>
      selectedEquipmentBookings
        .filter((item) => ["requested", "approved", "active"].includes(item.status) && new Date(item.end_at) >= new Date())
        .sort((left, right) => new Date(left.start_at).getTime() - new Date(right.start_at).getTime())
        .slice(0, 4),
    [selectedEquipmentBookings]
  );
  const filteredBookings = useMemo(() => {
    let list = bookings;
    if (bookingStatusFilter) list = list.filter((item) => item.status === bookingStatusFilter);
    if (bookingDateRange !== "all") {
      const now = new Date();
      const rangeStart = new Date(now);
      const rangeEnd = new Date(now);
      if (bookingDateRange === "week") {
        rangeStart.setDate(now.getDate() - now.getDay() + 1);
        rangeEnd.setDate(rangeStart.getDate() + 7);
      } else {
        rangeStart.setDate(1);
        rangeEnd.setMonth(now.getMonth() + 1, 1);
      }
      rangeStart.setHours(0, 0, 0, 0);
      rangeEnd.setHours(0, 0, 0, 0);
      list = list.filter((item) => {
        const start = new Date(item.start_at);
        const end = new Date(item.end_at);
        return start < rangeEnd && end >= rangeStart;
      });
    }
    return list;
  }, [bookings, bookingStatusFilter, bookingDateRange]);
  const weekDays = useMemo(
    () => Array.from({ length: showWeekends ? 7 : 5 }, (_, index) => addDays(calendarWeekStart, index)),
    [calendarWeekStart, showWeekends]
  );
  const scheduleHours = useMemo(
    () => Array.from({ length: SCHEDULE_END_HOUR - SCHEDULE_START_HOUR }, (_, index) => SCHEDULE_START_HOUR + index),
    []
  );
  const nextFreeSlotLabel = useMemo(() => {
    if (!selectedEquipment) return "-";
    const activeRows = selectedEquipmentBookings.filter((item) => ["requested", "approved", "active"].includes(item.status));
    const now = roundToNextHour(new Date());
    for (let offset = 0; offset < 24 * 14; offset += 1) {
      const start = new Date(now);
      start.setHours(now.getHours() + offset);
      const end = new Date(start);
      end.setHours(start.getHours() + 1);
      const blockedByDowntime = selectedEquipmentDowntime.some((item) =>
        overlaps(new Date(item.start_at), new Date(item.end_at), start, end)
      );
      const blockedByBooking =
        selectedEquipment.usage_mode === "exclusive" &&
        activeRows.some((item) => overlaps(new Date(item.start_at), new Date(item.end_at), start, end));
      if (!blockedByDowntime && !blockedByBooking) {
        return `${start.toLocaleDateString([], { day: "2-digit", month: "short" })} ${start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
      }
    }
    return "No free slot";
  }, [selectedEquipment, selectedEquipmentBookings, selectedEquipmentDowntime]);

  function resetForms() {
    setEditingId(null);
    setEquipmentName("");
    setEquipmentCategory("");
    setEquipmentModel("");
    setEquipmentSerialNumber("");
    setEquipmentLabId("");
    setEquipmentOwnerUserId("");
    setEquipmentStatus("active");
    setEquipmentUsageMode("exclusive");
    setEquipmentDescription("");
    setEquipmentAccessNotes("");
    setBookingEquipmentId("");
    setBookingProjectId("");
    setBookingStartAt("");
    setBookingEndAt("");
    setBookingPurpose("");
    setBookingNotes("");
    setDowntimeEquipmentId("");
    setDowntimeStartAt("");
    setDowntimeEndAt("");
    setDowntimeReason("maintenance");
    setDowntimeNotes("");
    setLabName("");
    setLabBuilding("");
    setLabRoom("");
    setLabNotes("");
    setLabResponsibleUserId("");
    setClosureLabId("");
    setClosureStartAt("");
    setClosureEndAt("");
    setClosureReason("personnel_unavailable");
    setClosureNotes("");
  }

  function openEquipmentModal(item?: Equipment) {
    resetForms();
    setModal("equipment");
    if (!item) return;
    setEditingId(item.id);
    setEquipmentName(item.name);
    setEquipmentCategory(item.category || "");
    setEquipmentModel(item.model || "");
    setEquipmentSerialNumber(item.serial_number || "");
    setEquipmentLabId(item.lab_id || "");
    setEquipmentOwnerUserId(item.owner_user_id || "");
    setEquipmentStatus(item.status);
    setEquipmentUsageMode(item.usage_mode);
    setEquipmentDescription(item.description || "");
    setEquipmentAccessNotes(item.access_notes || "");
  }

  function openBookingModal(item?: EquipmentBooking) {
    resetForms();
    setModal("booking");
    setBookingEquipmentId(selectedEquipmentId || "");
    if (!item) return;
    setEditingId(item.id);
    setBookingEquipmentId(item.equipment_id);
    setBookingProjectId(item.project_id);
    setBookingStartAt(toDateTimeInput(item.start_at));
    setBookingEndAt(toDateTimeInput(item.end_at));
    setBookingPurpose(item.purpose);
    setBookingNotes(item.notes || "");
  }

  function openDowntimeModal(item?: Equipment) {
    resetForms();
    setModal("downtime");
    if (item) setDowntimeEquipmentId(item.id);
  }

  function openLabModal(item?: Lab) {
    resetForms();
    setModal("lab");
    if (!item) return;
    setEditingId(item.id);
    setLabName(item.name);
    setLabBuilding(item.building || "");
    setLabRoom(item.room || "");
    setLabNotes(item.notes || "");
    setLabResponsibleUserId(item.responsible_user_id || "");
  }

  function openLabClosureModal(item?: Lab | LabClosure) {
    resetForms();
    setModal("lab-closure");
    if (!item) return;
    if ("lab_id" in item) {
      setEditingId(item.id);
      setClosureLabId(item.lab_id);
      setClosureStartAt(toDateTimeInput(item.start_at));
      setClosureEndAt(toDateTimeInput(item.end_at));
      setClosureReason(item.reason);
      setClosureNotes(item.notes || "");
      return;
    }
    setClosureLabId(item.id);
  }

  async function saveEquipment() {
    if (!equipmentName.trim()) return;
    try {
      setBusy(true);
      const payload = {
        name: equipmentName.trim(),
        category: equipmentCategory.trim() || null,
        model: equipmentModel.trim() || null,
        serial_number: equipmentSerialNumber.trim() || null,
        description: equipmentDescription.trim() || null,
        lab_id: equipmentLabId || null,
        owner_user_id: equipmentOwnerUserId || null,
        status: equipmentStatus,
        usage_mode: equipmentUsageMode,
        access_notes: equipmentAccessNotes.trim() || null,
      };
      if (editingId) await api.updateEquipment(editingId, payload);
      else await api.createEquipment(payload);
      setModal(null);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save equipment.");
    } finally {
      setBusy(false);
    }
  }

  async function saveLab() {
    if (!labName.trim()) return;
    try {
      setBusy(true);
      const payload = {
        name: labName.trim(),
        building: labBuilding.trim() || null,
        room: labRoom.trim() || null,
        notes: labNotes.trim() || null,
        responsible_user_id: labResponsibleUserId || null,
      };
      if (editingId) await api.updateLab(editingId, payload);
      else await api.createLab(payload);
      setModal(null);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save lab.");
    } finally {
      setBusy(false);
    }
  }

  async function saveLabClosure() {
    if (!closureLabId || !closureStartAt || !closureEndAt) return;
    try {
      setBusy(true);
      const payload = {
        lab_id: closureLabId,
        start_at: new Date(closureStartAt).toISOString(),
        end_at: new Date(closureEndAt).toISOString(),
        reason: closureReason,
        notes: closureNotes.trim() || null,
      };
      if (editingId) await api.updateLabClosure(editingId, payload);
      else await api.createLabClosure(payload);
      setModal(null);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save lab closure.");
    } finally {
      setBusy(false);
    }
  }

  async function saveBooking() {
    if (!bookingEquipmentId || !bookingProjectId || !bookingStartAt || !bookingEndAt || !bookingPurpose.trim()) return;
    try {
      setBusy(true);
      if (editingId) {
        await api.updateEquipmentBooking(editingId, {
          start_at: new Date(bookingStartAt).toISOString(),
          end_at: new Date(bookingEndAt).toISOString(),
          purpose: bookingPurpose.trim(),
          notes: bookingNotes.trim() || null,
        });
      } else {
        await api.createEquipmentBooking({
          equipment_id: bookingEquipmentId,
          project_id: bookingProjectId,
          start_at: new Date(bookingStartAt).toISOString(),
          end_at: new Date(bookingEndAt).toISOString(),
          purpose: bookingPurpose.trim(),
          notes: bookingNotes.trim() || null,
        });
      }
      setModal(null);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save booking.");
    } finally {
      setBusy(false);
    }
  }

  async function saveDowntime() {
    if (!downtimeEquipmentId || !downtimeStartAt || !downtimeEndAt) return;
    try {
      setBusy(true);
      await api.createEquipmentDowntime({
        equipment_id: downtimeEquipmentId,
        start_at: new Date(downtimeStartAt).toISOString(),
        end_at: new Date(downtimeEndAt).toISOString(),
        reason: downtimeReason,
        notes: downtimeNotes.trim() || null,
      });
      setModal(null);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save downtime.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteEquipmentRow(equipmentId: string) {
    if (!window.confirm("Delete this equipment?")) return;
    try {
      setBusy(true);
      await api.deleteEquipment(equipmentId);
      setStatus("Deleted.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete equipment.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteLabRow(labId: string) {
    if (!window.confirm("Delete this lab?")) return;
    try {
      setBusy(true);
      await api.deleteLab(labId);
      setStatus("Deleted.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete lab.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteLabClosureRow(closureId: string) {
    if (!window.confirm("Delete this lab closure?")) return;
    try {
      setBusy(true);
      await api.deleteLabClosure(closureId);
      setStatus("Deleted.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete lab closure.");
    } finally {
      setBusy(false);
    }
  }

  async function approveBooking(bookingId: string) {
    try {
      setBusy(true);
      await api.approveEquipmentBooking(bookingId);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve booking.");
    } finally {
      setBusy(false);
    }
  }

  async function rejectBooking(bookingId: string) {
    try {
      setBusy(true);
      await api.rejectEquipmentBooking(bookingId);
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject booking.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelBooking(bookingId: string) {
    try {
      setBusy(true);
      await api.updateEquipmentBooking(bookingId, { status: "cancelled" });
      setStatus("Saved.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel booking.");
    } finally {
      setBusy(false);
    }
  }

  function openBookingFromSlot(day: Date, hour: number) {
    resetForms();
    setModal("booking");
    setBookingEquipmentId(selectedEquipmentId || "");
    setBookingStartAt(toDateTimeInput(new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0, 0).toISOString()));
    setBookingEndAt(toDateTimeInput(new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour + 1, 0, 0).toISOString()));
  }

  function openBookingFromLabCell(equipId: string, day: Date) {
    resetForms();
    setModal("booking");
    setBookingEquipmentId(equipId);
    setBookingStartAt(toDateTimeInput(new Date(day.getFullYear(), day.getMonth(), day.getDate(), 9, 0, 0).toISOString()));
    setBookingEndAt(toDateTimeInput(new Date(day.getFullYear(), day.getMonth(), day.getDate(), 10, 0, 0).toISOString()));
  }

  function switchToBookingsFiltered() {
    if (selectedEquipmentId) setEquipmentFilterId(selectedEquipmentId);
    setTab("bookings");
  }

  const weekStartLabel = weekDays[0]?.toLocaleDateString([], { day: "2-digit", month: "short" }) || "";
  const weekEndLabel = weekDays[weekDays.length - 1]?.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) || "";
  const weekLabel = `${weekStartLabel} - ${weekEndLabel}`;

  return (
    <div className="resources-workspace">
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          {tab === "labs" && selectedLab ? (
            <>
              <span>{selectedLab.name}</span>
              <span className="setup-summary-sep" />
              <span>{selectedLabEquipment.length} equipment</span>
              <span className="setup-summary-sep" />
              <span>{bookings.filter((b) => selectedLabEquipment.some((e) => e.id === b.equipment_id) && ["requested", "approved", "active"].includes(b.status)).length} bookings</span>
              <span className="setup-summary-sep" />
              <span>{selectedLabClosures.length} closures</span>
            </>
          ) : tab === "equipment" && selectedEquipment ? (
            <>
              <span>{selectedEquipment.name}</span>
              <span className="setup-summary-sep" />
              <span>{selectedEquipmentBookings.filter((b) => ["requested", "approved", "active"].includes(b.status)).length} bookings</span>
              <span className="setup-summary-sep" />
              <span>{selectedEquipmentConflicts.length} conflicts</span>
              <span className="setup-summary-sep" />
              <span>{selectedEquipmentDowntime.filter((d) => new Date(d.end_at) >= new Date()).length} downtime</span>
            </>
          ) : (
            <>
              <span>{labs.length} labs</span>
              <span className="setup-summary-sep" />
              <span>{equipment.length} equipment</span>
              <span className="setup-summary-sep" />
              <span>{activeBookings.length} active bookings</span>
              <span className="setup-summary-sep" />
              <span>{openConflicts} conflicts</span>
              <span className="setup-summary-sep" />
              <span>{activeDowntime} downtime</span>
            </>
          )}
        </div>
        <div className="resources-summary-actions">
          {tab === "equipment" && isSuperAdmin ? (
            <button type="button" className="meetings-new-btn" onClick={() => openEquipmentModal()}>
              <FontAwesomeIcon icon={faPlus} /> Add Equipment
            </button>
          ) : null}
          {tab === "labs" && isSuperAdmin ? (
            <>
              <button type="button" className="ghost icon-text-button" onClick={() => openLabClosureModal()}>
                <FontAwesomeIcon icon={faClockRotateLeft} /> Close Lab
              </button>
              <button type="button" className="meetings-new-btn" onClick={() => openLabModal()}>
                <FontAwesomeIcon icon={faPlus} /> Add Lab
              </button>
            </>
          ) : null}
          {tab === "bookings" ? (
            <button type="button" className="meetings-new-btn" onClick={() => openBookingModal()}>
              <FontAwesomeIcon icon={faCalendarPlus} /> Book
            </button>
          ) : null}
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success-message">{status}</p> : null}

      <div className="delivery-tabs">
        <button type="button" className={`delivery-tab ${tab === "labs" ? "active" : ""}`} onClick={() => setTab("labs")}>
          Labs <span className="delivery-tab-count">{labs.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "equipment" ? "active" : ""}`} onClick={() => setTab("equipment")}>
          Equipment <span className="delivery-tab-count">{equipment.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "bookings" ? "active" : ""}`} onClick={() => setTab("bookings")}>
          Bookings <span className="delivery-tab-count">{bookings.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "conflicts" ? "active" : ""}`} onClick={() => setTab("conflicts")}>
          Conflicts <span className="delivery-tab-count">{conflicts.length}</span>
        </button>
      </div>

      <div className="meetings-toolbar">
        <div className="meetings-filter-group">
          {tab === "equipment" ? (
            <>
              <select value={equipmentLabFilter} onChange={(event) => { setEquipmentLabFilter(event.target.value); setSelectedEquipmentId(""); }}>
                <option value="">All Labs</option>
                {labs.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
              <select value={selectedEquipmentId} onChange={(event) => setSelectedEquipmentId(event.target.value)}>
                {filteredEquipment.filter((item) => !equipmentLabFilter || item.lab_id === equipmentLabFilter).map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
                {filteredEquipment.filter((item) => !equipmentLabFilter || item.lab_id === equipmentLabFilter).length === 0 ? <option value="">No equipment</option> : null}
              </select>
              <input className="meetings-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" />
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">All Status</option>
                <option value="active">Active</option>
                <option value="maintenance">Maintenance</option>
                <option value="unavailable">Unavailable</option>
                <option value="retired">Retired</option>
              </select>
            </>
          ) : tab === "labs" ? (
            <select value={selectedLabId} onChange={(event) => setLabFilterId(event.target.value)}>
              <option value="">Select Lab</option>
              {labs.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          ) : tab === "bookings" ? (
            <>
              <select value={equipmentFilterId} onChange={(event) => setEquipmentFilterId(event.target.value)}>
                <option value="">All Equipment</option>
                {equipment.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
              <select value={bookingStatusFilter} onChange={(event) => setBookingStatusFilter(event.target.value)}>
                <option value="">All Status</option>
                <option value="requested">Requested</option>
                <option value="approved">Approved</option>
                <option value="active">Active</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
                <option value="rejected">Rejected</option>
              </select>
              <select value={bookingDateRange} onChange={(event) => setBookingDateRange(event.target.value)}>
                <option value="week">This Week</option>
                <option value="month">This Month</option>
                <option value="all">All Time</option>
              </select>
            </>
          ) : (
            <select value={equipmentFilterId} onChange={(event) => setEquipmentFilterId(event.target.value)}>
              <option value="">All Equipment</option>
              {equipment.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {loading ? <div className="card">Loading...</div> : null}

      {!loading && tab === "equipment" && equipment.length === 0 ? (
        <div className="teaching-empty-state">
          <p>No equipment registered yet.</p>
          {isSuperAdmin ? (
            <button type="button" className="meetings-new-btn" onClick={() => openEquipmentModal()}>
              <FontAwesomeIcon icon={faPlus} /> Add First Equipment
            </button>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>Ask an admin to add equipment.</p>
          )}
        </div>
      ) : null}

      {!loading && tab === "equipment" && selectedEquipment ? (
        <div className="card resources-card">
          <div className="resources-schedule-shell">
            <div className="resources-schedule-topbar">
              <div className="setup-summary-stats resources-equip-stats">
                <span>{selectedEquipment.location || "No location"}</span>
                <span className="setup-summary-sep" />
                <span>{selectedEquipment.lab?.name || "No lab"}</span>
                <span>{selectedEquipment.owner?.display_name || "No owner"}</span>
                <span className="setup-summary-sep" />
                <span className="chip small">{selectedEquipment.status}</span>
                <span className="setup-summary-sep" />
                <span className="chip small">{selectedEquipment.usage_mode}</span>
                <span className="setup-summary-sep" />
                <span>Next free: <strong>{nextFreeSlotLabel}</strong></span>
                {selectedEquipmentConflicts.length > 0 ? (
                  <>
                    <span className="setup-summary-sep" />
                    <span className="danger-text">{selectedEquipmentConflicts.length} conflicts</span>
                  </>
                ) : null}
              </div>
              <div className="resources-card-actions">
                <button type="button" className="ghost icon-text-button small" onClick={() => openDowntimeModal(selectedEquipment)}>
                  <FontAwesomeIcon icon={faClockRotateLeft} /> Downtime
                </button>
                {isSuperAdmin ? (
                  <>
                    <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openEquipmentModal(selectedEquipment)}>
                      <FontAwesomeIcon icon={faPenToSquare} />
                    </button>
                    <button type="button" className="ghost docs-action-btn danger-text" title="Delete" onClick={() => void deleteEquipmentRow(selectedEquipment.id)}>
                      <FontAwesomeIcon icon={faTrash} />
                    </button>
                  </>
                ) : null}
              </div>
            </div>

            <div className="resources-schedule-toolbar">
              <div className="resources-calendar-nav">
                <button type="button" className="ghost icon-text-button small" onClick={() => setCalendarWeekStart((current) => addDays(current, -7))}>
                  Prev
                </button>
                <span className="resources-week-label">{weekLabel}</span>
                <button type="button" className="ghost icon-text-button small" onClick={() => setCalendarWeekStart((current) => addDays(current, 7))}>
                  Next
                </button>
                <button type="button" className="ghost icon-text-button small" onClick={() => setCalendarWeekStart(startOfWeek(new Date()))}>
                  Today
                </button>
                <button type="button" className={`ghost icon-text-button small ${showWeekends ? "active" : ""}`} onClick={() => setShowWeekends((v) => !v)}>
                  {showWeekends ? "Mon–Sun" : "Mon–Fri"}
                </button>
              </div>
              <div className="resources-card-actions">
                <button type="button" className="meetings-new-btn" onClick={() => openBookingModal()}>
                  <FontAwesomeIcon icon={faCalendarPlus} /> Book
                </button>
              </div>
            </div>
          </div>

          <div className="resources-schedule-legend">
            <span><span className="resources-legend-dot approved" /> Approved</span>
            <span><span className="resources-legend-dot requested" /> Requested</span>
            <span><span className="resources-legend-dot downtime" /> Downtime</span>
          </div>

          <div className="resources-schedule-grid-wrap">
            <div className="resources-schedule-grid">
              <div className="resources-schedule-time-col">
                <div className="resources-schedule-corner" />
                {scheduleHours.map((hour) => (
                  <div key={hour} className="resources-schedule-time-cell">
                    {String(hour).padStart(2, "0")}:00
                  </div>
                ))}
              </div>
              {weekDays.map((day) => (
                <div key={day.toISOString()} className="resources-schedule-day-col">
                  <div className={`resources-schedule-day-head ${sameDay(day, new Date()) ? "today" : ""}`}>
                    <strong>{day.toLocaleDateString([], { weekday: "short" })}</strong>
                    <span>{day.toLocaleDateString([], { day: "2-digit", month: "short" })}</span>
                  </div>
                  <div className="resources-schedule-day-body">
                    {scheduleHours.map((hour) => (
                      <button
                        key={`${day.toISOString()}-${hour}`}
                        type="button"
                        className="resources-schedule-slot"
                        onClick={() => openBookingFromSlot(day, hour)}
                        title={`Book ${selectedEquipment.name} at ${String(hour).padStart(2, "0")}:00`}
                      />
                    ))}
                    {selectedEquipmentDowntime
                      .filter((item) => {
                        const itemStart = new Date(item.start_at);
                        const itemEnd = new Date(item.end_at);
                        const dayStart = new Date(day);
                        dayStart.setHours(SCHEDULE_START_HOUR, 0, 0, 0);
                        const dayEnd = new Date(day);
                        dayEnd.setHours(SCHEDULE_END_HOUR, 0, 0, 0);
                        return itemStart < dayEnd && itemEnd > dayStart;
                      })
                      .map((item) => {
                        const itemStart = new Date(item.start_at);
                        const itemEnd = new Date(item.end_at);
                        const topHours = Math.max(SCHEDULE_START_HOUR, itemStart.getHours() + itemStart.getMinutes() / 60) - SCHEDULE_START_HOUR;
                        const bottomHours = Math.min(SCHEDULE_END_HOUR, itemEnd.getHours() + itemEnd.getMinutes() / 60) - SCHEDULE_START_HOUR;
                        return (
                          <div
                            key={item.id}
                            className="resources-schedule-block downtime"
                            style={{ top: `${topHours * 42}px`, height: `${Math.max(20, (bottomHours - topHours) * 42)}px` }}
                            title={`${item.reason}: ${formatRange(item.start_at, item.end_at)}`}
                          >
                            <strong>{item.reason}</strong>
                          </div>
                        );
                      })}
                    {selectedEquipmentBookings
                      .filter((item) => {
                        const itemStart = new Date(item.start_at);
                        const itemEnd = new Date(item.end_at);
                        const dayStart = new Date(day);
                        dayStart.setHours(SCHEDULE_START_HOUR, 0, 0, 0);
                        const dayEnd = new Date(day);
                        dayEnd.setHours(SCHEDULE_END_HOUR, 0, 0, 0);
                        return itemStart < dayEnd && itemEnd > dayStart;
                      })
                      .map((item) => {
                        const itemStart = new Date(item.start_at);
                        const itemEnd = new Date(item.end_at);
                        const topHours = Math.max(SCHEDULE_START_HOUR, itemStart.getHours() + itemStart.getMinutes() / 60) - SCHEDULE_START_HOUR;
                        const bottomHours = Math.min(SCHEDULE_END_HOUR, itemEnd.getHours() + itemEnd.getMinutes() / 60) - SCHEDULE_START_HOUR;
                        const project = projectMap.get(item.project_id);
                        return (
                          <button
                            key={item.id}
                            type="button"
                            className={`resources-schedule-block ${item.status === "requested" ? "requested" : item.status === "cancelled" ? "cancelled" : "approved"}`}
                            style={{ top: `${topHours * 42}px`, height: `${Math.max(20, (bottomHours - topHours) * 42)}px` }}
                            title={`${project?.code || item.project_id}: ${item.status}`}
                            onClick={() => openBookingModal(item)}
                          >
                            <strong>{project?.code || item.project_id.slice(0, 8)}</strong>
                            <span>{item.status}</span>
                          </button>
                        );
                      })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="resources-schedule-footer">
            <div className="resources-footer-head">
              <strong>Upcoming</strong>
              {selectedEquipmentBookings.length > 4 ? (
                <button type="button" className="ghost icon-text-button small" onClick={switchToBookingsFiltered}>
                  View all <FontAwesomeIcon icon={faArrowRight} />
                </button>
              ) : null}
            </div>
            <div className="resources-upcoming-strip">
              {selectedEquipmentUpcomingBookings.map((item) => {
                const project = projectMap.get(item.project_id);
                return (
                  <button key={item.id} type="button" className="resources-upcoming-row" onClick={() => openBookingModal(item)}>
                    <strong>{project?.code || item.project_id.slice(0, 8)}</strong>
                    <span>{formatRange(item.start_at, item.end_at)}</span>
                  </button>
                );
              })}
              {selectedEquipmentUpcomingBookings.length === 0 ? <span className="resources-empty compact">No upcoming bookings</span> : null}
            </div>
          </div>
        </div>
      ) : null}

      {!loading && tab === "labs" && labs.length === 0 ? (
        <div className="teaching-empty-state">
          <p>No labs registered yet.</p>
          {isSuperAdmin ? (
            <button type="button" className="meetings-new-btn" onClick={() => openLabModal()}>
              <FontAwesomeIcon icon={faPlus} /> Add First Lab
            </button>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>Ask an admin to add labs.</p>
          )}
        </div>
      ) : null}

      {!loading && tab === "labs" && labs.length > 0 ? (
        <div className="resources-labs-layout">
          {selectedLab ? (
            <div className="card resources-card">
              <div className="resources-schedule-shell">
                <div className="resources-schedule-topbar">
                  <div className="setup-summary-stats resources-equip-stats">
                    <span>{[selectedLab.building, selectedLab.room].filter(Boolean).join(" · ") || "No room"}</span>
                    <span className="setup-summary-sep" />
                    <span>{selectedLab.responsible?.display_name || "No responsible"}</span>
                  </div>
                  <div className="resources-card-actions">
                    <button type="button" className="ghost icon-text-button small" onClick={() => setCalendarWeekStart((current) => addDays(current, -7))}>
                      Prev
                    </button>
                    <span className="resources-week-label">{weekLabel}</span>
                    <button type="button" className="ghost icon-text-button small" onClick={() => setCalendarWeekStart((current) => addDays(current, 7))}>
                      Next
                    </button>
                    <button type="button" className="ghost icon-text-button small" onClick={() => setCalendarWeekStart(startOfWeek(new Date()))}>
                      Today
                    </button>
                    <button type="button" className={`ghost icon-text-button small ${showWeekends ? "active" : ""}`} onClick={() => setShowWeekends((v) => !v)}>
                      {showWeekends ? "Mon–Sun" : "Mon–Fri"}
                    </button>
                  </div>
                </div>
              </div>
              <div className="resources-schedule-legend">
                <span><span className="resources-legend-dot approved" /> Booking</span>
                <span><span className="resources-legend-dot requested" /> Request</span>
                <span><span className="resources-legend-dot downtime" /> Closure</span>
              </div>
              <div className="resources-lab-calendar-wrap">
                <div className="resources-lab-calendar" style={{ gridTemplateColumns: `220px repeat(${weekDays.length}, minmax(120px, 1fr))` }}>
                  <div className="resources-lab-calendar-head resources-lab-calendar-equipment">Equipment</div>
                  {weekDays.map((day) => (
                    <div key={day.toISOString()} className={`resources-lab-calendar-head ${sameDay(day, new Date()) ? "today" : ""}`}>
                      <strong>{day.toLocaleDateString([], { weekday: "short" })}</strong>
                      <span>{day.toLocaleDateString([], { day: "2-digit", month: "short" })}</span>
                    </div>
                  ))}
                  {selectedLabEquipment.map((item) => (
                    <Fragment key={item.id}>
                      <div key={`${item.id}-name`} className="resources-lab-calendar-equipment resources-lab-calendar-rowhead">
                        <strong>{item.name}</strong>
                        <span>{item.category || item.model || item.status}</span>
                      </div>
                      {weekDays.map((day) => {
                        const dayStart = new Date(day);
                        dayStart.setHours(0, 0, 0, 0);
                        const dayEnd = addDays(dayStart, 1);
                        const dayBookings = bookings
                          .filter((entry) => entry.equipment_id === item.id && entry.status !== "cancelled" && overlaps(new Date(entry.start_at), new Date(entry.end_at), dayStart, dayEnd))
                          .sort((left, right) => new Date(left.start_at).getTime() - new Date(right.start_at).getTime());
                        const dayClosures = selectedLabClosures.filter((entry) => overlaps(new Date(entry.start_at), new Date(entry.end_at), dayStart, dayEnd));
                        return (
                          <div key={`${item.id}-${day.toISOString()}`} className="resources-lab-calendar-cell" role="button" tabIndex={0} onClick={() => openBookingFromLabCell(item.id, day)} title={`Book ${item.name}`}>
                            {dayClosures.map((entry) => (
                              <div key={entry.id} className="resources-lab-pill downtime" title={`${entry.reason}: ${formatRange(entry.start_at, entry.end_at)}`}>
                                <strong>{entry.reason}</strong>
                                <span>{formatDayTimeRange(entry.start_at, entry.end_at)}</span>
                              </div>
                            ))}
                            {dayBookings.map((entry) => {
                              const project = projectMap.get(entry.project_id);
                              return (
                                <button
                                  key={entry.id}
                                  type="button"
                                  className={`resources-lab-pill ${entry.status === "requested" ? "requested" : "approved"}`}
                                  onClick={() => openBookingModal(entry)}
                                  title={`${project?.code || entry.project_id}: ${formatRange(entry.start_at, entry.end_at)}`}
                                >
                                  <strong>{project?.code || entry.project_id.slice(0, 8)}</strong>
                                  <span>{formatDayTimeRange(entry.start_at, entry.end_at)}</span>
                                </button>
                              );
                            })}
                          </div>
                        );
                      })}
                    </Fragment>
                  ))}
                </div>
                {selectedLabEquipment.length === 0 ? <div className="resources-empty">No equipment assigned to this lab.</div> : null}
              </div>
            </div>
          ) : null}
          <div className="card resources-card resources-labs-tables">
            <div className="resources-footer-head">
              <strong>Labs</strong>
            </div>
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Lab</th>
                    <th>Responsible</th>
                    <th>Equipment</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {labs.map((item) => (
                    <tr key={item.id} className={item.id === selectedLabId ? "row-selected" : ""}>
                      <td>
                        <strong>{item.name}</strong>
                        <div className="resources-subline">{[item.building, item.room].filter(Boolean).join(" · ") || "-"}</div>
                      </td>
                      <td>{item.responsible?.display_name || "-"}</td>
                      <td>{item.equipment_count}</td>
                      <td className="teaching-row-actions">
                        {isSuperAdmin ? (
                          <>
                            <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openLabModal(item)}>
                              <FontAwesomeIcon icon={faPenToSquare} />
                            </button>
                            <button type="button" className="ghost docs-action-btn danger-text" title="Delete" onClick={() => void deleteLabRow(item.id)}>
                              <FontAwesomeIcon icon={faTrash} />
                            </button>
                            <button type="button" className="ghost icon-text-button small" onClick={() => openLabClosureModal(item)}>
                              Close
                            </button>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                  {labs.length === 0 ? <tr><td colSpan={4}>No labs</td></tr> : null}
                </tbody>
              </table>
            </div>
            {selectedLabClosures.length > 0 || isSuperAdmin ? (
              <>
                <div className="resources-footer-head" style={{ marginTop: 8 }}>
                  <strong>Closures</strong>
                  <span className="delivery-tab-count">{selectedLabClosures.length}</span>
                </div>
                <div className="simple-table-wrap">
                  <table className="simple-table compact-table">
                    <thead>
                      <tr>
                        <th>Lab</th>
                        <th>Window</th>
                        <th>Reason</th>
                        <th>Cancelled</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {selectedLabClosures.map((item) => (
                        <tr key={item.id}>
                          <td><strong>{item.lab.name}</strong></td>
                          <td>{formatRange(item.start_at, item.end_at)}</td>
                          <td>{item.reason}</td>
                          <td>{item.cancelled_booking_count}</td>
                          <td className="teaching-row-actions">
                            {isSuperAdmin ? (
                              <>
                                <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openLabClosureModal(item)}>
                                  <FontAwesomeIcon icon={faPenToSquare} />
                                </button>
                                <button type="button" className="ghost docs-action-btn danger-text" title="Delete" onClick={() => void deleteLabClosureRow(item.id)}>
                                  <FontAwesomeIcon icon={faTrash} />
                                </button>
                              </>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                      {selectedLabClosures.length === 0 ? (
                        <tr><td colSpan={5}>No closures</td></tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      {!loading && tab === "bookings" ? (
        <div className="card resources-card">
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Equipment</th>
                  <th>Project</th>
                  <th>Window</th>
                  <th>Status</th>
                  <th>Requester</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredBookings.map((item) => (
                  <tr key={item.id} className={item.status === "cancelled" ? "resources-row-muted" : ""}>
                    <td><strong>{item.equipment.name}</strong></td>
                    <td>
                      <button type="button" className="ghost resources-link-btn" onClick={() => onOpenProject(item.project_id)}>
                        {projectMap.get(item.project_id)?.code || item.project_id.slice(0, 8)}
                        <FontAwesomeIcon icon={faArrowRight} />
                      </button>
                    </td>
                    <td>{formatRange(item.start_at, item.end_at)}</td>
                    <td><span className="chip small">{item.status}</span></td>
                    <td>{item.requester?.display_name || "-"}</td>
                    <td className="teaching-row-actions">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openBookingModal(item)}>
                        <FontAwesomeIcon icon={faPenToSquare} />
                      </button>
                      {item.status === "requested" || item.status === "approved" ? (
                        <button type="button" className="ghost icon-text-button small danger-text" onClick={() => void cancelBooking(item.id)}>
                          Cancel
                        </button>
                      ) : null}
                      {item.status === "requested" ? (
                        <>
                          <button type="button" className="ghost icon-text-button small" onClick={() => void approveBooking(item.id)}>Approve</button>
                          <button type="button" className="ghost icon-text-button small danger-text" onClick={() => void rejectBooking(item.id)}>Reject</button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {filteredBookings.length === 0 ? <tr><td colSpan={6}>No bookings</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {!loading && tab === "conflicts" ? (
        <div className="card resources-card">
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Equipment</th>
                  <th>Type</th>
                  <th>Projects</th>
                  <th>Detail</th>
                  <th>Window</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {conflicts.map((item, index) => (
                  <tr key={`${item.booking_id || item.downtime_id || index}`}>
                    <td><strong>{item.equipment_name}</strong></td>
                    <td><span className="chip small">{item.conflict_type}</span></td>
                    <td className="resources-conflict-projects">
                      {item.project_id ? <button type="button" className="ghost resources-link-btn" onClick={() => onOpenProject(item.project_id!)}>{projectMap.get(item.project_id)?.code || item.project_id.slice(0, 8)}</button> : null}
                      {item.conflicting_project_id ? <button type="button" className="ghost resources-link-btn" onClick={() => onOpenProject(item.conflicting_project_id!)}>{projectMap.get(item.conflicting_project_id)?.code || item.conflicting_project_id.slice(0, 8)}</button> : null}
                    </td>
                    <td><FontAwesomeIcon icon={faTriangleExclamation} className="resources-conflict-icon" /> {item.detail}</td>
                    <td className="resources-conflict-window">{formatRange(item.start_at, item.end_at)}</td>
                    <td className="teaching-row-actions">
                      {item.booking_id ? (
                        <button type="button" className="ghost icon-text-button small danger-text" onClick={() => void cancelBooking(item.booking_id!)}>
                          Cancel
                        </button>
                      ) : null}
                      {item.conflicting_booking_id ? (
                        <button type="button" className="ghost icon-text-button small danger-text" onClick={() => void cancelBooking(item.conflicting_booking_id!)}>
                          Cancel other
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {conflicts.length === 0 ? <tr><td colSpan={6}>No conflicts</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {modal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className={`modal-card ${modal === "equipment" || modal === "booking" ? "settings-modal-card" : ""}`}>
            <div className="modal-head">
              <h3>
                {modal === "equipment" ? (editingId ? "Edit Equipment" : "Add Equipment")
                  : modal === "lab" ? (editingId ? "Edit Lab" : "Add Lab")
                  : modal === "booking" ? (editingId ? "Edit Booking" : "Add Booking")
                  : modal === "lab-closure" ? (editingId ? "Edit Lab Closure" : "Close Lab")
                  : "Add Downtime"}
              </h3>
              <div className="modal-head-actions">
                <button
                  type="button"
                  className="meetings-new-btn"
                  disabled={busy}
                  onClick={() => void (modal === "equipment" ? saveEquipment() : modal === "lab" ? saveLab() : modal === "booking" ? saveBooking() : modal === "lab-closure" ? saveLabClosure() : saveDowntime())}
                >
                  {busy ? "Saving..." : "Save"}
                </button>
                <button type="button" className="ghost docs-action-btn" onClick={() => setModal(null)} title="Close">
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>

            {modal === "equipment" ? (
              <div className="form-grid">
                <label>
                  Name
                  <input value={equipmentName} onChange={(event) => setEquipmentName(event.target.value)} />
                </label>
                <label>
                  Category
                  <input value={equipmentCategory} onChange={(event) => setEquipmentCategory(event.target.value)} />
                </label>
                <label>
                  Model
                  <input value={equipmentModel} onChange={(event) => setEquipmentModel(event.target.value)} />
                </label>
                <label>
                  Serial Number
                  <input value={equipmentSerialNumber} onChange={(event) => setEquipmentSerialNumber(event.target.value)} />
                </label>
                <label>
                  Lab
                  <select value={equipmentLabId} onChange={(event) => setEquipmentLabId(event.target.value)}>
                    <option value="">Unassigned</option>
                    {labs.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Owner
                  <select value={equipmentOwnerUserId} onChange={(event) => setEquipmentOwnerUserId(event.target.value)}>
                    <option value="">Unassigned</option>
                    {users.map((item) => (
                      <option key={item.id} value={item.id}>{item.display_name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Status
                  <select value={equipmentStatus} onChange={(event) => setEquipmentStatus(event.target.value)}>
                    <option value="active">Active</option>
                    <option value="maintenance">Maintenance</option>
                    <option value="unavailable">Unavailable</option>
                    <option value="retired">Retired</option>
                  </select>
                </label>
                <label>
                  Mode
                  <select value={equipmentUsageMode} onChange={(event) => setEquipmentUsageMode(event.target.value)}>
                    <option value="exclusive">Exclusive</option>
                    <option value="shared">Shared</option>
                  </select>
                </label>
                <label className="full-span">
                  Description
                  <textarea rows={3} value={equipmentDescription} onChange={(event) => setEquipmentDescription(event.target.value)} />
                </label>
                <label className="full-span">
                  Access Notes
                  <textarea rows={3} value={equipmentAccessNotes} onChange={(event) => setEquipmentAccessNotes(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "lab" ? (
              <div className="form-grid">
                <label>
                  Name
                  <input value={labName} onChange={(event) => setLabName(event.target.value)} />
                </label>
                <label>
                  Building
                  <input value={labBuilding} onChange={(event) => setLabBuilding(event.target.value)} />
                </label>
                <label>
                  Room
                  <input value={labRoom} onChange={(event) => setLabRoom(event.target.value)} />
                </label>
                <label>
                  Responsible
                  <select value={labResponsibleUserId} onChange={(event) => setLabResponsibleUserId(event.target.value)}>
                    <option value="">Unassigned</option>
                    {users.map((item) => (
                      <option key={item.id} value={item.id}>{item.display_name}</option>
                    ))}
                  </select>
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={3} value={labNotes} onChange={(event) => setLabNotes(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "booking" ? (
              <div className="form-grid">
                <label>
                  Equipment
                  <select value={bookingEquipmentId} onChange={(event) => setBookingEquipmentId(event.target.value)} disabled={Boolean(editingId) || Boolean(selectedEquipmentId)}>
                    <option value="">Select</option>
                    {equipment.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Project
                  <select value={bookingProjectId} onChange={(event) => setBookingProjectId(event.target.value)} disabled={Boolean(editingId)}>
                    <option value="">Select</option>
                    {projects.map((item) => (
                      <option key={item.id} value={item.id}>{item.code} · {item.title}</option>
                    ))}
                  </select>
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
                  Purpose
                  <input value={bookingPurpose} onChange={(event) => setBookingPurpose(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={3} value={bookingNotes} onChange={(event) => setBookingNotes(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "downtime" ? (
              <div className="form-grid">
                <label>
                  Equipment
                  <select value={downtimeEquipmentId} onChange={(event) => setDowntimeEquipmentId(event.target.value)}>
                    <option value="">Select</option>
                    {equipment.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Reason
                  <select value={downtimeReason} onChange={(event) => setDowntimeReason(event.target.value)}>
                    <option value="maintenance">Maintenance</option>
                    <option value="repair">Repair</option>
                    <option value="unavailable">Unavailable</option>
                  </select>
                </label>
                <label>
                  Start
                  <input type="datetime-local" value={downtimeStartAt} onChange={(event) => setDowntimeStartAt(event.target.value)} />
                </label>
                <label>
                  End
                  <input type="datetime-local" value={downtimeEndAt} onChange={(event) => setDowntimeEndAt(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={3} value={downtimeNotes} onChange={(event) => setDowntimeNotes(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "lab-closure" ? (
              <div className="form-grid">
                <label>
                  Lab
                  <select value={closureLabId} onChange={(event) => setClosureLabId(event.target.value)}>
                    <option value="">Select</option>
                    {labs.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Reason
                  <select value={closureReason} onChange={(event) => setClosureReason(event.target.value)}>
                    <option value="personnel_unavailable">Personnel Unavailable</option>
                    <option value="safety">Safety</option>
                    <option value="maintenance">Maintenance</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <label>
                  Start
                  <input type="datetime-local" value={closureStartAt} onChange={(event) => setClosureStartAt(event.target.value)} />
                </label>
                <label>
                  End
                  <input type="datetime-local" value={closureEndAt} onChange={(event) => setClosureEndAt(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={3} value={closureNotes} onChange={(event) => setClosureNotes(event.target.value)} />
                </label>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
