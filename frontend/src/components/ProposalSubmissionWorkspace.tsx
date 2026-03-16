import { useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUpRightFromSquare,
  faCloudArrowUp,
  faFileLines,
  faLink,
  faPen,
  faPlus,
  faUsersRectangle,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type {
  AuthUser,
  DocumentListItem,
  Member,
  Partner,
  Project,
  ProposalCallBrief,
  ProposalSubmissionItem,
  ProposalSubmissionRequirement,
  ProposalTemplate,
} from "../types";

type Props = {
  selectedProjectId: string;
  callBrief: ProposalCallBrief | null;
  currentUser: AuthUser | null;
  project: Project | null;
};

type RequirementModalMode = "create" | "edit";
type ItemModalState = {
  requirement: ProposalSubmissionRequirement;
  item: ProposalSubmissionItem;
} | null;
type DocumentModalState = {
  requirement: ProposalSubmissionRequirement;
  item: ProposalSubmissionItem;
} | null;

const DOCUMENT_TYPE_OPTIONS = [
  { value: "project", label: "Project" },
  { value: "per_partner", label: "Per Partner" },
] as const;

const FORMAT_HINT_OPTIONS = [
  { value: "online", label: "Online" },
  { value: "upload", label: "Upload" },
] as const;

const STATUS_OPTIONS = [
  { value: "not_started", label: "Not started" },
  { value: "in_preparation", label: "In preparation" },
  { value: "completed", label: "Completed" },
  { value: "submitted", label: "Submitted" },
] as const;

function requirementTypeLabel(value: string): string {
  return DOCUMENT_TYPE_OPTIONS.find((item) => item.value === value)?.label || value;
}

function formatHintLabel(value: string): string {
  return FORMAT_HINT_OPTIONS.find((item) => item.value === value)?.label || value;
}

function submissionStatusLabel(value: string): string {
  return STATUS_OPTIONS.find((item) => item.value === value)?.label || value;
}

function submissionStatusChipClass(status: string): string {
  if (status === "submitted") return "chip small status-ok";
  if (status === "completed") return "chip small status-active";
  if (status === "in_preparation") return "chip small status-warning";
  return "chip small";
}

function buildSubmissionDocumentTitle(requirement: ProposalSubmissionRequirement, item: ProposalSubmissionItem): string {
  return item.partner_name ? `${requirement.title} - ${item.partner_name}` : requirement.title;
}

export function ProposalSubmissionWorkspace({ selectedProjectId, callBrief, currentUser, project }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [requirements, setRequirements] = useState<ProposalSubmissionRequirement[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [templates, setTemplates] = useState<ProposalTemplate[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "project" | "per_partner">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "not_started" | "in_preparation" | "completed" | "submitted">("all");
  const [requirementModalMode, setRequirementModalMode] = useState<RequirementModalMode>("create");
  const [requirementModalOpen, setRequirementModalOpen] = useState(false);
  const [editingRequirementId, setEditingRequirementId] = useState("");
  const [itemModalState, setItemModalState] = useState<ItemModalState>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [documentType, setDocumentType] = useState<"project" | "per_partner">("project");
  const [formatHint, setFormatHint] = useState<"online" | "upload">("online");
  const [required, setRequired] = useState(true);
  const [position, setPosition] = useState(1);
  const [templateId, setTemplateId] = useState("");
  const [itemStatus, setItemStatus] = useState("not_started");
  const [itemAssigneeId, setItemAssigneeId] = useState("");
  const [itemNotes, setItemNotes] = useState("");
  const [documentModalState, setDocumentModalState] = useState<DocumentModalState>(null);
  const [projectDocuments, setProjectDocuments] = useState<DocumentListItem[]>([]);
  const [documentSearch, setDocumentSearch] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");

  useEffect(() => {
    if (!selectedProjectId) {
      setRequirements([]);
      setMembers([]);
      setPartners([]);
      setTemplates([]);
      return;
    }
    setBusy(true);
    setError("");
    Promise.all([
      api.listProposalSubmissionRequirements(selectedProjectId),
      api.listMembers(selectedProjectId),
      api.listPartners(selectedProjectId),
      callBrief?.source_call_id ? api.listProposalTemplates("", true, callBrief.source_call_id) : Promise.resolve({ items: [] }),
    ])
      .then(([requirementsRes, membersRes, partnersRes, templatesRes]) => {
        setRequirements(requirementsRes.items);
        setMembers(membersRes.items);
        setPartners(partnersRes.items);
        setTemplates(templatesRes.items);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load submission package."))
      .finally(() => setBusy(false));
  }, [selectedProjectId, callBrief?.source_call_id]);

  const currentMemberRows = useMemo(
    () => members.filter((member) => member.user_account_id === currentUser?.id),
    [currentUser?.id, members]
  );

  const visiblePartnerIds = useMemo(
    () => new Set(currentMemberRows.map((member) => member.partner_id)),
    [currentMemberRows]
  );

  const isCoordinator = Boolean(
    currentUser?.platform_role === "super_admin" ||
    (project?.coordinator_partner_id && visiblePartnerIds.has(project.coordinator_partner_id))
  );

  const scopedRequirements = useMemo(() => {
    if (isCoordinator) return requirements;
    return requirements
      .filter((requirement) => requirement.document_type === "per_partner")
      .map((requirement) => ({
        ...requirement,
        items: requirement.items.filter((item) => item.partner_id ? visiblePartnerIds.has(item.partner_id) : false),
      }))
      .filter((requirement) => requirement.items.length > 0);
  }, [isCoordinator, requirements, visiblePartnerIds]);

  const flattenedRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const rows = scopedRequirements.flatMap((requirement) => (
      requirement.items.length > 0
        ? requirement.items.map((item) => ({ requirement, item }))
        : [{ requirement, item: null as ProposalSubmissionItem | null }]
    ));
    return rows.filter(({ requirement, item }) => {
      if (typeFilter !== "all" && requirement.document_type !== typeFilter) return false;
      if (statusFilter !== "all" && item?.status !== statusFilter) return false;
      if (!query) return true;
      return [
        requirement.title,
        requirement.description || "",
        item?.partner_name || "",
        item?.assignee_name || "",
        item?.notes || "",
      ].some((value) => value.toLowerCase().includes(query));
    });
  }, [scopedRequirements, search, statusFilter, typeFilter]);

  const itemStats = useMemo(() => {
    const items = scopedRequirements.flatMap((requirement) => requirement.items);
    return {
      totalRequirements: scopedRequirements.length,
      totalItems: items.length,
      projectDocs: scopedRequirements.filter((item) => item.document_type === "project").length,
      partnerDocs: scopedRequirements.filter((item) => item.document_type === "per_partner").length,
      completed: items.filter((item) => item.status === "completed").length,
      submitted: items.filter((item) => item.status === "submitted").length,
      waiting: scopedRequirements.filter((item) => item.document_type === "per_partner" && item.items.length === 0).length,
    };
  }, [scopedRequirements]);

  const readiness = useMemo(() => {
    const requiredRequirements = requirements.filter((requirement) => requirement.required);
    const requiredItems = requiredRequirements.flatMap((requirement) => requirement.items);
    return {
      waiting: requiredRequirements.filter((requirement) => requirement.document_type === "per_partner" && requirement.items.length === 0).length,
      missingFiles: requiredItems.filter((item) => !item.latest_uploaded_document_id).length,
      missingAssignees: requiredItems.filter((item) => !item.assignee_member_id).length,
      openItems: requiredItems.filter((item) => item.status !== "submitted").length,
    };
  }, [requirements]);

  function resetRequirementForm() {
    setEditingRequirementId("");
    setTitle("");
    setDescription("");
    setDocumentType("project");
    setFormatHint("online");
    setRequired(true);
    setPosition(requirements.length + 1);
    setTemplateId("");
  }

  function openCreateRequirementModal() {
    resetRequirementForm();
    setRequirementModalMode("create");
    setRequirementModalOpen(true);
  }

  function openEditRequirementModal(requirement: ProposalSubmissionRequirement) {
    setRequirementModalMode("edit");
    setEditingRequirementId(requirement.id);
    setTitle(requirement.title);
    setDescription(requirement.description || "");
    setDocumentType(requirement.document_type as "project" | "per_partner");
    setFormatHint(requirement.format_hint as "online" | "upload");
    setRequired(requirement.required);
    setPosition(requirement.position);
    setTemplateId(requirement.template_id || "");
    setRequirementModalOpen(true);
  }

  function closeRequirementModal() {
    setRequirementModalOpen(false);
    resetRequirementForm();
  }

  async function handleSaveRequirement() {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const payload = {
        title,
        description: description || null,
        document_type: documentType,
        format_hint: formatHint,
        required,
        position,
        template_id: documentType === "project" && formatHint === "online" && templateId ? templateId : null,
      };
      const saved = requirementModalMode === "edit" && editingRequirementId
        ? await api.updateProposalSubmissionRequirement(selectedProjectId, editingRequirementId, payload)
        : await api.createProposalSubmissionRequirement(selectedProjectId, payload);
      setRequirements((prev) => {
        const next = prev.filter((item) => item.id !== saved.id);
        return [...next, saved].sort((a, b) => a.position - b.position || a.title.localeCompare(b.title));
      });
      setStatus(requirementModalMode === "edit" ? "Document updated." : "Document added.");
      closeRequirementModal();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save document.");
    } finally {
      setBusy(false);
    }
  }

  function openItemModal(requirement: ProposalSubmissionRequirement, item: ProposalSubmissionItem) {
    setItemModalState({ requirement, item });
    setItemStatus(item.status);
    setItemAssigneeId(item.assignee_member_id || "");
    setItemNotes(item.notes || "");
  }

  function closeItemModal() {
    setItemModalState(null);
    setItemStatus("not_started");
    setItemAssigneeId("");
    setItemNotes("");
  }

  async function handleSaveItem() {
    if (!selectedProjectId || !itemModalState) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.updateProposalSubmissionItem(selectedProjectId, itemModalState.item.id, {
        status: itemStatus,
        assignee_member_id: itemAssigneeId || null,
        notes: itemNotes || null,
      });
      setRequirements((prev) => prev.map((requirement) => {
        if (requirement.id !== itemModalState.requirement.id) return requirement;
        return {
          ...requirement,
          items: requirement.items.map((item) => (item.id === updated.id ? updated : item)),
        };
      }));
      setStatus("Item updated.");
      closeItemModal();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update item.");
    } finally {
      setBusy(false);
    }
  }

  const templateChoices = useMemo(
    () => templates.filter((item) => item.is_active),
    [templates]
  );

  async function openDocumentModal(requirement: ProposalSubmissionRequirement, item: ProposalSubmissionItem) {
    if (!selectedProjectId) return;
    setDocumentModalState({ requirement, item });
    setDocumentSearch("");
    setSelectedDocumentId(item.latest_uploaded_document_id || "");
    setUploadFile(null);
    setUploadTitle(buildSubmissionDocumentTitle(requirement, item));
    try {
      const docs = await api.listDocuments(selectedProjectId, { scope: "project" });
      setProjectDocuments(docs.items);
    } catch {
      setProjectDocuments([]);
    }
  }

  function closeDocumentModal() {
    setDocumentModalState(null);
    setProjectDocuments([]);
    setDocumentSearch("");
    setSelectedDocumentId("");
    setUploadFile(null);
    setUploadTitle("");
  }

  async function handleAttachExistingDocument() {
    if (!selectedProjectId || !documentModalState || !selectedDocumentId) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.updateProposalSubmissionItem(selectedProjectId, documentModalState.item.id, {
        latest_uploaded_document_id: selectedDocumentId,
        status: documentModalState.item.status === "submitted" ? "submitted" : "completed",
      });
      setRequirements((prev) => prev.map((requirement) => {
        if (requirement.id !== documentModalState.requirement.id) return requirement;
        return {
          ...requirement,
          items: requirement.items.map((item) => (item.id === updated.id ? updated : item)),
        };
      }));
      setStatus("Document linked.");
      closeDocumentModal();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to link document.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadSubmissionDocument() {
    if (!selectedProjectId || !documentModalState || !uploadFile) return;
    try {
      setBusy(true);
      setError("");
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: uploadFile,
        scope: "project",
        title: uploadTitle.trim() || buildSubmissionDocumentTitle(documentModalState.requirement, documentModalState.item),
        uploaded_by_member_id: documentModalState.item.assignee_member_id || undefined,
        metadata_json: JSON.stringify({
          submission_requirement_id: documentModalState.requirement.id,
          submission_item_id: documentModalState.item.id,
          submission_partner_id: documentModalState.item.partner_id,
        }),
      });
      const updated = await api.updateProposalSubmissionItem(selectedProjectId, documentModalState.item.id, {
        latest_uploaded_document_id: uploaded.id,
        status: documentModalState.item.status === "submitted" ? "submitted" : "completed",
      });
      setRequirements((prev) => prev.map((requirement) => {
        if (requirement.id !== documentModalState.requirement.id) return requirement;
        return {
          ...requirement,
          items: requirement.items.map((item) => (item.id === updated.id ? updated : item)),
        };
      }));
      setStatus("Document uploaded.");
      closeDocumentModal();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload document.");
    } finally {
      setBusy(false);
    }
  }

  const filteredProjectDocuments = useMemo(() => {
    const query = documentSearch.trim().toLowerCase();
    if (!query) return projectDocuments;
    return projectDocuments.filter((item) => item.title.toLowerCase().includes(query));
  }, [documentSearch, projectDocuments]);

  return (
    <div className="submission-page">
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span>{itemStats.totalRequirements} documents</span>
          <span className="setup-summary-sep" />
          <span>{itemStats.projectDocs} project</span>
          <span className="setup-summary-sep" />
          <span>{itemStats.partnerDocs} per partner</span>
          <span className="setup-summary-sep" />
          <span>{itemStats.completed} completed</span>
          <span className="setup-summary-sep" />
          <span>{itemStats.submitted} submitted</span>
          <span className="setup-summary-sep" />
          <span>{itemStats.waiting} waiting</span>
        </div>
        <button type="button" className="meetings-new-btn" onClick={openCreateRequirementModal} disabled={!selectedProjectId || busy || !isCoordinator}>
          <FontAwesomeIcon icon={faPlus} />
          Add Document
        </button>
      </div>

      {isCoordinator ? (
        <div className="setup-summary-bar submission-readiness-bar">
          <div className="setup-summary-stats">
            <span>{readiness.waiting} waiting</span>
            <span className="setup-summary-sep" />
            <span>{readiness.missingFiles} missing files</span>
            <span className="setup-summary-sep" />
            <span>{readiness.missingAssignees} missing assignees</span>
            <span className="setup-summary-sep" />
            <span>{readiness.openItems} open</span>
          </div>
        </div>
      ) : null}

      {status ? <div className="success-banner">{status}</div> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="meetings-toolbar">
        <div className="meetings-filter-group">
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}>
            <option value="all">All Types</option>
            <option value="project">Project</option>
            <option value="per_partner">Per Partner</option>
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
            <option value="all">All Statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <input
            className="meetings-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search"
          />
        </div>
      </div>

      <div className="simple-table-wrap">
        <table className="simple-table compact-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Type</th>
              <th>Format</th>
              <th>Partner</th>
              <th>Status</th>
              <th>Assignee</th>
              <th>File</th>
              <th>Template</th>
              <th>Updated</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {flattenedRows.map(({ requirement, item }) => {
              const template = requirement.template_id ? templates.find((entry) => entry.id === requirement.template_id) : null;
              return (
                <tr key={item?.id || `${requirement.id}-waiting`} onDoubleClick={() => { if (item) openItemModal(requirement, item); }}>
                  <td>
                    <div className="submission-doc-cell">
                      <strong>{requirement.title}</strong>
                      {requirement.description ? <span>{requirement.description}</span> : null}
                    </div>
                  </td>
                  <td>
                    <span className="chip small">{requirementTypeLabel(requirement.document_type)}</span>
                  </td>
                  <td>
                    <span className="chip small">{formatHintLabel(requirement.format_hint)}</span>
                  </td>
                  <td>{item ? (item.partner_name || "Project") : "Waiting for partners"}</td>
                  <td>
                    {item ? (
                      <span className={submissionStatusChipClass(item.status)}>{submissionStatusLabel(item.status)}</span>
                    ) : (
                      <span className="chip small status-warning">Waiting</span>
                    )}
                  </td>
                  <td>{item?.assignee_name || "-"}</td>
                  <td>{item?.latest_uploaded_document_title || "-"}</td>
                  <td>
                    {template ? (
                      <span className="submission-template-link">
                        <FontAwesomeIcon icon={faFileLines} />
                        {template.name}
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{new Date(item?.updated_at || requirement.updated_at).toLocaleDateString()}</td>
                  <td>
                    <div className="table-row-actions">
                      {isCoordinator ? (
                        <button type="button" className="ghost small" onClick={() => openEditRequirementModal(requirement)}>
                          <FontAwesomeIcon icon={faPen} />
                        </button>
                      ) : null}
                      {item ? (
                        <button type="button" className="ghost small" onClick={() => void openDocumentModal(requirement, item)}>
                          <FontAwesomeIcon icon={faLink} />
                        </button>
                      ) : null}
                      {item ? (
                        <button type="button" className="ghost small" onClick={() => openItemModal(requirement, item)}>
                          <FontAwesomeIcon icon={faArrowUpRightFromSquare} />
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
            {!busy && flattenedRows.length === 0 ? (
              <tr>
                <td colSpan={10}>
                  <div className="empty-state-card submission-empty-card">No documents</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {requirementModalOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeRequirementModal(); }}>
          <div className="modal-card settings-modal-card">
            <div className="modal-head">
              <h3>{requirementModalMode === "edit" ? "Edit Document" : "Add Document"}</h3>
              <button type="button" className="ghost" onClick={closeRequirementModal}>Close</button>
            </div>
            <div className="form-grid">
              <label className="full-span">
                Title
                <input value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label>
                Type
                <select
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value as "project" | "per_partner")}
                  disabled={requirementModalMode === "edit"}
                >
                  {DOCUMENT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Format
                <select
                  value={formatHint}
                  onChange={(e) => setFormatHint(e.target.value as "online" | "upload")}
                  disabled={requirementModalMode === "edit"}
                >
                  {FORMAT_HINT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Position
                <input type="number" min={1} value={position} onChange={(e) => setPosition(Number(e.target.value) || 1)} />
              </label>
              <label className="checkbox-label submission-required-toggle">
                <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />
                Required
              </label>
              <label className="full-span">
                Template
                <select
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  disabled={documentType !== "project" || formatHint !== "online"}
                >
                  <option value="">None</option>
                  {templateChoices.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </label>
              <label className="full-span">
                Description
                <textarea rows={5} value={description} onChange={(e) => setDescription(e.target.value)} />
              </label>
            </div>
            <div className="row-actions">
              <button type="button" onClick={handleSaveRequirement} disabled={busy || !title.trim()}>
                {requirementModalMode === "edit" ? "Save" : "Add"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {itemModalState ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeItemModal(); }}>
          <div className="modal-card settings-modal-card">
            <div className="modal-head">
              <h3>{itemModalState.requirement.title}</h3>
              <button type="button" className="ghost" onClick={closeItemModal}>Close</button>
            </div>
            <div className="submission-item-head">
              <span className="chip small">{requirementTypeLabel(itemModalState.requirement.document_type)}</span>
              <span className="chip small">{formatHintLabel(itemModalState.requirement.format_hint)}</span>
              {itemModalState.item.partner_name ? (
                <span className="submission-item-meta">
                  <FontAwesomeIcon icon={faUsersRectangle} />
                  {itemModalState.item.partner_name}
                </span>
              ) : null}
            </div>
            <div className="form-grid">
              <label>
                Status
                <select value={itemStatus} onChange={(e) => setItemStatus(e.target.value)}>
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Assignee
                <select value={itemAssigneeId} onChange={(e) => setItemAssigneeId(e.target.value)}>
                  <option value="">None</option>
                  {members.map((member) => (
                    <option key={member.id} value={member.id}>{member.full_name}</option>
                  ))}
                </select>
              </label>
              <label className="full-span">
                Notes
                <textarea rows={6} value={itemNotes} onChange={(e) => setItemNotes(e.target.value)} />
              </label>
            </div>
            <div className="row-actions">
              <button type="button" onClick={handleSaveItem} disabled={busy}>Save</button>
            </div>
          </div>
        </div>
      ) : null}

      {documentModalState ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeDocumentModal(); }}>
          <div className="modal-card settings-modal-card">
            <div className="modal-head">
              <h3>{buildSubmissionDocumentTitle(documentModalState.requirement, documentModalState.item)}</h3>
              <button type="button" className="ghost" onClick={closeDocumentModal}>Close</button>
            </div>
            <div className="submission-link-grid">
              <div className="submission-link-panel">
                <div className="meetings-toolbar">
                  <div className="meetings-filter-group">
                    <input
                      className="meetings-search"
                      value={documentSearch}
                      onChange={(e) => setDocumentSearch(e.target.value)}
                      placeholder="Search"
                    />
                  </div>
                </div>
                <div className="simple-table-wrap">
                  <table className="simple-table compact-table">
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Version</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProjectDocuments.map((document) => (
                        <tr
                          key={document.document_key}
                          className={selectedDocumentId === document.latest_document_id ? "row-selected" : ""}
                          onClick={() => setSelectedDocumentId(document.latest_document_id)}
                        >
                          <td><strong>{document.title}</strong></td>
                          <td><span className="chip small">{document.status}</span></td>
                          <td>v{document.latest_version}</td>
                        </tr>
                      ))}
                      {filteredProjectDocuments.length === 0 ? (
                        <tr>
                          <td colSpan={3}>
                            <div className="empty-state-card submission-doc-picker-empty">No documents</div>
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
                <div className="row-actions submission-link-actions">
                  <button type="button" onClick={handleAttachExistingDocument} disabled={busy || !selectedDocumentId}>
                    Use Existing
                  </button>
                </div>
              </div>
              <div className="submission-link-panel">
                <div className="form-grid">
                  <label className="full-span">
                    Title
                    <input value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} />
                  </label>
                  <label className="full-span">
                    File
                    <input type="file" onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)} />
                  </label>
                </div>
                <div className="row-actions submission-link-actions">
                  <button type="button" onClick={handleUploadSubmissionDocument} disabled={busy || !uploadFile}>
                    <FontAwesomeIcon icon={faCloudArrowUp} />
                    Upload
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
