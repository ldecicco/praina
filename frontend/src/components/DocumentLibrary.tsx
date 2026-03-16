import { useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faChevronDown,
  faCloudArrowUp,
  faLink,
  faRotate,
  faCodeBranch,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type { DocumentListItem, DocumentVersion, Member, ProjectProposalSection, WorkEntity } from "../types";

type Props = {
  selectedProjectId: string;
  highlightDocumentKey?: string | null;
  onHighlightConsumed?: () => void;
};

type Scope = "project" | "wp" | "task" | "deliverable" | "milestone";
type StatusFilter = "" | "uploaded" | "indexed" | "failed";

const scopeLabel: Record<Scope, string> = {
  project: "Project",
  wp: "Work Package",
  task: "Task",
  deliverable: "Deliverable",
  milestone: "Milestone",
};

function statusClassName(value: string): string {
  if (value === "indexed") return "doc-status doc-indexed";
  if (value === "failed") return "doc-status doc-failed";
  return "doc-status doc-uploaded";
}

export function DocumentLibrary({ selectedProjectId, highlightDocumentKey, onHighlightConsumed }: Props) {
  const [scopeFilter, setScopeFilter] = useState<Scope | "">("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [search, setSearch] = useState("");

  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [wps, setWps] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);
  const [milestones, setMilestones] = useState<WorkEntity[]>([]);
  const [proposalSections, setProposalSections] = useState<ProjectProposalSection[]>([]);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadScope, setUploadScope] = useState<Scope>("project");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadMetadata, setUploadMetadata] = useState('{"category":"general"}');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadMemberId, setUploadMemberId] = useState("");
  const [scopeEntityId, setScopeEntityId] = useState("");
  const [uploadProposalSectionId, setUploadProposalSectionId] = useState("");

  const [selectedDocumentKey, setSelectedDocumentKey] = useState("");
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [versionOpen, setVersionOpen] = useState(false);

  const [versionTitle, setVersionTitle] = useState("");
  const [versionMetadata, setVersionMetadata] = useState("");
  const [versionFile, setVersionFile] = useState<File | null>(null);
  const [versionMemberId, setVersionMemberId] = useState("");
  const [versionProposalSectionId, setVersionProposalSectionId] = useState("");

  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [linkTitle, setLinkTitle] = useState("");
  const [linkScope, setLinkScope] = useState<Scope>("project");
  const [linkScopeEntityId, setLinkScopeEntityId] = useState("");
  const [linkProposalSectionId, setLinkProposalSectionId] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const scopeEntities = useMemo(() => {
    if (uploadScope === "wp") return wps;
    if (uploadScope === "task") return tasks;
    if (uploadScope === "deliverable") return deliverables;
    if (uploadScope === "milestone") return milestones;
    return [];
  }, [uploadScope, wps, tasks, deliverables, milestones]);
  const linkScopeEntities = useMemo(() => {
    if (linkScope === "wp") return wps;
    if (linkScope === "task") return tasks;
    if (linkScope === "deliverable") return deliverables;
    if (linkScope === "milestone") return milestones;
    return [];
  }, [linkScope, wps, tasks, deliverables, milestones]);
  const indexedCount = useMemo(() => documents.filter((item) => item.status === "indexed").length, [documents]);
  const failedCount = useMemo(() => documents.filter((item) => item.status === "failed").length, [documents]);

  useAutoRefresh(() => {
    if (selectedProjectId) {
      api.listDocuments(selectedProjectId, { scope: scopeFilter || undefined, status: statusFilter || undefined, search: search || undefined })
        .then((docsRes) => setDocuments(docsRes.items))
        .catch(() => {});
    }
  });

  useEffect(() => {
    if (!selectedProjectId) {
      setDocuments([]);
      setMembers([]);
      setWps([]);
      setTasks([]);
      setDeliverables([]);
      setMilestones([]);
      setProposalSections([]);
      return;
    }
    setBusy(true);
    setError("");
    Promise.all([
      api.listMembers(selectedProjectId),
      api.listWorkPackages(selectedProjectId),
      api.listTasks(selectedProjectId),
      api.listDeliverables(selectedProjectId),
      api.listMilestones(selectedProjectId),
      api.listDocuments(selectedProjectId),
      api.listProjectProposalSections(selectedProjectId),
    ])
      .then(([membersRes, wpsRes, tasksRes, deliverablesRes, milestonesRes, docsRes, sectionsRes]) => {
        setMembers(membersRes.items);
        setWps(wpsRes.items);
        setTasks(tasksRes.items);
        setDeliverables(deliverablesRes.items);
        setMilestones(milestonesRes.items);
        setDocuments(docsRes.items);
        setProposalSections(sectionsRes.items);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load project documents.");
      })
      .finally(() => setBusy(false));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    setBusy(true);
    setError("");
    api
      .listDocuments(selectedProjectId, {
        scope: scopeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      })
      .then((docsRes) => setDocuments(docsRes.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to filter documents."))
      .finally(() => setBusy(false));
  }, [selectedProjectId, scopeFilter, statusFilter, search]);

  useEffect(() => {
    if (highlightDocumentKey && documents.length > 0) {
      void loadVersions(highlightDocumentKey);
      onHighlightConsumed?.();
    }
  }, [highlightDocumentKey, documents.length]);

  async function loadVersions(documentKey: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const response = await api.listDocumentVersions(selectedProjectId, documentKey);
      setSelectedDocumentKey(documentKey);
      setVersions(response.versions);
      setVersionOpen(true);
      setStatus(`Loaded ${response.versions.length} version(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load versions.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadDocument() {
    if (!selectedProjectId || !uploadFile || !uploadTitle) return;
    try {
      setBusy(true);
      setError("");
      const payload: {
        file: File;
        scope: Scope;
        title: string;
        metadata_json?: string;
        uploaded_by_member_id?: string;
        proposal_section_id?: string;
        wp_id?: string;
        task_id?: string;
        deliverable_id?: string;
        milestone_id?: string;
      } = {
        file: uploadFile,
        scope: uploadScope,
        title: uploadTitle,
        metadata_json: uploadMetadata,
        uploaded_by_member_id: uploadMemberId || undefined,
        proposal_section_id: uploadProposalSectionId || undefined,
      };
      if (uploadScope === "wp") payload.wp_id = scopeEntityId;
      if (uploadScope === "task") payload.task_id = scopeEntityId;
      if (uploadScope === "deliverable") payload.deliverable_id = scopeEntityId;
      if (uploadScope === "milestone") payload.milestone_id = scopeEntityId;
      const result = await api.uploadDocument(selectedProjectId, payload);
      setStatus(`Uploaded ${result.title} (v${result.version}).`);
      setUploadFile(null);
      setUploadTitle("");
      setScopeEntityId("");
      setUploadProposalSectionId("");
      setUploadOpen(false);
      const docsRes = await api.listDocuments(selectedProjectId, {
        scope: scopeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setDocuments(docsRes.items);
      await loadVersions(result.document_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadVersion() {
    if (!selectedProjectId || !selectedDocumentKey || !versionFile) return;
    try {
      setBusy(true);
      setError("");
      const result = await api.uploadDocumentVersion(selectedProjectId, selectedDocumentKey, {
        file: versionFile,
        title: versionTitle || undefined,
        metadata_json: versionMetadata || undefined,
        uploaded_by_member_id: versionMemberId || undefined,
        proposal_section_id: versionProposalSectionId || undefined,
      });
      setStatus(`New version uploaded: v${result.version}.`);
      setVersionFile(null);
      setVersionTitle("");
      setVersionMetadata("");
      setVersionProposalSectionId("");
      const docsRes = await api.listDocuments(selectedProjectId, {
        scope: scopeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setDocuments(docsRes.items);
      await loadVersions(result.document_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload version.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReindex(documentId: string, documentKey?: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const result = await api.reindexDocument(selectedProjectId, documentId, false);
      setStatus(
        result.status === "indexed"
          ? `Indexed document: ${result.chunks_indexed} chunks.`
          : `Indexing failed: ${result.error || "unknown error"}.`
      );
      const docsRes = await api.listDocuments(selectedProjectId, {
        scope: scopeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setDocuments(docsRes.items);
      if (documentKey) {
        await loadVersions(documentKey);
      } else if (selectedDocumentKey) {
        await loadVersions(selectedDocumentKey);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reindex failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkDocument() {
    if (!selectedProjectId || !linkUrl || !linkTitle) return;
    try {
      setBusy(true);
      setError("");
      const payload: {
        url: string;
        scope: Scope;
        title: string;
        proposal_section_id?: string;
        wp_id?: string;
        task_id?: string;
        deliverable_id?: string;
        milestone_id?: string;
      } = { url: linkUrl, scope: linkScope, title: linkTitle, proposal_section_id: linkProposalSectionId || undefined };
      if (linkScope === "wp") payload.wp_id = linkScopeEntityId;
      if (linkScope === "task") payload.task_id = linkScopeEntityId;
      if (linkScope === "deliverable") payload.deliverable_id = linkScopeEntityId;
      if (linkScope === "milestone") payload.milestone_id = linkScopeEntityId;
      const result = await api.linkDocument(selectedProjectId, payload);
      setStatus(`Linked ${result.title} (v${result.version}).`);
      setLinkUrl("");
      setLinkTitle("");
      setLinkScopeEntityId("");
      setLinkProposalSectionId("");
      setLinkOpen(false);
      const docsRes = await api.listDocuments(selectedProjectId, {
        scope: scopeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setDocuments(docsRes.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Link failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshFromUrl(documentId: string, documentKey?: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const result = await api.refreshDocument(selectedProjectId, documentId);
      setStatus(`Refreshed to v${result.version}.`);
      const docsRes = await api.listDocuments(selectedProjectId, {
        scope: scopeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setDocuments(docsRes.items);
      if (documentKey) {
        await loadVersions(documentKey);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!selectedProjectId) {
    return (
      <section className="panel">
        <p className="muted-small">Select a project to start.</p>
      </section>
    );
  }

  return (
    <section className="panel docs-page">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span>{documents.length} documents</span>
          <span className="setup-summary-sep" />
          <span>{indexedCount} indexed</span>
          <span className="setup-summary-sep" />
          <span className={failedCount > 0 ? "docs-failed-count" : ""}>{failedCount} failed</span>
        </div>
        <button type="button" className="meetings-new-btn" onClick={() => setUploadOpen((p) => !p)}>
          <FontAwesomeIcon icon={faCloudArrowUp} /> Upload
        </button>
        <button type="button" className="meetings-new-btn" onClick={() => setLinkOpen((p) => !p)}>
          <FontAwesomeIcon icon={faLink} /> Link Google Doc
        </button>
      </div>

      {/* Upload modal */}
      {uploadOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card docs-upload-modal" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy && uploadTitle && uploadFile && (uploadScope === "project" || scopeEntityId)) { e.preventDefault(); handleUploadDocument(); } }}>
            <div className="modal-head">
              <h3>Upload Document</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setUploadOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label>
                Title
                <input value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} placeholder="Consortium Agreement" />
              </label>
              <label>
                Scope
                <select value={uploadScope} onChange={(e) => { setUploadScope(e.target.value as Scope); setScopeEntityId(""); }}>
                  <option value="project">Project</option>
                  <option value="wp">WP</option>
                  <option value="task">Task</option>
                  <option value="deliverable">Deliverable</option>
                  <option value="milestone">Milestone</option>
                </select>
              </label>
              {uploadScope !== "project" ? (
                <label className="wide">
                  Linked Entity
                  <select value={scopeEntityId} onChange={(e) => setScopeEntityId(e.target.value)}>
                    <option value="">Select entity</option>
                    {scopeEntities.map((entity) => (
                      <option key={entity.id} value={entity.id}>{entity.code} · {entity.title}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label>
                Uploader
                <select value={uploadMemberId} onChange={(e) => setUploadMemberId(e.target.value)}>
                  <option value="">Optional</option>
                  {members.map((member) => (
                    <option key={member.id} value={member.id}>{member.full_name}</option>
                  ))}
                </select>
              </label>
              <label>
                File
                <input type="file" onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)} />
              </label>
              <label>
                Proposal Section
                <select value={uploadProposalSectionId} onChange={(e) => setUploadProposalSectionId(e.target.value)}>
                  <option value="">Optional</option>
                  {proposalSections.map((section) => (
                    <option key={section.id} value={section.id}>{section.title}</option>
                  ))}
                </select>
              </label>
              <label className="wide">
                Metadata JSON
                <textarea value={uploadMetadata} onChange={(e) => setUploadMetadata(e.target.value)} rows={2} />
              </label>
            </div>
            <div className="row-actions">
              <button
                type="button"
                disabled={busy || !uploadTitle || !uploadFile || (uploadScope !== "project" && !scopeEntityId)}
                onClick={handleUploadDocument}
              >
                Upload Document
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}

      {/* Link Google Doc modal */}
      {linkOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card docs-upload-modal" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy && linkUrl && linkTitle && (linkScope === "project" || linkScopeEntityId)) { e.preventDefault(); handleLinkDocument(); } }}>
            <div className="modal-head">
              <h3>Link Google Doc</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setLinkOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label className="wide">
                Google Docs URL
                <input value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} placeholder="https://docs.google.com/document/d/..." />
              </label>
              <label>
                Title
                <input value={linkTitle} onChange={(e) => setLinkTitle(e.target.value)} placeholder="Proposal Section B" />
              </label>
              <label>
                Scope
                <select value={linkScope} onChange={(e) => { setLinkScope(e.target.value as Scope); setLinkScopeEntityId(""); }}>
                  <option value="project">Project</option>
                  <option value="wp">WP</option>
                  <option value="task">Task</option>
                  <option value="deliverable">Deliverable</option>
                  <option value="milestone">Milestone</option>
                </select>
              </label>
              {linkScope !== "project" ? (
                <label className="wide">
                  Linked Entity
                  <select value={linkScopeEntityId} onChange={(e) => setLinkScopeEntityId(e.target.value)}>
                    <option value="">Select entity</option>
                    {linkScopeEntities.map((entity) => (
                      <option key={entity.id} value={entity.id}>{entity.code} · {entity.title}</option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label>
                Proposal Section
                <select value={linkProposalSectionId} onChange={(e) => setLinkProposalSectionId(e.target.value)}>
                  <option value="">Optional</option>
                  {proposalSections.map((section) => (
                    <option key={section.id} value={section.id}>{section.title}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="row-actions">
              <button
                type="button"
                disabled={busy || !linkUrl || !linkTitle || (linkScope !== "project" && !linkScopeEntityId)}
                onClick={handleLinkDocument}
              >
                Link Document
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}

      {/* Filters */}
      <div className="meetings-toolbar">
        <div className="meetings-filter-group">
          <select value={scopeFilter} onChange={(e) => setScopeFilter(e.target.value as Scope | "")}>
            <option value="">All scopes</option>
            <option value="project">Project</option>
            <option value="wp">WP</option>
            <option value="task">Task</option>
            <option value="deliverable">Deliverable</option>
            <option value="milestone">Milestone</option>
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}>
            <option value="">All statuses</option>
            <option value="uploaded">Uploaded</option>
            <option value="indexed">Indexed</option>
            <option value="failed">Failed</option>
          </select>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search documents..." className="meetings-search" />
        </div>
      </div>

      {/* Document table */}
      <div className="simple-table-wrap">
        <table className="simple-table compact-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Scope</th>
              <th>Status</th>
              <th>Version</th>
              <th>Updated</th>
              <th style={{ width: 120 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((item) => (
              <tr key={item.document_key} className={selectedDocumentKey === item.document_key ? "row-selected" : ""}>
                <td><strong>{item.title}</strong></td>
                <td><span className="chip small">{scopeLabel[item.scope]}</span></td>
                <td><span className={statusClassName(item.status)}>{item.status}</span></td>
                <td>v{item.latest_version} ({item.versions_count})</td>
                <td>{new Date(item.updated_at).toLocaleDateString()}</td>
                <td>
                  <div className="docs-actions">
                    <button type="button" className="ghost docs-action-btn" title="Versions" onClick={() => void loadVersions(item.document_key)}>
                      <FontAwesomeIcon icon={faCodeBranch} />
                    </button>
                    <button type="button" className="ghost docs-action-btn" title="Reindex" onClick={() => void handleReindex(item.latest_document_id, item.document_key)}>
                      <FontAwesomeIcon icon={faRotate} />
                    </button>
                    {item.source_type === "google_docs" ? (
                      <button type="button" className="ghost docs-action-btn" title="Refresh from Google Docs" onClick={() => void handleRefreshFromUrl(item.latest_document_id, item.document_key)}>
                        <FontAwesomeIcon icon={faLink} />
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
            {!busy && documents.length === 0 ? (
              <tr><td colSpan={6} className="empty-state-card">
                No documents yet.
                <button type="button" className="ghost" onClick={() => setUploadOpen(true)} style={{ marginTop: 8 }}>
                  <FontAwesomeIcon icon={faCloudArrowUp} /> Upload Document
                </button>
              </td></tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {/* Version history — collapsible panel below table */}
      {selectedDocumentKey && versionOpen ? (
        <div className="docs-version-panel">
          <div className="docs-version-head">
            <button type="button" className="docs-version-toggle" onClick={() => setVersionOpen((p) => !p)}>
              <FontAwesomeIcon icon={faChevronDown} className={`meetings-toggle-chevron ${versionOpen ? "open" : ""}`} />
              <strong>Version History</strong>
              <span className="docs-version-count">{versions.length}</span>
            </button>
            <div className="docs-new-version-row">
              <input value={versionTitle} onChange={(e) => setVersionTitle(e.target.value)} placeholder="Version title (optional)" />
              <select value={versionMemberId} onChange={(e) => setVersionMemberId(e.target.value)}>
                <option value="">Uploader</option>
                {members.map((member) => (
                  <option key={member.id} value={member.id}>{member.full_name}</option>
                ))}
              </select>
              <select value={versionProposalSectionId} onChange={(e) => setVersionProposalSectionId(e.target.value)}>
                <option value="">Proposal Section</option>
                {proposalSections.map((section) => (
                  <option key={section.id} value={section.id}>{section.title}</option>
                ))}
              </select>
              <input type="file" onChange={(e) => setVersionFile(e.target.files?.[0] ?? null)} className="docs-file-input" />
              <button type="button" disabled={busy || !versionFile} onClick={handleUploadVersion}>
                Upload Version
              </button>
            </div>
          </div>
          <div className="docs-version-list">
            {versions.map((version) => (
              <div key={version.id} className="docs-version-item">
                <span className="docs-version-badge">v{version.version}</span>
                <span className="docs-version-filename">{version.original_filename}</span>
                <span className={statusClassName(version.status)}>{version.status}</span>
                <span className="docs-version-size">{(version.file_size_bytes / 1024).toFixed(0)} KB</span>
                <span className="docs-version-date">{new Date(version.created_at).toLocaleDateString()}</span>
                {version.ingestion_error ? <span className="error docs-version-error">{version.ingestion_error}</span> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
