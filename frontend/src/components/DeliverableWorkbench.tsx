import { useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUpRightFromSquare,
  faCircleCheck,
  faClock,
  faFileArrowUp,
  faFileLines,
  faListCheck,
  faTriangleExclamation,
  faUserCheck,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { DocumentListItem, Member, ReviewFinding, WorkEntity } from "../types";
import { useStatusToast } from "../lib/useStatusToast";

type Props = {
  selectedProjectId: string;
  onOpenAssistant: (prompt: string) => void;
};

type WorkbenchTab = "planning" | "review" | "findings";

function reviewStateLabel(deliverable: WorkEntity | null, reviewer: Member | null): string {
  if (!deliverable) return "-";
  if (deliverable.workflow_status === "final") return "Final";
  if (reviewer && deliverable.review_due_month) return `Due M${deliverable.review_due_month}`;
  if (reviewer) return "Reviewer Set";
  return "Unassigned";
}

export function DeliverableWorkbench({ selectedProjectId, onOpenAssistant }: Props) {
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [findings, setFindings] = useState<ReviewFinding[]>([]);
  const [draftFile, setDraftFile] = useState<File | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedDeliverableId, setSelectedDeliverableId] = useState("");
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("planning");
  const [findingModalOpen, setFindingModalOpen] = useState(false);
  const [editingFindingId, setEditingFindingId] = useState<string | null>(null);
  const [findingType, setFindingType] = useState("issue");
  const [findingStatus, setFindingStatus] = useState("open");
  const [findingSource, setFindingSource] = useState("manual");
  const [findingDocumentId, setFindingDocumentId] = useState("");
  const [findingSectionRef, setFindingSectionRef] = useState("");
  const [findingSummary, setFindingSummary] = useState("");
  const [findingDetails, setFindingDetails] = useState("");
  const [findingCreatedByMemberId, setFindingCreatedByMemberId] = useState("");
  const { error, setError, status, setStatus } = useStatusToast();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!selectedProjectId) {
      setDeliverables([]);
      setDocuments([]);
      setMembers([]);
      setFindings([]);
      return;
    }
    Promise.all([api.listDeliverables(selectedProjectId), api.listDocuments(selectedProjectId), api.listMembers(selectedProjectId)])
      .then(([deliverablesRes, documentsRes, membersRes]) => {
        setDeliverables(deliverablesRes.items);
        setDocuments(documentsRes.items);
        setMembers(membersRes.items);
        setSelectedDeliverableId((current) => current || deliverablesRes.items[0]?.id || "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load deliverables."));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || !selectedDeliverableId) {
      setFindings([]);
      return;
    }
    api
      .listReviewFindings(selectedProjectId, selectedDeliverableId)
      .then((response) => setFindings(response.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load review findings."));
  }, [selectedProjectId, selectedDeliverableId]);

  const selectedDeliverable = useMemo(
    () => deliverables.find((item) => item.id === selectedDeliverableId) || null,
    [deliverables, selectedDeliverableId]
  );
  const linkedDocuments = useMemo(
    () => documents.filter((item) => item.deliverable_id === selectedDeliverableId),
    [documents, selectedDeliverableId]
  );
  const reviewer = useMemo(
    () => members.find((item) => item.id === selectedDeliverable?.review_owner_member_id) || null,
    [members, selectedDeliverable?.review_owner_member_id]
  );
  const openFindingsCount = useMemo(() => findings.filter((item) => item.status === "open").length, [findings]);

  function resetFindingForm() {
    setEditingFindingId(null);
    setFindingType("issue");
    setFindingStatus("open");
    setFindingSource("manual");
    setFindingDocumentId("");
    setFindingSectionRef("");
    setFindingSummary("");
    setFindingDetails("");
    setFindingCreatedByMemberId("");
  }

  function openNewFinding() {
    resetFindingForm();
    setFindingModalOpen(true);
  }

  function openEditFinding(finding: ReviewFinding) {
    setEditingFindingId(finding.id);
    setFindingType(finding.finding_type);
    setFindingStatus(finding.status);
    setFindingSource(finding.source);
    setFindingDocumentId(finding.document_id || "");
    setFindingSectionRef(finding.section_ref || "");
    setFindingSummary(finding.summary);
    setFindingDetails(finding.details || "");
    setFindingCreatedByMemberId(finding.created_by_member_id || "");
    setFindingModalOpen(true);
  }

  async function handleSaveFinding() {
    if (!selectedProjectId || !selectedDeliverable) return;
    try {
      setBusy(true);
      setError("");
      const payload = {
        document_id: findingDocumentId || null,
        finding_type: findingType,
        status: findingStatus,
        source: findingSource,
        section_ref: findingSectionRef || undefined,
        summary: findingSummary,
        details: findingDetails || undefined,
        created_by_member_id: findingCreatedByMemberId || null,
      };
      const saved = editingFindingId
        ? await api.updateReviewFinding(selectedProjectId, selectedDeliverable.id, editingFindingId, payload)
        : await api.createReviewFinding(selectedProjectId, selectedDeliverable.id, payload);
      setFindings((current) => {
        const existingIndex = current.findIndex((item) => item.id === saved.id);
        if (existingIndex >= 0) {
          const next = [...current];
          next[existingIndex] = saved;
          return next;
        }
        return [saved, ...current];
      });
      setFindingModalOpen(false);
      setStatus(`${saved.summary} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save finding.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDraftUpload() {
    if (!selectedProjectId || !selectedDeliverable || !draftFile) return;
    try {
      setBusy(true);
      setError("");
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: draftFile,
        scope: "deliverable",
        title: draftTitle.trim() || `${selectedDeliverable.code} Draft`,
        deliverable_id: selectedDeliverable.id,
      });
      setStatus(`Uploaded ${uploaded.title} v${uploaded.version}.`);
      setDraftFile(null);
      setDraftTitle("");
      const documentsRes = await api.listDocuments(selectedProjectId);
      setDocuments(documentsRes.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload draft.");
    } finally {
      setBusy(false);
    }
  }

  if (!selectedProjectId) {
    return <section className="panel"><p className="muted-small">Select a project to start.</p></section>;
  }

  return (
    <section className="panel delivery-page workbench-page">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <strong>{selectedDeliverable?.code || "No deliverable"}</strong>
          <span className="setup-summary-sep" />
          <span>Deliverables {deliverables.length}</span>
          <span className="setup-summary-sep" />
          <span>Findings {findings.length}</span>
          <span className="setup-summary-sep" />
          <span>Open {openFindingsCount}</span>
          <span className="setup-summary-sep" />
          <span>Documents {linkedDocuments.length}</span>
          {selectedDeliverable?.due_month ? (
            <>
              <span className="setup-summary-sep" />
              <span>Due M{selectedDeliverable.due_month}</span>
            </>
          ) : null}
          <span className="setup-summary-sep" />
          <span>{reviewStateLabel(selectedDeliverable, reviewer)}</span>
        </div>
        {selectedDeliverable ? (
          <button
            type="button"
            className="meetings-new-btn"
            onClick={() => onOpenAssistant(`Prepare a deliverable workbench brief for ${selectedDeliverable.code}: planning status, review setup, linked documents, and next actions.`)}
          >
            <FontAwesomeIcon icon={faArrowUpRightFromSquare} /> Open In Assistant
          </button>
        ) : null}
      </div>

      <div className="meetings-toolbar">
        <div className="meetings-filter-group workbench-filter-group">
          <select value={selectedDeliverableId} onChange={(event) => setSelectedDeliverableId(event.target.value)}>
            {deliverables.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} · {item.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="delivery-tabs">
        <button type="button" className={`delivery-tab ${activeTab === "planning" ? "active" : ""}`} onClick={() => setActiveTab("planning")}>
          Planning
        </button>
        <button type="button" className={`delivery-tab ${activeTab === "review" ? "active" : ""}`} onClick={() => setActiveTab("review")}>
          Review
        </button>
        <button type="button" className={`delivery-tab ${activeTab === "findings" ? "active" : ""}`} onClick={() => setActiveTab("findings")}>
          Findings <span className="delivery-tab-count">{findings.length}</span>
        </button>
        {activeTab === "findings" ? (
          <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openNewFinding}>
            New Finding
          </button>
        ) : null}
      </div>

      {selectedDeliverable ? (
        <div className="workbench-shell">
          <div className="workbench-primary">
            <div className="card-slab">
              <div className="workpane-head">
                <h3>{selectedDeliverable.code}</h3>
              </div>
              <div className="assistant-brief-grid workbench-info-grid">
                <div className="assistant-brief-cell">
                  <span>Status</span>
                  <strong>{selectedDeliverable.workflow_status || "draft"}</strong>
                </div>
                <div className="assistant-brief-cell">
                  <span>Reviewer</span>
                  <strong>{reviewer?.full_name || "Unassigned"}</strong>
                </div>
                <div className="assistant-brief-cell">
                  <span>Review Due</span>
                  <strong>{selectedDeliverable.review_due_month ? `M${selectedDeliverable.review_due_month}` : "-"}</strong>
                </div>
                <div className="assistant-brief-cell">
                  <span>Linked WPs</span>
                  <strong>{selectedDeliverable.wp_ids.length}</strong>
                </div>
              </div>
            </div>

            {activeTab === "planning" ? (
              <div className="card-slab">
                <div className="assistant-action-grid workbench-actions-grid">
                  <button type="button" className="assistant-action-card" onClick={() => onOpenAssistant(`Create a structured outline for deliverable ${selectedDeliverable.code} ${selectedDeliverable.title}. Use linked project knowledge and work package context.`)}>
                    <FontAwesomeIcon icon={faListCheck} className="assistant-action-icon" />
                    <strong>Outline</strong>
                  </button>
                  <button type="button" className="assistant-action-card" onClick={() => onOpenAssistant(`List the evidence, sections, and missing inputs needed to write deliverable ${selectedDeliverable.code}.`)}>
                    <FontAwesomeIcon icon={faFileLines} className="assistant-action-icon" />
                    <strong>Evidence</strong>
                  </button>
                  <button type="button" className="assistant-action-card" onClick={() => onOpenAssistant(`Suggest contributors and reviewers for deliverable ${selectedDeliverable.code} based on current assignments and project members.`)}>
                    <FontAwesomeIcon icon={faUserCheck} className="assistant-action-icon" />
                    <strong>Contributors</strong>
                  </button>
                </div>
              </div>
            ) : null}

            {activeTab === "review" ? (
              <>
                <div className="card-slab">
                  <div className="assistant-action-grid workbench-actions-grid">
                    <button type="button" className="assistant-action-card" onClick={() => onOpenAssistant(`Review deliverable ${selectedDeliverable.code}. Check coherence with proposal objectives, linked documents, and current project status.`)}>
                      <FontAwesomeIcon icon={faCircleCheck} className="assistant-action-icon" />
                      <strong>Coherence</strong>
                    </button>
                    <button type="button" className="assistant-action-card" onClick={() => onOpenAssistant(`For deliverable ${selectedDeliverable.code}, identify missing sections, unsupported claims, and terminology inconsistencies.`)}>
                      <FontAwesomeIcon icon={faTriangleExclamation} className="assistant-action-icon" />
                      <strong>Gaps</strong>
                    </button>
                    <button type="button" className="assistant-action-card" onClick={() => onOpenAssistant(`Prepare a review memo for deliverable ${selectedDeliverable.code} with issues, strengths, and next corrections.`)}>
                      <FontAwesomeIcon icon={faClock} className="assistant-action-icon" />
                      <strong>Memo</strong>
                    </button>
                  </div>
                </div>
                <div className="card-slab workbench-upload-card">
                  <div className="workpane-head">
                    <h3>Upload Draft</h3>
                  </div>
                  <div className="form-grid">
                    <label>
                      Draft Title
                      <input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} />
                    </label>
                    <label>
                      Draft File
                      <input type="file" onChange={(event) => setDraftFile(event.target.files?.[0] || null)} />
                    </label>
                  </div>
                  <div className="row-actions">
                    <button type="button" className="btn-primary" onClick={() => void handleDraftUpload()} disabled={busy || !draftFile}>
                      <FontAwesomeIcon icon={faFileArrowUp} /> Upload Draft
                    </button>
                  </div>
                </div>
              </>
            ) : null}

            {activeTab === "findings" ? (
              <div className="card-slab">
                <div className="simple-table-wrap">
                  <table className="simple-table compact-table">
                    <thead>
                      <tr>
                        <th>Summary</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Section</th>
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {findings.map((item) => (
                        <tr key={item.id} onDoubleClick={() => openEditFinding(item)}>
                          <td>
                            <strong>{item.summary}</strong>
                          </td>
                          <td>{item.finding_type}</td>
                          <td>{item.status}</td>
                          <td>{item.section_ref || "-"}</td>
                          <td>{item.source}</td>
                        </tr>
                      ))}
                      {findings.length === 0 ? (
                        <tr>
                          <td colSpan={5}>No findings.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>

          <aside className="card-slab workbench-side-card">
            <div className="workpane-head">
              <h3>Documents</h3>
            </div>
            <div className="assistant-focus-list">
              {linkedDocuments.map((item) => (
                <div key={item.latest_document_id} className="assistant-focus-item neutral workbench-doc-item">
                  <span className="doc-status-wrap">
                    <span className={`doc-status ${item.status === "indexed" ? "doc-indexed" : item.status === "failed" ? "doc-failed" : "doc-uploaded"}`}>
                      {item.status}
                    </span>
                  </span>
                  <strong>{item.title}</strong>
                </div>
              ))}
              {linkedDocuments.length === 0 ? <div className="dashboard-empty-row">No linked documents</div> : null}
            </div>
          </aside>
        </div>
      ) : (
        <div className="dashboard-empty-row">No deliverable selected</div>
      )}

      {findingModalOpen && selectedDeliverable ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card settings-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy && findingSummary.trim()) { e.preventDefault(); void handleSaveFinding(); } }}>
            <div className="modal-head">
              <h3>{editingFindingId ? "Edit Finding" : "New Finding"}</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setFindingModalOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label>
                Type
                <select value={findingType} onChange={(event) => setFindingType(event.target.value)}>
                  <option value="issue">Issue</option>
                  <option value="warning">Warning</option>
                  <option value="strength">Strength</option>
                </select>
              </label>
              <label>
                Status
                <select value={findingStatus} onChange={(event) => setFindingStatus(event.target.value)}>
                  <option value="open">Open</option>
                  <option value="resolved">Resolved</option>
                </select>
              </label>
              <label>
                Source
                <select value={findingSource} onChange={(event) => setFindingSource(event.target.value)}>
                  <option value="manual">Manual</option>
                  <option value="assistant">Assistant</option>
                </select>
              </label>
              <label>
                Draft
                <select value={findingDocumentId} onChange={(event) => setFindingDocumentId(event.target.value)}>
                  <option value="">None</option>
                  {linkedDocuments.map((item) => (
                    <option key={item.latest_document_id} value={item.latest_document_id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Section
                <input value={findingSectionRef} onChange={(event) => setFindingSectionRef(event.target.value)} />
              </label>
              <label>
                Owner
                <select value={findingCreatedByMemberId} onChange={(event) => setFindingCreatedByMemberId(event.target.value)}>
                  <option value="">None</option>
                  {members.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="full-span">
                Summary
                <input value={findingSummary} onChange={(event) => setFindingSummary(event.target.value)} />
              </label>
              <label className="full-span">
                Details
                <textarea rows={8} value={findingDetails} onChange={(event) => setFindingDetails(event.target.value)} />
              </label>
            </div>
            <div className="row-actions">
              <button type="button" disabled={busy || !findingSummary.trim()} onClick={() => void handleSaveFinding()}>Save</button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}
    </section>
  );
}
