import { useEffect, useMemo, useRef, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCalendarDay,
  faDownload,
  faFileLines,
  faMicrophone,
  faPlus,
  faRobot,
  faChevronDown,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type { CalendarImportBatch, CalendarIntegration, DocumentListItem, MeetingActionItem, MeetingRecord, Member, WorkEntity } from "../types";

type Props = {
  selectedProjectId: string;
  onOpenAssistant: (prompt: string) => void;
  highlightMeetingId?: string | null;
  onHighlightConsumed?: () => void;
};

export function MeetingsHub({ selectedProjectId, onOpenAssistant, highlightMeetingId, onHighlightConsumed }: Props) {
  const [meetings, setMeetings] = useState<MeetingRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [workPackages, setWorkPackages] = useState<WorkEntity[]>([]);
  const [actionItems, setActionItems] = useState<MeetingActionItem[]>([]);
  const [calendarIntegrations, setCalendarIntegrations] = useState<CalendarIntegration[]>([]);
  const [calendarImports, setCalendarImports] = useState<CalendarImportBatch[]>([]);
  const [sourceFilter, setSourceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingMeetingId, setEditingMeetingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [sourceType, setSourceType] = useState("minutes");
  const [sourceUrl, setSourceUrl] = useState("");
  const [participantsText, setParticipantsText] = useState("");
  const [contentText, setContentText] = useState("");
  const [linkedDocumentId, setLinkedDocumentId] = useState("");
  const [createdByMemberId, setCreatedByMemberId] = useState("");
  const [transcriptFile, setTranscriptFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [showActionForm, setShowActionForm] = useState(false);
  const [newActionDescription, setNewActionDescription] = useState("");
  const [newActionAssigneeMemberId, setNewActionAssigneeMemberId] = useState("");
  const [newActionDueDate, setNewActionDueDate] = useState("");
  const [newActionPriority, setNewActionPriority] = useState("normal");
  const [promoteItemId, setPromoteItemId] = useState<string | null>(null);
  const [promoteWpId, setPromoteWpId] = useState("");
  const icsInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!selectedProjectId) {
      setMeetings([]);
      setDocuments([]);
      setMembers([]);
      setWorkPackages([]);
      setActionItems([]);
      return;
    }
    void loadData();
  }, [selectedProjectId, sourceFilter, search]);

  const activeMeeting = selectedMeetingId
    ? meetings.find((m) => m.id === selectedMeetingId) ?? null
    : meetings[0] ?? null;

  useAutoRefresh(() => { void loadData(); });

  useEffect(() => {
    if (highlightMeetingId && meetings.length > 0) {
      setSelectedMeetingId(highlightMeetingId);
      onHighlightConsumed?.();
    }
  }, [highlightMeetingId, meetings.length]);

  useEffect(() => {
    if (!selectedProjectId || !activeMeeting?.id) {
      setActionItems([]);
      return;
    }
    void loadActionItems(activeMeeting.id);
  }, [selectedProjectId, activeMeeting?.id]);

  async function loadData(preferredMeetingId?: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const [meetingsRes, documentsRes, membersRes, workPackagesRes, integrationsRes, importsRes] = await Promise.all([
        api.listMeetings(selectedProjectId, { search: search || undefined, source_type: sourceFilter || undefined }),
        api.listDocuments(selectedProjectId),
        api.listMembers(selectedProjectId),
        api.listWorkPackages(selectedProjectId),
        api.listCalendarIntegrations(selectedProjectId),
        api.listCalendarImports(selectedProjectId),
      ]);
      setMeetings(meetingsRes.items);
      setDocuments(documentsRes.items);
      setMembers(membersRes.items);
      setWorkPackages(workPackagesRes.items);
      setCalendarIntegrations(integrationsRes.items);
      setCalendarImports(importsRes.items);
      setSelectedMeetingId((prev) => {
        if (!meetingsRes.items.length) return null;
        if (preferredMeetingId && meetingsRes.items.some((item) => item.id === preferredMeetingId)) return preferredMeetingId;
        if (prev && meetingsRes.items.some((item) => item.id === prev)) return prev;
        return meetingsRes.items[0].id;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load meetings.");
    } finally {
      setBusy(false);
    }
  }

  async function loadActionItems(meetingId: string) {
    if (!selectedProjectId) return;
    try {
      setActionBusy(true);
      const response = await api.listActionItems(selectedProjectId, meetingId);
      setActionItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load action items.");
    } finally {
      setActionBusy(false);
    }
  }

  function resetForm() {
    setEditingMeetingId(null);
    setTitle("");
    setStartsAt("");
    setSourceType("minutes");
    setSourceUrl("");
    setParticipantsText("");
    setContentText("");
    setLinkedDocumentId("");
    setCreatedByMemberId("");
    setTranscriptFile(null);
  }

  function resetActionForm() {
    setShowActionForm(false);
    setNewActionDescription("");
    setNewActionAssigneeMemberId("");
    setNewActionDueDate("");
    setNewActionPriority("normal");
  }

  function openNewMeeting() {
    resetForm();
    setModalOpen(true);
  }

  function openEditMeeting(meeting: MeetingRecord) {
    setEditingMeetingId(meeting.id);
    setTitle(meeting.title);
    setStartsAt(meeting.starts_at.slice(0, 16));
    setSourceType(meeting.source_type);
    setSourceUrl(meeting.source_url || "");
    setParticipantsText(meeting.participants.join(", "));
    setContentText(meeting.content_text);
    setLinkedDocumentId(meeting.linked_document_id || "");
    setCreatedByMemberId(meeting.created_by_member_id || "");
    setModalOpen(true);
  }

  async function handleSave() {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      let saved: MeetingRecord;

      if (transcriptFile && !editingMeetingId) {
        // Upload with file
        const formData = new FormData();
        formData.append("file", transcriptFile);
        formData.append("title", title);
        formData.append("starts_at", new Date(startsAt).toISOString());
        formData.append("source_type", sourceType);
        formData.append("participants", participantsText);
        if (createdByMemberId) formData.append("created_by_member_id", createdByMemberId);
        saved = await api.uploadMeetingTranscript(selectedProjectId, formData);
      } else {
        const payload = {
          title,
          starts_at: new Date(startsAt).toISOString(),
          source_type: sourceType,
          source_url: sourceUrl || undefined,
          participants: participantsText.split(",").map((item) => item.trim()).filter(Boolean),
          content_text: contentText,
          linked_document_id: linkedDocumentId || null,
          created_by_member_id: createdByMemberId || null,
        };
        saved = editingMeetingId
          ? await api.updateMeeting(selectedProjectId, editingMeetingId, payload)
          : await api.createMeeting(selectedProjectId, payload);
      }

      setModalOpen(false);
      resetForm();
      await loadData(saved.id);
      setStatus(`${saved.title} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save meeting.");
    } finally {
      setBusy(false);
    }
  }

  const sourceCounts = useMemo(
    () => ({
      minutes: meetings.filter((item) => item.source_type === "minutes").length,
      transcript: meetings.filter((item) => item.source_type === "transcript").length,
    }),
    [meetings]
  );

  async function handleToggleActionStatus(item: MeetingActionItem) {
    if (!selectedProjectId || !activeMeeting) return;
    try {
      setActionBusy(true);
      const nextStatus = item.status === "done" ? "pending" : "done";
      const updated = await api.updateActionItem(selectedProjectId, activeMeeting.id, item.id, { status: nextStatus });
      setActionItems((prev) => prev.map((entry) => (entry.id === updated.id ? updated : entry)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update action item.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleCreateActionItem() {
    if (!selectedProjectId || !activeMeeting || !newActionDescription.trim()) return;
    try {
      setActionBusy(true);
      const created = await api.createActionItem(selectedProjectId, activeMeeting.id, {
        description: newActionDescription.trim(),
        assignee_member_id: newActionAssigneeMemberId || null,
        assignee_name: null,
        due_date: newActionDueDate || null,
        priority: newActionPriority,
        source: "manual",
      });
      setActionItems((prev) => [...prev, created].sort((a, b) => a.sort_order - b.sort_order));
      resetActionForm();
      setStatus("Action item added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create action item.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleExtractActions() {
    if (!selectedProjectId || !activeMeeting) return;
    try {
      setActionBusy(true);
      setError("");
      const extracted = await api.extractMeetingActions(selectedProjectId, activeMeeting.id);
      setActionItems(extracted.items);
      setMeetings((prev) =>
        prev.map((meeting) =>
          meeting.id === activeMeeting.id ? { ...meeting, summary: extracted.summary } : meeting
        )
      );
      setStatus("Action items refreshed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to extract action items.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handlePromoteActionItem() {
    if (!selectedProjectId || !activeMeeting || !promoteItemId || !promoteWpId) return;
    try {
      setActionBusy(true);
      const updated = await api.promoteActionItem(selectedProjectId, activeMeeting.id, promoteItemId, promoteWpId);
      setActionItems((prev) => prev.map((entry) => (entry.id === updated.id ? updated : entry)));
      setPromoteItemId(null);
      setPromoteWpId("");
      setStatus("Action item promoted to task.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to promote action item.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleConnectMicrosoft365() {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const response = await api.connectMicrosoft365Calendar(selectedProjectId);
      window.location.assign(response.auth_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Microsoft 365 connection.");
      setBusy(false);
    }
  }

  async function handleSyncMicrosoft365() {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const response = await api.syncMicrosoft365Calendar(selectedProjectId);
      await loadData();
      setStatus(`Outlook synced. ${response.imported} imported, ${response.updated} updated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sync Outlook calendar.");
    } finally {
      setBusy(false);
    }
  }

  async function handleIcsSelected(event: React.ChangeEvent<HTMLInputElement>) {
    if (!selectedProjectId) return;
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      setBusy(true);
      setError("");
      const formData = new FormData();
      formData.append("file", file);
      const response = await api.importIcsCalendar(selectedProjectId, formData);
      await loadData();
      setStatus(`.ics imported. ${response.imported} created, ${response.updated} updated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to import .ics calendar.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteMeeting() {
    if (!selectedProjectId || !activeMeeting) return;
    if (!window.confirm(`Delete meeting "${activeMeeting.title}"?`)) return;
    try {
      setBusy(true);
      setError("");
      const deletedMeetingId = activeMeeting.id;
      await api.deleteMeeting(selectedProjectId, deletedMeetingId);
      setModalOpen(false);
      resetForm();
      setActionItems([]);
      setSelectedMeetingId(null);
      await loadData();
      setStatus("Meeting deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete meeting.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteCalendarImport(batch: CalendarImportBatch) {
    if (!selectedProjectId) return;
    if (!window.confirm(`Remove imported calendar "${batch.filename}" and its meetings?`)) return;
    try {
      setBusy(true);
      setError("");
      await api.deleteCalendarImport(selectedProjectId, batch.id);
      setSelectedMeetingId(null);
      setActionItems([]);
      await loadData();
      setStatus(`Removed ${batch.filename}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove imported calendar.");
    } finally {
      setBusy(false);
    }
  }

  const microsoftIntegration = calendarIntegrations.find((item) => item.provider === "microsoft365") ?? null;

  if (!selectedProjectId) {
    return <section className="panel"><p className="muted-small">Select a project to start.</p></section>;
  }

  return (
    <section className="panel meetings-page">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span>{meetings.length} meetings</span>
          <span className="setup-summary-sep" />
          <span>{sourceCounts.minutes} minutes</span>
          <span className="setup-summary-sep" />
          <span>{sourceCounts.transcript} transcripts</span>
        </div>
        <button type="button" className="meetings-new-btn" onClick={openNewMeeting}>
          <FontAwesomeIcon icon={faPlus} /> New Meeting
        </button>
        <div className="meetings-calendar-actions">
          <button type="button" className="meetings-new-btn" disabled={busy} onClick={() => void handleConnectMicrosoft365()}>
            Connect Outlook
          </button>
          <button
            type="button"
            className="meetings-new-btn"
            disabled={busy || !microsoftIntegration || microsoftIntegration.sync_status === "disconnected"}
            onClick={() => void handleSyncMicrosoft365()}
          >
            Sync Outlook
          </button>
          <button type="button" className="meetings-new-btn" disabled={busy} onClick={() => icsInputRef.current?.click()}>
            Import .ics
          </button>
          <input
            ref={icsInputRef}
            type="file"
            accept=".ics,text/calendar"
            style={{ display: "none" }}
            onChange={(event) => void handleIcsSelected(event)}
          />
          {microsoftIntegration?.connected_account_email ? (
            <span className="chip small">{microsoftIntegration.connected_account_email}</span>
          ) : null}
        </div>
      </div>

      {/* Toolbar: filters */}
      <div className="meetings-toolbar">
        <div className="meetings-filter-group">
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
            <option value="">All sources</option>
            <option value="minutes">Minutes</option>
            <option value="transcript">Transcript</option>
          </select>
          <input
            className="meetings-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search meetings..."
          />
        </div>
      </div>
      {calendarImports.length ? (
        <div className="meetings-imports-panel">
          {calendarImports.map((item) => (
            <div key={item.id} className="meetings-import-row">
              <span className="chip small">{item.filename}</span>
              <span className="muted-small">{item.imported_count} created</span>
              <span className="muted-small">{item.updated_count} updated</span>
              <button type="button" className="ghost" disabled={busy} onClick={() => void handleDeleteCalendarImport(item)}>
                Remove
              </button>
            </div>
          ))}
        </div>
      ) : null}

      {/* Main content: single column */}
      <div className="meetings-list-section">
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th>Meeting</th>
                <th>Source</th>
                <th>Date</th>
                <th>Participants</th>
              </tr>
            </thead>
            <tbody>
              {meetings.map((item) => (
                <tr
                  key={item.id}
                  className={activeMeeting?.id === item.id ? "row-selected" : ""}
                  onClick={() => setSelectedMeetingId(item.id)}
                  onDoubleClick={() => openEditMeeting(item)}
                >
                  <td>
                    <span className={`meetings-source-icon ${item.source_type}`}>
                      <FontAwesomeIcon icon={item.source_type === "transcript" ? faMicrophone : faFileLines} />
                    </span>
                  </td>
                  <td><strong>{item.title}</strong></td>
                  <td><span className="chip small">{item.source_type}</span></td>
                  <td>{new Date(item.starts_at).toLocaleDateString()}</td>
                  <td>{item.participants.length}</td>
                </tr>
              ))}
              {meetings.length === 0 ? (
                <tr><td colSpan={5} className="empty-state-card">
                  No meetings yet.
                  <button type="button" className="ghost" onClick={openNewMeeting} style={{ marginTop: 8 }}>
                    <FontAwesomeIcon icon={faPlus} /> Create Meeting
                  </button>
                </td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {/* Meeting detail + assistant actions */}
      {activeMeeting ? (
        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <FontAwesomeIcon icon={faCalendarDay} className="meetings-detail-icon" />
              <div>
                <strong>{activeMeeting.title}</strong>
                <span className="meetings-detail-meta">
                  {new Date(activeMeeting.starts_at).toLocaleString()} · {activeMeeting.participants.length} participants · {activeMeeting.source_type}
                  {activeMeeting.original_filename ? ` · ${activeMeeting.original_filename}` : ""}
                </span>
                {activeMeeting.summary ? <p className="meetings-summary">{activeMeeting.summary}</p> : null}
                <span className={`chip small ${activeMeeting.indexing_status === "indexed" ? "status-ok" : ""}`}>
                  {activeMeeting.indexing_status}
                </span>
              </div>
            </div>
            <button
              type="button"
              className={`meetings-assistant-toggle ${assistantOpen ? "open" : ""}`}
              onClick={() => setAssistantOpen((prev) => !prev)}
            >
              <FontAwesomeIcon icon={faRobot} />
              <span>AI Actions</span>
              <FontAwesomeIcon icon={faChevronDown} className="meetings-toggle-chevron" />
            </button>
            <button
              type="button"
              className="ghost icon-text-button small"
              onClick={async () => {
                try {
                  const md = await api.getMeetingReport(selectedProjectId, activeMeeting.id);
                  const blob = new Blob([md], { type: "text/markdown" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `meeting-report-${activeMeeting.title.replace(/\s+/g, "-").slice(0, 40)}.md`;
                  a.click();
                  URL.revokeObjectURL(url);
                } catch { /* ignore */ }
              }}
            >
              <FontAwesomeIcon icon={faDownload} /> Export
            </button>
            <button type="button" className="ghost" disabled={busy} onClick={() => void handleDeleteMeeting()}>
              Delete
            </button>
          </div>

          {assistantOpen ? (
            <div className="meetings-assistant-bar">
              <button type="button" className="meetings-ai-btn" onClick={() => onOpenAssistant(`Summarize the meeting "${activeMeeting.title}" held on ${new Date(activeMeeting.starts_at).toLocaleDateString()}. Focus on decisions, action items, blockers, and links to WPs, tasks, deliverables, or risks.`)}>Summarize</button>
              <button type="button" className="meetings-ai-btn" disabled={actionBusy} onClick={() => void handleExtractActions()}>Extract Actions</button>
              <button type="button" className="meetings-ai-btn" onClick={() => onOpenAssistant(`From the meeting "${activeMeeting.title}", identify new risks or blockers and propose additions or updates to the project risk register.`)}>Identify Risks</button>
              <button type="button" className="meetings-ai-btn" onClick={() => onOpenAssistant(`Use the latest meeting records to draft a concise steering-committee follow-up email with decisions, action owners, and deadlines.`)}>Draft Follow-up</button>
            </div>
          ) : null}

          <div className="meetings-content-scroll">
            <pre className="meetings-content-text">{activeMeeting.content_text}</pre>
          </div>
          <div className="meetings-actions-panel">
            <div className="meetings-actions-head">
              <strong>Action Items</strong>
              <button type="button" className="meetings-new-btn" onClick={() => setShowActionForm((prev) => !prev)}>
                <FontAwesomeIcon icon={faPlus} /> Add Action Item
              </button>
            </div>
            {showActionForm ? (
              <div className="inline-form two-cols meetings-action-form">
                <label className="full-span">
                  Description
                  <input value={newActionDescription} onChange={(event) => setNewActionDescription(event.target.value)} />
                </label>
                <label>
                  Assignee
                  <select value={newActionAssigneeMemberId} onChange={(event) => setNewActionAssigneeMemberId(event.target.value)}>
                    <option value="">None</option>
                    {members.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}
                  </select>
                </label>
                <label>
                  Due Date
                  <input type="date" value={newActionDueDate} onChange={(event) => setNewActionDueDate(event.target.value)} />
                </label>
                <label>
                  Priority
                  <select value={newActionPriority} onChange={(event) => setNewActionPriority(event.target.value)}>
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </label>
                <div className="row-actions full-span">
                  <button type="button" disabled={actionBusy || !newActionDescription.trim()} onClick={() => void handleCreateActionItem()}>
                    Save
                  </button>
                  <button type="button" className="ghost" onClick={resetActionForm}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
            <div className="meetings-action-list">
              {actionItems.map((item) => (
                <div key={item.id} className={`meetings-action-row ${item.status === "done" ? "done" : ""}`}>
                  <label className="meetings-action-main">
                    <input
                      type="checkbox"
                      checked={item.status === "done"}
                      disabled={actionBusy}
                      onChange={() => void handleToggleActionStatus(item)}
                    />
                    <span className="meetings-action-copy">
                      <strong>{item.description}</strong>
                      <span className="chips-row">
                        {item.assignee_name ? <span className="chip small">{item.assignee_name}</span> : null}
                        {item.due_date ? <span className="chip small">Due {new Date(item.due_date).toLocaleDateString()}</span> : null}
                        <span className="chip small">{item.priority}</span>
                        <span className="chip small muted">{item.source}</span>
                        {item.linked_task_id ? <span className="chip small status-ok">Task linked</span> : null}
                      </span>
                    </span>
                  </label>
                  <div className="row-actions meetings-action-buttons">
                    <button
                      type="button"
                      className="ghost"
                      disabled={!!item.linked_task_id}
                      onClick={() => {
                        setPromoteItemId(item.id);
                        setPromoteWpId(workPackages[0]?.id || "");
                      }}
                    >
                      Promote to Task
                    </button>
                  </div>
                </div>
              ))}
              {!actionItems.length && !actionBusy ? <p className="muted-small">No action items.</p> : null}
              {actionBusy ? <p className="muted-small">Updating action items...</p> : null}
            </div>
          </div>
        </div>
      ) : null}

      {modalOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card settings-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy && title.trim() && startsAt && (contentText.trim() || transcriptFile)) { e.preventDefault(); void handleSave(); } }}>
            <div className="modal-head">
              <h3>{editingMeetingId ? "Edit Meeting" : "New Meeting"}</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setModalOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label>
                Title
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label>
                Date and Time
                <input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} />
              </label>
              <label>
                Source
                <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
                  <option value="minutes">Minutes</option>
                  <option value="transcript">Transcript</option>
                </select>
              </label>
              <label>
                Source URL
                <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
              </label>
              <label className="full-span">
                Participants
                <input value={participantsText} onChange={(event) => setParticipantsText(event.target.value)} placeholder="Alice, Bob, Carol" />
              </label>
              <label>
                Linked Document
                <select value={linkedDocumentId} onChange={(event) => setLinkedDocumentId(event.target.value)}>
                  <option value="">None</option>
                  {documents.map((item) => <option key={item.latest_document_id} value={item.latest_document_id}>{item.title}</option>)}
                </select>
              </label>
              <label>
                Owner
                <select value={createdByMemberId} onChange={(event) => setCreatedByMemberId(event.target.value)}>
                  <option value="">None</option>
                  {members.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}
                </select>
              </label>
              {!editingMeetingId ? (
                <label className="full-span">
                  Transcript File (optional — .txt, .pdf, .docx)
                  <input
                    type="file"
                    accept=".txt,.pdf,.docx,.md"
                    onChange={(event) => setTranscriptFile(event.target.files?.[0] ?? null)}
                  />
                </label>
              ) : null}
              {!transcriptFile ? (
                <label className="full-span">
                  Content
                  <textarea rows={14} value={contentText} onChange={(event) => setContentText(event.target.value)} />
                </label>
              ) : (
                <p className="muted-small full-span">Content will be extracted from the uploaded file.</p>
              )}
            </div>
            <div className="row-actions">
              <button type="button" disabled={busy || !title.trim() || !startsAt || (!contentText.trim() && !transcriptFile)} onClick={() => void handleSave()}>Save</button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}

      {promoteItemId ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card meetings-promote-modal" onKeyDown={(e) => { if (e.key === "Enter" && !actionBusy && promoteWpId) { e.preventDefault(); void handlePromoteActionItem(); } }}>
            <div className="modal-head">
              <h3>Promote to Task</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setPromoteItemId(null)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label>
                Work Package
                <select value={promoteWpId} onChange={(event) => setPromoteWpId(event.target.value)}>
                  <option value="">Select</option>
                  {workPackages.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.title}</option>)}
                </select>
              </label>
            </div>
            <div className="row-actions">
              <button type="button" disabled={actionBusy || !promoteWpId} onClick={() => void handlePromoteActionItem()}>
                Promote
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}
    </section>
  );
}
