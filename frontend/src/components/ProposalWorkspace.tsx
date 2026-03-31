import { useEffect, useMemo, useRef, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUpRightFromSquare,
  faBoxArchive,
  faBolt,
  faCalendarDay,
  faCheck,
  faChevronDown,
  faChevronLeft,
  faChevronRight,
  faCopy,
  faFileLines,
  faFilePdf,
  faFolderOpen,
  faLayerGroup,
  faListCheck,
  faPaperPlane,
  faPen,
  faPlus,
  faRotate,
  faTrash,
  faUserCheck,
  faUsersRectangle,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { renderMarkdown } from "../lib/renderMarkdown";
import { ProposalRichEditor } from "./ProposalRichEditor";
import { useStatusToast } from "../lib/useStatusToast";
import type {
  AuthUser,
  Member,
  Project,
  ProjectProposalSection,
  ProposalCallAnswer,
  ProposalCallBrief,
  ProposalCallIngestJob,
  ProposalCallLibraryDocument,
  ProposalCallLibraryEntry,
  ProposalReviewFinding,
  ProposalTemplate,
  ProposalTemplateSection,
} from "../types";

type Props = {
  selectedProjectId: string;
  project: Project | null;
  currentUser?: AuthUser | null;
  onProjectUpdated: (project: Project) => void;
  onNavigateToAssistant?: () => void;
  onNavigateToCall?: () => void;
  onNavigateToProposal?: () => void;
  workspaceMode?: "call" | "proposal";
};

type SectionFilter = "all" | "open" | "needs_docs" | "in_review" | "approved";
type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

const STATUS_OPTIONS = ["not_started", "drafting", "in_review", "changes_requested", "approved", "final"] as const;
const ASSISTANT_PENDING_PROMPT_KEY = "assistant_pending_prompt";
const LANGUAGE_LABELS: Record<string, string> = {
  en_GB: "English (UK)",
  en_US: "English (US)",
  it: "Italian",
  fr: "French",
  de: "German",
  es: "Spanish",
  pt: "Portuguese",
};

const CALL_DOCUMENT_CATEGORIES = [
  { value: "main_call", label: "Main Call" },
  { value: "addendum", label: "Addendum" },
  { value: "faq", label: "FAQ" },
  { value: "annex", label: "Annex" },
  { value: "guide", label: "Guide" },
  { value: "budget_rules", label: "Budget Rules" },
  { value: "submission_manual", label: "Submission Manual" },
  { value: "template", label: "Template" },
  { value: "other", label: "Other" },
] as const;

function callDocumentCategoryLabel(category: string | null | undefined): string {
  return CALL_DOCUMENT_CATEGORIES.find((item) => item.value === category)?.label || "Other";
}

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function callDocumentIndexingLabel(status: string): string {
  if (status === "uploaded") return "queued";
  if (status === "processing") return "indexing";
  return status || "uploaded";
}

function languageInstruction(langCode: string | null | undefined): string {
  if (!langCode || langCode === "en_GB") return "";
  const label = LANGUAGE_LABELS[langCode] || "English (UK)";
  return `IMPORTANT: You MUST reply in ${label}. All output text must be written in ${label}.`;
}

function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

function saveStateLabel(saveState: SaveState): string {
  switch (saveState) {
    case "dirty":
      return "Unsaved";
    case "saving":
      return "Saving";
    case "saved":
      return "Saved";
    case "error":
      return "Error";
    default:
      return "Ready";
  }
}

function statusChipClass(status: string): string {
  if (status === "approved" || status === "final") return "chip small status-ok";
  if (status === "in_review") return "chip small status-active";
  if (status === "changes_requested") return "chip small status-danger";
  if (status === "drafting") return "chip small status-warning";
  return "chip small";
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "<1m";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  if (minutes < 60) return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function tokenizeForMatch(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/i)
    .map((item) => item.trim())
    .filter((item) => item.length >= 4);
}

function emptyCallBrief(projectId: string): ProposalCallBrief {
  return {
    id: null,
    project_id: projectId,
    source_call_id: null,
    source_version: null,
    copied_by_user_id: null,
    copied_at: null,
    call_title: null,
    funder_name: null,
    programme_name: null,
    reference_code: null,
    submission_deadline: null,
    source_url: null,
    summary: null,
    eligibility_notes: null,
    budget_notes: null,
    scoring_notes: null,
    requirements_text: null,
    created_at: null,
    updated_at: null,
  };
}

export function ProposalWorkspace({
  selectedProjectId,
  project,
  currentUser,
  onProjectUpdated,
  onNavigateToAssistant,
  onNavigateToCall,
  onNavigateToProposal,
  workspaceMode = "proposal",
}: Props) {
  const [busy, setBusy] = useState(false);
  const { error, setError, status, setStatus } = useStatusToast();
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [templates, setTemplates] = useState<ProposalTemplate[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [sections, setSections] = useState<ProjectProposalSection[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [activeSectionId, setActiveSectionId] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<SectionFilter>("all");
  const [localContent, setLocalContent] = useState("");
  const [localNotes, setLocalNotes] = useState("");
  const [promptPreviewOpen, setPromptPreviewOpen] = useState(false);
  const [promptPreviewText, setPromptPreviewText] = useState("");
  const [sectionBrowserOpen, setSectionBrowserOpen] = useState(false);
  const [sectionMetaOpen, setSectionMetaOpen] = useState(false);
  const [contextPanelOpen, setContextPanelOpen] = useState(false);
  const [reviewPanelOpen, setReviewPanelOpen] = useState(false);
  const [assistantMenuOpen, setAssistantMenuOpen] = useState(false);
  const [sectionAssistantMenuOpen, setSectionAssistantMenuOpen] = useState(false);
  const [callTab, setCallTab] = useState<"repository" | "details" | "documents" | "templates" | "ask" | "findings">("repository");
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [inlineGenerating, setInlineGenerating] = useState(false);
  const [inlineGeneratedContent, setInlineGeneratedContent] = useState("");
  const [reviewFindings, setReviewFindings] = useState<ProposalReviewFinding[]>([]);
  const [callReviewFindings, setCallReviewFindings] = useState<ProposalReviewFinding[]>([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [callReviewBusy, setCallReviewBusy] = useState(false);
  const [callBriefBusy, setCallBriefBusy] = useState(false);
  const [callBrief, setCallBrief] = useState<ProposalCallBrief>(emptyCallBrief(selectedProjectId));
  const [callLibrary, setCallLibrary] = useState<ProposalCallLibraryEntry[]>([]);
  const [callLibraryBusy, setCallLibraryBusy] = useState(false);
  const [callLibrarySearch, setCallLibrarySearch] = useState("");
  const [newCallModalOpen, setNewCallModalOpen] = useState(false);
  const [newCallTitle, setNewCallTitle] = useState("");
  const [newCallFunder, setNewCallFunder] = useState("");
  const [newCallProgramme, setNewCallProgramme] = useState("");
  const [newCallReference, setNewCallReference] = useState("");
  const [newCallDeadline, setNewCallDeadline] = useState("");
  const [newCallSourceUrl, setNewCallSourceUrl] = useState("");
  const [newCallSummary, setNewCallSummary] = useState("");
  const [createFromPdfModalOpen, setCreateFromPdfModalOpen] = useState(false);
  const [callLibraryPdf, setCallLibraryPdf] = useState<File | null>(null);
  const [callLibrarySourceUrl, setCallLibrarySourceUrl] = useState("");
  const [callLibraryPdfCategory, setCallLibraryPdfCategory] = useState("main_call");
  const [confirmDeleteCallLibraryEntry, setConfirmDeleteCallLibraryEntry] = useState<ProposalCallLibraryEntry | null>(null);
  const [callIngestJob, setCallIngestJob] = useState<ProposalCallIngestJob | null>(null);
  const [callIngestTarget, setCallIngestTarget] = useState<"repository" | "documents">("repository");
  const [callDocuments, setCallDocuments] = useState<ProposalCallLibraryDocument[]>([]);
  const [callDocumentsBusy, setCallDocumentsBusy] = useState(false);
  const [callDocumentsFilter, setCallDocumentsFilter] = useState<"all" | "active" | "superseded">("active");
  const [addCallDocumentOpen, setAddCallDocumentOpen] = useState(false);
  const [editingCallDocument, setEditingCallDocument] = useState<ProposalCallLibraryDocument | null>(null);
  const [editingCallDocumentCategory, setEditingCallDocumentCategory] = useState("other");
  const [editingCallDocumentStatus, setEditingCallDocumentStatus] = useState("active");
  const [callQuestion, setCallQuestion] = useState("");
  const [callAnswer, setCallAnswer] = useState<ProposalCallAnswer | null>(null);
  const [callAskBusy, setCallAskBusy] = useState(false);
  const [templateEditorMode, setTemplateEditorMode] = useState<"closed" | "create" | "edit">("closed");
  const [templateFormName, setTemplateFormName] = useState("");
  const [templateFormFundingProgram, setTemplateFormFundingProgram] = useState("");
  const [templateFormDescription, setTemplateFormDescription] = useState("");
  const [templateFormIsActive, setTemplateFormIsActive] = useState(true);
  const [templateSectionKey, setTemplateSectionKey] = useState("");
  const [templateSectionTitle, setTemplateSectionTitle] = useState("");
  const [templateSectionGuidance, setTemplateSectionGuidance] = useState("");
  const [templateSectionPosition, setTemplateSectionPosition] = useState(1);
  const [templateSectionRequired, setTemplateSectionRequired] = useState(true);
  const [templateSectionScopeHint, setTemplateSectionScopeHint] = useState("project");
  const [editingTemplateSectionId, setEditingTemplateSectionId] = useState("");
  const [confirmDeleteTemplateOpen, setConfirmDeleteTemplateOpen] = useState(false);
  const [confirmAssignTemplateOpen, setConfirmAssignTemplateOpen] = useState(false);
  const saveTimerRef = useRef<number | null>(null);
  const latestDraftRef = useRef<{ sectionId: string; content: string; notes: string } | null>(null);
  const sectionsRef = useRef<ProjectProposalSection[]>([]);
  const lastContentChangeRemoteRef = useRef(false);
  const handledCallIngestJobIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);

  useEffect(() => {
    setTemplateId(project?.proposal_template_id || "");
  }, [project?.proposal_template_id]);

  useEffect(() => {
    if (!callBrief.source_call_id) {
      setTemplates([]);
      return;
    }
    api.listProposalTemplates("", true, callBrief.source_call_id)
      .then((res) => setTemplates(res.items))
      .catch(() => setTemplates([]));
  }, [callBrief.source_call_id]);

  useEffect(() => {
    if (!callBrief.source_call_id) {
      setCallDocuments([]);
      return;
    }
    setCallDocumentsBusy(true);
    api.listProposalCallLibraryDocuments(callBrief.source_call_id, true)
      .then((res) => setCallDocuments(res.items))
      .catch(() => setCallDocuments([]))
      .finally(() => setCallDocumentsBusy(false));
  }, [callBrief.source_call_id]);

  useEffect(() => {
    if (!callBrief.source_call_id) return;
    if (!callDocuments.some((item) => ["uploaded", "processing"].includes(item.indexing_status))) return;
    const timer = window.setInterval(() => {
      void refreshCallDocuments();
    }, 1800);
    return () => window.clearInterval(timer);
  }, [callBrief.source_call_id, callDocuments]);

  useEffect(() => {
    if (!selectedProjectId) {
      setMembers([]);
      setSections([]);
      setActiveSectionId("");
      setReviewFindings([]);
      setCallReviewFindings([]);
      setCallDocuments([]);
      setCallBrief(emptyCallBrief(""));
      return;
    }
    setBusy(true);
    setError("");
    Promise.all([
      api.listMembers(selectedProjectId),
      api.listProjectProposalSections(selectedProjectId),
      api.getProposalCallBrief(selectedProjectId).catch(() => emptyCallBrief(selectedProjectId)),
    ])
      .then(([membersRes, sectionsRes, callBriefRes]) => {
        setMembers(membersRes.items);
        setSections(sectionsRes.items);
        setActiveSectionId((current) => current || sectionsRes.items[0]?.id || "");
        setCallBrief(callBriefRes);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load proposal workspace."))
      .finally(() => setBusy(false));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      setReviewFindings([]);
      setCallReviewFindings([]);
      return;
    }
    api.listProposalReviewFindings(selectedProjectId, activeSectionId || undefined, "general")
      .then((res) => setReviewFindings(res.items))
      .catch(() => setReviewFindings([]));
    api.listProposalReviewFindings(selectedProjectId, activeSectionId || undefined, "call_compliance")
      .then((res) => setCallReviewFindings(res.items))
      .catch(() => setCallReviewFindings([]));
  }, [selectedProjectId, activeSectionId]);

  useEffect(() => {
    if (!selectedProjectId) {
      setCallLibrary([]);
      return;
    }
    setCallLibraryBusy(true);
    api.listProposalCallLibrary(callLibrarySearch)
      .then((res) => setCallLibrary(res.items))
      .catch(() => setCallLibrary([]))
      .finally(() => setCallLibraryBusy(false));
  }, [selectedProjectId, callLibrarySearch]);

  useEffect(() => {
    if (workspaceMode !== "call") return;
    setCallTab(callBrief.source_call_id ? "details" : "repository");
  }, [workspaceMode, callBrief.source_call_id]);

  useEffect(() => {
    if (!callIngestJob || !["queued", "processing"].includes(callIngestJob.status)) return;
    const timer = window.setInterval(() => {
      api.getProposalCallLibraryIngestJob(callIngestJob.id)
        .then((job) => setCallIngestJob(job))
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to refresh call extraction progress."));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [callIngestJob?.id, callIngestJob?.status]);

  useEffect(() => {
    if (!callIngestJob || callIngestJob.status !== "completed") return;
    if (handledCallIngestJobIdsRef.current.has(callIngestJob.id)) return;
    handledCallIngestJobIdsRef.current.add(callIngestJob.id);
    void (async () => {
      try {
        const libraryRes = await api.listProposalCallLibrary(callLibrarySearch);
        setCallLibrary(libraryRes.items);
        if (callIngestTarget === "repository") {
          const imported = await api.importProposalCallBrief(selectedProjectId, callIngestJob.library_entry_id);
          setCallBrief(imported);
          closeCreateFromPdfModal();
          setCallTab("details");
          setStatus("Call extracted from PDF.");
        } else {
          await refreshCallDocuments();
          closeAddCallDocumentModal();
          setStatus("Document processed.");
        }
        setCallLibraryPdf(null);
        setCallLibrarySourceUrl("");
        setCallIngestJob(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Call extraction finished, but the UI could not be updated.");
      }
    })();
  }, [callIngestJob, callIngestTarget, callLibrarySearch, selectedProjectId]);

  useEffect(() => {
    if (!callIngestJob || callIngestJob.status !== "failed") return;
    if (handledCallIngestJobIdsRef.current.has(callIngestJob.id)) return;
    handledCallIngestJobIdsRef.current.add(callIngestJob.id);
    setError(callIngestJob.error || "Failed to extract call from PDF.");
  }, [callIngestJob]);

  const memberNameById = useMemo(
    () => Object.fromEntries(members.map((member) => [member.id, member.full_name])),
    [members]
  );

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === templateId) || null,
    [templates, templateId]
  );
  const filteredCallDocuments = useMemo(() => {
    if (callDocumentsFilter === "all") return callDocuments;
    return callDocuments.filter((item) => item.status === callDocumentsFilter);
  }, [callDocuments, callDocumentsFilter]);

  useEffect(() => {
    if (templateEditorMode !== "edit" || !selectedTemplate) return;
    setTemplateFormName(selectedTemplate.name);
    setTemplateFormFundingProgram(selectedTemplate.funding_program);
    setTemplateFormDescription(selectedTemplate.description || "");
    setTemplateFormIsActive(selectedTemplate.is_active);
  }, [selectedTemplate, templateEditorMode]);

  const abstractSection = useMemo(
    () => sections.find((item) => item.key.toLowerCase() === "abstract" || item.key.toLowerCase() === "summary"),
    [sections]
  );

  const filteredSections = useMemo(() => {
    const query = search.trim().toLowerCase();
    return sections.filter((section) => {
      if (filter === "open" && ["approved", "final"].includes(section.status)) return false;
      if (filter === "needs_docs" && section.linked_documents_count > 0) return false;
      if (filter === "in_review" && section.status !== "in_review") return false;
      if (filter === "approved" && !["approved", "final"].includes(section.status)) return false;
      if (!query) return true;
      return [section.title, section.key, section.guidance || "", section.notes || "", section.content || ""].some((value) =>
        value.toLowerCase().includes(query)
      );
    });
  }, [sections, filter, search]);

  const activeSection = useMemo(
    () => sections.find((section) => section.id === activeSectionId) || filteredSections[0] || sections[0] || null,
    [sections, filteredSections, activeSectionId]
  );

  useEffect(() => {
    if (!activeSection) {
      setLocalContent("");
      setLocalNotes("");
      setSaveState("idle");
      latestDraftRef.current = null;
      return;
    }
    setActiveSectionId(activeSection.id);
    setLocalContent(activeSection.content || "");
    setLocalNotes(activeSection.notes || "");
    setSaveState("idle");
    latestDraftRef.current = {
      sectionId: activeSection.id,
      content: activeSection.content || "",
      notes: activeSection.notes || "",
    };
  }, [activeSection?.id, activeSection?.updated_at]);

  async function persistSectionDraft(sectionId: string, content: string, notes: string) {
    if (!selectedProjectId) return;
    const currentSection = sectionsRef.current.find((item) => item.id === sectionId);
    const serverContent = currentSection?.content || "";
    const serverNotes = currentSection?.notes || "";
    if (content === serverContent && notes === serverNotes) return;
    const updated = await api.updateProjectProposalSection(selectedProjectId, sectionId, {
      content: content || null,
      notes: notes || null,
      preserve_yjs_state: true,
    });
    setSections((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
  }

  function handleEditorContentChange(value: string, options?: { remote?: boolean }) {
    lastContentChangeRemoteRef.current = Boolean(options?.remote);
    setLocalContent(value);
  }

  useEffect(() => {
    if (!activeSection || !selectedProjectId) return;
    const serverContent = activeSection.content || "";
    const serverNotes = activeSection.notes || "";
    if (localContent === serverContent && localNotes === serverNotes) return;
    if (lastContentChangeRemoteRef.current) {
      lastContentChangeRemoteRef.current = false;
      setSaveState("idle");
      latestDraftRef.current = {
        sectionId: activeSection.id,
        content: localContent,
        notes: localNotes,
      };
      return;
    }
    latestDraftRef.current = {
      sectionId: activeSection.id,
      content: localContent,
      notes: localNotes,
    };
    setSaveState("dirty");
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = window.setTimeout(async () => {
      try {
        setSaveState("saving");
        await persistSectionDraft(activeSection.id, localContent, localNotes);
        setSaveState("saved");
      } catch (err) {
        setSaveState("error");
        setError(err instanceof Error ? err.message : "Failed to save section.");
      }
    }, 700);
    return () => {
      if (saveTimerRef.current) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [localContent, localNotes, activeSection?.id, activeSection?.content, activeSection?.notes, selectedProjectId]);

  useEffect(() => {
    return () => {
      const latestDraft = latestDraftRef.current;
      if (!latestDraft) return;
      void persistSectionDraft(latestDraft.sectionId, latestDraft.content, latestDraft.notes).catch((err) => {
        setSaveState("error");
        setError(err instanceof Error ? err.message : "Failed to save section.");
      });
    };
  }, [activeSection?.id, selectedProjectId]);

  async function handleAssignTemplate(overrideId?: string) {
    if (!project) return;
    const idToApply = overrideId !== undefined ? overrideId : templateId;
    try {
      setBusy(true);
      setError("");
      const updated = await api.updateProject(project.id, { proposal_template_id: idToApply || null });
      onProjectUpdated(updated);
      const sectionsRes = await api.listProjectProposalSections(project.id);
      setSections(sectionsRes.items);
      setActiveSectionId(sectionsRes.items[0]?.id || "");
      setStatus(idToApply ? "Template applied." : "Template cleared.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply template.");
    } finally {
      setBusy(false);
    }
  }

  function resetTemplateSectionForm() {
    setEditingTemplateSectionId("");
    setTemplateSectionKey("");
    setTemplateSectionTitle("");
    setTemplateSectionGuidance("");
    setTemplateSectionPosition(1);
    setTemplateSectionRequired(true);
    setTemplateSectionScopeHint("project");
  }

  function openCreateTemplateEditor() {
    setTemplateEditorMode("create");
    setTemplateFormName("");
    setTemplateFormFundingProgram(callBrief.programme_name || "");
    setTemplateFormDescription("");
    setTemplateFormIsActive(true);
    resetTemplateSectionForm();
  }

  function openEditTemplateEditor() {
    if (!selectedTemplate) return;
    setTemplateEditorMode("edit");
    setTemplateFormName(selectedTemplate.name);
    setTemplateFormFundingProgram(selectedTemplate.funding_program);
    setTemplateFormDescription(selectedTemplate.description || "");
    setTemplateFormIsActive(selectedTemplate.is_active);
    resetTemplateSectionForm();
  }

  async function handleSaveTemplateEditor() {
    if (!callBrief.source_call_id) return;
    try {
      setBusy(true);
      setError("");
      const payload = {
        call_library_entry_id: callBrief.source_call_id,
        name: templateFormName,
        funding_program: templateFormFundingProgram,
        description: templateFormDescription || null,
        is_active: templateFormIsActive,
      };
      const saved = templateEditorMode === "edit" && selectedTemplate
        ? await api.updateProposalTemplate(selectedTemplate.id, payload)
        : await api.createProposalTemplate(payload);
      setTemplates((prev) => {
        const next = prev.filter((item) => item.id !== saved.id);
        return [...next, saved].sort((a, b) => a.name.localeCompare(b.name));
      });
      setTemplateId(saved.id);
      setTemplateEditorMode("edit");
      setTemplateFormName(saved.name);
      setTemplateFormFundingProgram(saved.funding_program);
      setTemplateFormDescription(saved.description || "");
      setTemplateFormIsActive(saved.is_active);
      resetTemplateSectionForm();
      setStatus(templateEditorMode === "edit" ? "Template saved." : "Template created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save template.");
    } finally {
      setBusy(false);
    }
  }

  function startEditTemplateSection(section: ProposalTemplateSection) {
    setEditingTemplateSectionId(section.id);
    setTemplateSectionKey(section.key);
    setTemplateSectionTitle(section.title);
    setTemplateSectionGuidance(section.guidance || "");
    setTemplateSectionPosition(section.position);
    setTemplateSectionRequired(section.required);
    setTemplateSectionScopeHint(section.scope_hint);
  }

  async function handleSaveTemplateSection() {
    if (!selectedTemplate) return;
    try {
      setBusy(true);
      setError("");
      const payload = {
        key: templateSectionKey,
        title: templateSectionTitle,
        guidance: templateSectionGuidance || null,
        position: templateSectionPosition,
        required: templateSectionRequired,
        scope_hint: templateSectionScopeHint,
      };
      const updated = editingTemplateSectionId
        ? await api.updateProposalTemplateSection(selectedTemplate.id, editingTemplateSectionId, payload)
        : await api.createProposalTemplateSection(selectedTemplate.id, payload);
      setTemplates((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      resetTemplateSectionForm();
      setStatus(editingTemplateSectionId ? "Section saved." : "Section added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save section.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteTemplateSection(sectionId: string) {
    if (!selectedTemplate) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.deleteProposalTemplateSection(selectedTemplate.id, sectionId);
      setTemplates((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      if (editingTemplateSectionId === sectionId) {
        resetTemplateSectionForm();
      }
      setStatus("Section deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete section.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteTemplate() {
    if (!selectedTemplate) return;
    try {
      setBusy(true);
      setError("");
      await api.deleteProposalTemplate(selectedTemplate.id);
      setTemplates((prev) => prev.filter((item) => item.id !== selectedTemplate.id));
      if (templateId === selectedTemplate.id) {
        setTemplateId("");
      }
      if (selectedProjectId) {
        const sectionsRes = await api.listProjectProposalSections(selectedProjectId);
        setSections(sectionsRes.items);
      }
      if (project?.proposal_template_id === selectedTemplate.id) {
        onProjectUpdated({ ...project, proposal_template_id: null });
      }
      setTemplateEditorMode("closed");
      setConfirmDeleteTemplateOpen(false);
      resetTemplateSectionForm();
      setStatus("Template deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete template.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSectionMetaPatch(sectionId: string, patch: Partial<ProjectProposalSection>) {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.updateProjectProposalSection(selectedProjectId, sectionId, {
        status: patch.status,
        owner_member_id: Object.prototype.hasOwnProperty.call(patch, "owner_member_id") ? patch.owner_member_id : undefined,
        reviewer_member_id: Object.prototype.hasOwnProperty.call(patch, "reviewer_member_id") ? patch.reviewer_member_id : undefined,
        due_date: Object.prototype.hasOwnProperty.call(patch, "due_date") ? patch.due_date : undefined,
      });
      setSections((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setStatus(`Updated ${updated.title}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update section.");
    } finally {
      setBusy(false);
    }
  }

  function buildStructuredPrompt(task: string, section?: ProjectProposalSection): string {
    const activeSectionText = section
      ? [
          section.title,
          section.key,
          section.guidance || "",
          section.notes || "",
          section.id === activeSection?.id ? localContent : section.content || "",
          project?.description || "",
        ].join(" ")
      : project?.description || "";
    const activeTokens = new Set(tokenizeForMatch(activeSectionText));

    const relatedSections = section
      ? sections
          .filter((item) => item.id !== section.id && !!item.content?.trim())
          .map((item) => {
            const comparisonText = [item.title, item.key, item.guidance || "", item.notes || "", item.content || ""].join(" ");
            const comparisonTokens = tokenizeForMatch(comparisonText);
            const overlap = comparisonTokens.filter((token) => activeTokens.has(token)).length;
            const adjacencyBonus = Math.abs(item.position - section.position) <= 1 ? 2 : 0;
            const abstractBonus = item.key.toLowerCase() === "abstract" || item.key.toLowerCase() === "summary" ? 3 : 0;
            return { item, score: overlap + adjacencyBonus + abstractBonus };
          })
          .sort((a, b) => b.score - a.score)
          .slice(0, 3)
          .map((entry) => entry.item)
      : [];

    const sectionSummaries = sections
      .map((item) => {
        const summaryParts = [
          `key=${item.key}`,
          `title=${item.title}`,
          `status=${item.status}`,
          `required=${item.required ? "yes" : "no"}`,
          `scope_hint=${item.scope_hint}`,
          `owner=${item.owner_member_id ? memberNameById[item.owner_member_id] || item.owner_member_id : "none"}`,
          `reviewer=${item.reviewer_member_id ? memberNameById[item.reviewer_member_id] || item.reviewer_member_id : "none"}`,
          `docs=${item.linked_documents_count}`,
        ];
        if (item.content?.trim()) {
          summaryParts.push(`content_excerpt=${JSON.stringify(item.content.trim().slice(0, 400))}`);
        }
        if (item.notes?.trim()) {
          summaryParts.push(`notes=${JSON.stringify(item.notes.trim().slice(0, 240))}`);
        }
        return `- ${summaryParts.join(" | ")}`;
      })
      .join("\n");

    const focusSectionBlock = section
      ? [
          "FOCUS_SECTION",
          `key: ${section.key}`,
          `title: ${section.title}`,
          `status: ${section.status}`,
          `required: ${section.required ? "yes" : "no"}`,
          `scope_hint: ${section.scope_hint}`,
          `guidance: ${section.guidance || "-"}`,
          `owner: ${section.owner_member_id ? memberNameById[section.owner_member_id] || section.owner_member_id : "-"}`,
          `reviewer: ${section.reviewer_member_id ? memberNameById[section.reviewer_member_id] || section.reviewer_member_id : "-"}`,
          `due_date: ${section.due_date || "-"}`,
          `current_content: ${(section.id === activeSection?.id ? localContent : section.content)?.trim() || "-"}`,
          `notes: ${(section.id === activeSection?.id ? localNotes : section.notes)?.trim() || "-"}`,
        ].join("\n")
      : "";

    const relatedSectionsBlock = relatedSections.length > 0
      ? [
          "RELATED_SECTIONS_FULL_TEXT",
          ...relatedSections.map((item) =>
            [
              `SECTION ${item.key}`,
              `title: ${item.title}`,
              `status: ${item.status}`,
              `guidance: ${item.guidance || "-"}`,
              `content: ${item.content?.trim() || "-"}`,
            ].join("\n")
          ),
        ].join("\n\n")
      : "";

    const abstractBlock = abstractSection?.content?.trim()
      ? `PROJECT_ABSTRACT_REFERENCE\n${abstractSection.content.trim()}`
      : "PROJECT_ABSTRACT_REFERENCE\n-";

    const templateBlock = selectedTemplate
      ? [
          "TEMPLATE_CONTEXT",
          `name: ${selectedTemplate.name}`,
          `funding_program: ${selectedTemplate.funding_program}`,
          `description: ${selectedTemplate.description || "-"}`,
        ].join("\n")
      : "TEMPLATE_CONTEXT\nname: -\nfunding_program: -\ndescription: -";

    const callBlock = callBrief.call_title || callBrief.summary || callBrief.requirements_text || callBrief.scoring_notes
      ? [
          "CALL_CONTEXT",
          `call_title: ${callBrief.call_title || "-"}`,
          `funder_name: ${callBrief.funder_name || "-"}`,
          `programme_name: ${callBrief.programme_name || "-"}`,
          `reference_code: ${callBrief.reference_code || "-"}`,
          `submission_deadline: ${callBrief.submission_deadline || "-"}`,
          `source_url: ${callBrief.source_url || "-"}`,
          `summary: ${callBrief.summary?.trim() || "-"}`,
          `eligibility_notes: ${callBrief.eligibility_notes?.trim() || "-"}`,
          `budget_notes: ${callBrief.budget_notes?.trim() || "-"}`,
          `scoring_notes: ${callBrief.scoring_notes?.trim() || "-"}`,
          `requirements_text: ${callBrief.requirements_text?.trim() || "-"}`,
        ].join("\n")
      : "CALL_CONTEXT\ncall_title: -";

    const languageBlock = languageInstruction(project?.language);

    return [
      "You are assisting with proposal drafting.",
      "Use the structured project context below. Do not invent missing project facts. If information is missing, state the gap clearly and make the minimum reasonable drafting assumption.",
      languageBlock,
      "",
      "TASK",
      task,
      "",
      "PROJECT_CONTEXT",
      `code: ${project?.code || "-"}`,
      `title: ${project?.title || "-"}`,
      `language: ${project?.language || "en_GB"}`,
      `mode: ${project?.project_mode || "proposal"}`,
      `start_date: ${project?.start_date || "-"}`,
      `duration_months: ${project?.duration_months ?? "-"}`,
      `description: ${project?.description?.trim() || "-"}`,
      "",
      templateBlock,
      "",
      callBlock,
      "",
      abstractBlock,
      "",
      "PROPOSAL_SECTIONS_OVERVIEW",
      sectionSummaries || "-",
      focusSectionBlock ? `\n${focusSectionBlock}\n` : "",
      relatedSectionsBlock ? `\n${relatedSectionsBlock}\n` : "",
      "OUTPUT_REQUIREMENTS",
      "- Keep the response grounded in the provided project context.",
      "- Maintain consistency with the project description and existing section content.",
      "- If drafting text, produce text ready to refine in the proposal editor.",
      "- If proposing structure, return a concrete structure, not generic advice.",
    ]
      .filter(Boolean)
      .join("\n");
  }

  function openPromptPreview(prompt: string) {
    setPromptPreviewText(prompt);
    setPromptPreviewOpen(true);
  }

  function navigateToAssistantWithPrompt(prompt: string) {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(ASSISTANT_PENDING_PROMPT_KEY, prompt);
    }
    onNavigateToAssistant?.();
  }

  async function handleCopyPrompt() {
    if (!promptPreviewText) return;
    try {
      await navigator.clipboard.writeText(promptPreviewText);
      setStatus("Prompt copied.");
    } catch {
      setError("Failed to copy prompt.");
    }
  }

  async function handleInlineGenerate() {
    if (!promptPreviewText || !selectedProjectId) return;
    setPromptPreviewOpen(false);
    setInlineGenerating(true);
    setInlineGeneratedContent("");
    try {
      const conversation = await api.createChatConversation(selectedProjectId, { title: "Proposal AI generation" });
      await api.postChatMessageStream(
        selectedProjectId,
        conversation.id,
        { content: promptPreviewText },
        {
          onStart: () => {},
          onToken: (token) => {
            setInlineGeneratedContent((prev) => prev + token);
          },
          onDone: () => {
            setInlineGenerating(false);
          },
          onError: (detail) => {
            setInlineGenerating(false);
            setError(detail);
          },
        }
      );
    } catch (err) {
      setInlineGenerating(false);
      setError(err instanceof Error ? err.message : "Failed to generate content.");
    }
  }

  function handleAcceptGenerated() {
    setLocalContent((prev) => (prev ? prev + "\n\n" + inlineGeneratedContent : inlineGeneratedContent));
    setInlineGeneratedContent("");
    setSaveState("dirty");
  }

  function handleDiscardGenerated() {
    setInlineGeneratedContent("");
  }

  function handleDraftAbstract() {
    openPromptPreview(
      buildStructuredPrompt(
        "Draft the project abstract using the project context. Produce a concise, submission-ready abstract that covers objectives, innovation, methodology, and expected impact. If critical information is missing, identify the missing points after the draft."
      )
    );
  }

  function handleGenerateWBS() {
    openPromptPreview(
      buildStructuredPrompt(
        "Propose a complete work breakdown structure with work packages, tasks, deliverables, and milestones. Keep it consistent with the project description and existing proposal state. Return a concrete structure with short rationale for each work package."
      )
    );
  }

  function handleSectionAIAssist(section: ProjectProposalSection) {
    openPromptPreview(
      buildStructuredPrompt(
        `Draft or improve the proposal section "${section.title}" (${section.key}). Follow the section guidance, keep terminology aligned with the rest of the proposal, and produce text suitable for direct editing in the proposal workspace.`,
        section
      )
    );
  }

  async function loadReviewFindings(sectionId?: string) {
    if (!selectedProjectId) return;
    const res = await api.listProposalReviewFindings(selectedProjectId, sectionId || undefined, "general");
    setReviewFindings(res.items);
  }

  async function loadCallReviewFindings(sectionId?: string) {
    if (!selectedProjectId) return;
    const res = await api.listProposalReviewFindings(selectedProjectId, sectionId || undefined, "call_compliance");
    setCallReviewFindings(res.items);
  }

  async function handleRunReview(scope: "section" | "proposal") {
    if (!selectedProjectId) return;
    setReviewBusy(true);
    setError("");
    try {
      const result = await api.runProposalReview(selectedProjectId, scope === "section" ? activeSection?.id : null);
      await loadReviewFindings(activeSection?.id);
      setReviewPanelOpen(true);
      setStatus(
        result.created.length > 0
          ? `${result.created.length} review finding${result.created.length !== 1 ? "s" : ""} created.`
          : "Review completed with no findings."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run review.");
    } finally {
      setReviewBusy(false);
    }
  }

  async function saveCallBriefDraft(): Promise<ProposalCallBrief> {
    if (!selectedProjectId) {
      throw new Error("No project selected.");
    }
    const updated = await api.upsertProposalCallBrief(selectedProjectId, {
      call_title: callBrief.call_title || null,
      funder_name: callBrief.funder_name || null,
      programme_name: callBrief.programme_name || null,
      reference_code: callBrief.reference_code || null,
      submission_deadline: callBrief.submission_deadline || null,
      source_url: callBrief.source_url || null,
      summary: callBrief.summary || null,
      eligibility_notes: callBrief.eligibility_notes || null,
      budget_notes: callBrief.budget_notes || null,
      scoring_notes: callBrief.scoring_notes || null,
      requirements_text: callBrief.requirements_text || null,
    });
    setCallBrief(updated);
    return updated;
  }

  async function handleSaveCallBrief() {
    if (!selectedProjectId) return;
    setCallBriefBusy(true);
    setError("");
    try {
      await saveCallBriefDraft();
      setStatus("Call saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save call.");
    } finally {
      setCallBriefBusy(false);
    }
  }

  async function handleRunCallCompliance(scope: "section" | "proposal") {
    if (!selectedProjectId) return;
    setCallReviewBusy(true);
    setError("");
    try {
      await saveCallBriefDraft();
      const result = await api.runProposalCallCompliance(selectedProjectId, scope === "section" ? activeSection?.id : null);
      await loadCallReviewFindings(activeSection?.id);
      setStatus(
        result.created.length > 0
          ? `${result.created.length} call finding${result.created.length !== 1 ? "s" : ""} created.`
          : "Call check completed with no findings."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run call check.");
    } finally {
      setCallReviewBusy(false);
    }
  }

  async function handleImportCallFromLibrary(libraryEntryId: string) {
    if (!selectedProjectId) return;
    setCallBriefBusy(true);
    setError("");
    try {
      const updated = await api.importProposalCallBrief(selectedProjectId, libraryEntryId);
      setCallBrief(updated);
      setCallTab("details");
      setStatus("Call copied to project.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to copy call.");
    } finally {
      setCallBriefBusy(false);
    }
  }

  async function handleCreateLibraryEntryFromBrief() {
    if (!callBrief.call_title?.trim()) {
      setError("Call title is required.");
      return;
    }
    setCallBriefBusy(true);
    setError("");
    try {
      const created = await api.createProposalCallLibraryEntry({
        call_title: callBrief.call_title.trim(),
        funder_name: callBrief.funder_name || null,
        programme_name: callBrief.programme_name || null,
        reference_code: callBrief.reference_code || null,
        submission_deadline: callBrief.submission_deadline || null,
        source_url: callBrief.source_url || null,
        summary: callBrief.summary || null,
        eligibility_notes: callBrief.eligibility_notes || null,
        budget_notes: callBrief.budget_notes || null,
        scoring_notes: callBrief.scoring_notes || null,
        requirements_text: callBrief.requirements_text || null,
        is_active: true,
      });
      setCallLibrary((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      const imported = await api.importProposalCallBrief(selectedProjectId, created.id);
      setCallBrief(imported);
      setCallTab("repository");
      setStatus("Call added to repository.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add call.");
    } finally {
      setCallBriefBusy(false);
    }
  }

  async function handleIngestLibraryPdf(targetLibraryEntryId?: string | null, target: "repository" | "documents" = "repository") {
    if (!callLibraryPdf) {
      setError("Select a PDF first.");
      return;
    }
    setError("");
    try {
      const job = await api.startProposalCallLibraryIngestJob(callLibraryPdf, {
        library_entry_id: targetLibraryEntryId || undefined,
        source_url: callLibrarySourceUrl || null,
        category: callLibraryPdfCategory,
      });
      setCallIngestTarget(target);
      setCallIngestJob(job);
      setStatus("Call extraction started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to ingest PDF.");
    }
  }

  async function handleDeleteCallLibraryEntry() {
    if (!confirmDeleteCallLibraryEntry) return;
    try {
      setBusy(true);
      setError("");
      await api.deleteProposalCallLibraryEntry(confirmDeleteCallLibraryEntry.id);
      setCallLibrary((prev) => prev.filter((item) => item.id !== confirmDeleteCallLibraryEntry.id));
      setConfirmDeleteCallLibraryEntry(null);
      setStatus("Call deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete call.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateRepositoryCall() {
    if (!newCallTitle.trim()) {
      setError("Call title is required.");
      return;
    }
    try {
      setBusy(true);
      setError("");
      const created = await api.createProposalCallLibraryEntry({
        call_title: newCallTitle.trim(),
        funder_name: newCallFunder || null,
        programme_name: newCallProgramme || null,
        reference_code: newCallReference || null,
        submission_deadline: newCallDeadline || null,
        source_url: newCallSourceUrl || null,
        summary: newCallSummary || null,
        is_active: true,
      });
      setCallLibrary((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      closeNewCallModal();
      setStatus("Call created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create call.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshCallDocuments() {
    if (!callBrief.source_call_id) {
      setCallDocuments([]);
      return;
    }
    setCallDocumentsBusy(true);
    try {
      const res = await api.listProposalCallLibraryDocuments(callBrief.source_call_id, true);
      setCallDocuments(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load call documents.");
    } finally {
      setCallDocumentsBusy(false);
    }
  }

  async function handleSupersedeCallDocument(documentId: string) {
    if (!callBrief.source_call_id) return;
    setCallDocumentsBusy(true);
    setError("");
    try {
      await api.updateProposalCallLibraryDocument(callBrief.source_call_id, documentId, { status: "superseded" });
      await refreshCallDocuments();
      setStatus("Document superseded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update document.");
    } finally {
      setCallDocumentsBusy(false);
    }
  }

  async function handleActivateCallDocument(documentId: string) {
    if (!callBrief.source_call_id) return;
    setCallDocumentsBusy(true);
    setError("");
    try {
      await api.updateProposalCallLibraryDocument(callBrief.source_call_id, documentId, { status: "active" });
      await refreshCallDocuments();
      setStatus("Document activated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update document.");
    } finally {
      setCallDocumentsBusy(false);
    }
  }

  async function handleDeleteCallDocument(documentId: string) {
    if (!callBrief.source_call_id) return;
    setCallDocumentsBusy(true);
    setError("");
    try {
      await api.deleteProposalCallLibraryDocument(callBrief.source_call_id, documentId);
      setCallDocuments((current) => current.filter((item) => item.id !== documentId));
      setStatus("Document deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document.");
    } finally {
      setCallDocumentsBusy(false);
    }
  }

  async function handleReindexCallDocument(documentId: string) {
    if (!callBrief.source_call_id) return;
    setCallDocumentsBusy(true);
    setError("");
    try {
      await api.reindexProposalCallLibraryDocument(callBrief.source_call_id, documentId);
      await refreshCallDocuments();
      setStatus("Document queued for re-index.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to re-index document.");
    } finally {
      setCallDocumentsBusy(false);
    }
  }

  function openCallDocumentEditor(document: ProposalCallLibraryDocument) {
    setEditingCallDocument(document);
    setEditingCallDocumentCategory(document.category || "other");
    setEditingCallDocumentStatus(document.status || "active");
  }

  function closeCallDocumentEditor() {
    setEditingCallDocument(null);
    setEditingCallDocumentCategory("other");
    setEditingCallDocumentStatus("active");
  }

  function openNewCallModal() {
    setNewCallModalOpen(true);
  }

  function closeNewCallModal() {
    setNewCallModalOpen(false);
    setNewCallTitle("");
    setNewCallFunder("");
    setNewCallProgramme("");
    setNewCallReference("");
    setNewCallDeadline("");
    setNewCallSourceUrl("");
    setNewCallSummary("");
  }

  function openCreateFromPdfModal() {
    setCallLibraryPdf(null);
    setCallLibrarySourceUrl("");
    setCallLibraryPdfCategory("main_call");
    setCreateFromPdfModalOpen(true);
  }

  function closeCreateFromPdfModal() {
    if (callIngestTarget === "repository" && callIngestJob && ["queued", "processing"].includes(callIngestJob.status)) return;
    setCreateFromPdfModalOpen(false);
    setCallLibraryPdf(null);
    setCallLibrarySourceUrl("");
    setCallLibraryPdfCategory("main_call");
    if (callIngestTarget === "repository" && callIngestJob?.status !== "failed") {
      setCallIngestJob(null);
    }
  }

  function openAddCallDocumentModal() {
    setCallLibraryPdf(null);
    setCallLibrarySourceUrl("");
    setCallLibraryPdfCategory("main_call");
    setAddCallDocumentOpen(true);
  }

  function closeAddCallDocumentModal() {
    setAddCallDocumentOpen(false);
    setCallLibraryPdf(null);
    setCallLibrarySourceUrl("");
    setCallLibraryPdfCategory("main_call");
  }

  async function handleSaveCallDocumentMetadata() {
    if (!callBrief.source_call_id || !editingCallDocument) return;
    setCallDocumentsBusy(true);
    setError("");
    try {
      const updated = await api.updateProposalCallLibraryDocument(callBrief.source_call_id, editingCallDocument.id, {
        category: editingCallDocumentCategory,
        status: editingCallDocumentStatus,
      });
      setCallDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      closeCallDocumentEditor();
      setStatus("Document updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update document.");
    } finally {
      setCallDocumentsBusy(false);
    }
  }

  async function handleResolveFinding(finding: ProposalReviewFinding, nextStatus: string) {
    if (!selectedProjectId) return;
    try {
      const updated = await api.updateProposalReviewFinding(selectedProjectId, finding.id, {
        review_kind: finding.review_kind,
        finding_type: finding.finding_type,
        status: nextStatus,
        source: finding.source,
        scope: finding.scope,
        summary: finding.summary,
        details: finding.details,
        anchor_text: finding.anchor_text,
        anchor_prefix: finding.anchor_prefix,
        anchor_suffix: finding.anchor_suffix,
        start_offset: finding.start_offset,
        end_offset: finding.end_offset,
      });
      if (finding.review_kind === "call_compliance") {
        setCallReviewFindings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        setReviewFindings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update review finding.");
    }
  }

  async function handleAskCallQuestion() {
    if (!selectedProjectId) return;
    if (!callQuestion.trim()) {
      setError("Question cannot be empty.");
      return;
    }
    try {
      setCallAskBusy(true);
      setError("");
      const answer = await api.askProposalCallQuestion(selectedProjectId, callQuestion.trim());
      setCallAnswer(answer);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to ask question about the call.");
    } finally {
      setCallAskBusy(false);
    }
  }

  async function handleCreateComment(anchorText: string, anchorPrefix: string, anchorSuffix: string, summary: string) {
    if (!selectedProjectId || !activeSection) return;
    const memberEntry = members.find((m) => m.user_account_id === currentUser?.id);
    try {
      await api.createProposalReviewFinding(selectedProjectId, {
        proposal_section_id: activeSection.id,
        finding_type: "comment",
        status: "open",
        source: "manual",
        scope: "anchor",
        summary,
        anchor_text: anchorText,
        anchor_prefix: anchorPrefix,
        anchor_suffix: anchorSuffix,
        created_by_member_id: memberEntry?.id || null,
      });
      await loadReviewFindings(activeSection.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create comment.");
    }
  }

  async function handleReplyToFinding(parentId: string, summary: string) {
    if (!selectedProjectId || !activeSection) return;
    const memberEntry = members.find((m) => m.user_account_id === currentUser?.id);
    try {
      await api.createProposalReviewFinding(selectedProjectId, {
        proposal_section_id: activeSection.id,
        finding_type: "comment",
        status: "open",
        source: "manual",
        scope: "anchor",
        summary,
        parent_finding_id: parentId,
        created_by_member_id: memberEntry?.id || null,
      });
      await loadReviewFindings(activeSection.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reply.");
    }
  }

  async function handleDeleteFinding(findingId: string) {
    if (!selectedProjectId) return;
    try {
      await api.deleteProposalReviewFinding(selectedProjectId, findingId);
      await loadReviewFindings(activeSection?.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete finding.");
    }
  }

  const completedSections = sections.filter((section) => ["approved", "final"].includes(section.status)).length;
  const reviewSections = sections.filter((section) => section.status === "in_review").length;
  const missingDocsCount = sections.filter((section) => section.required && section.linked_documents_count === 0).length;
  const activeWordCount = wordCount(localContent);
  const proposalHasStarted = sections.some(
    (section) =>
      Boolean(section.content?.trim()) ||
      Boolean(section.notes?.trim()) ||
      section.status !== "not_started" ||
      section.linked_documents_count > 0
  );
  const ownerName = activeSection?.owner_member_id ? memberNameById[activeSection.owner_member_id] || "Unknown" : "None";
  const reviewerName = activeSection?.reviewer_member_id ? memberNameById[activeSection.reviewer_member_id] || "Unknown" : "None";
  const activeSectionFindings = reviewFindings.filter(
    (item) => item.proposal_section_id === activeSection?.id && item.scope !== "proposal"
  );
  const anchoredFindings = activeSectionFindings.filter((item) => item.scope === "anchor");
  const broadSectionFindings = activeSectionFindings.filter((item) => item.scope !== "anchor");
  const proposalWideFindings = reviewFindings.filter((item) => item.scope === "proposal");
  const activeCallFindings = callReviewFindings.filter(
    (item) => item.proposal_section_id === activeSection?.id && item.scope !== "proposal"
  );
  const sectionCallFindings = activeCallFindings.filter((item) => item.scope !== "anchor");
  const proposalWideCallFindings = callReviewFindings.filter((item) => item.scope === "proposal");
  const callFindingCount = sectionCallFindings.length + proposalWideCallFindings.length;
  const callConfigured = Boolean(
    callBrief.call_title ||
    callBrief.summary ||
    callBrief.requirements_text ||
    callBrief.scoring_notes ||
    callBrief.eligibility_notes
  );
  const callReady = Boolean(callBrief.source_call_id || callConfigured);
  const templateReady = Boolean(project?.proposal_template_id);
  const onboardingStep = !callReady ? "call" : !templateReady ? "template" : "proposal";
  const callIngestProgressPercent = callIngestJob?.progress_total
    ? Math.min(100, Math.round((callIngestJob.progress_current / callIngestJob.progress_total) * 100))
    : callIngestJob?.status === "completed"
      ? 100
      : 0;
  const callIngestEtaSeconds = (() => {
    if (!callIngestJob?.started_at || !callIngestJob.progress_total || callIngestJob.progress_current <= 0) return null;
    const elapsedSeconds = Math.max(1, (Date.now() - new Date(callIngestJob.started_at).getTime()) / 1000);
    const secondsPerChunk = elapsedSeconds / callIngestJob.progress_current;
    return Math.max(0, Math.round(secondsPerChunk * (callIngestJob.progress_total - callIngestJob.progress_current)));
  })();
  const activeSourceCall = callBrief.source_call_id ? callLibrary.find((item) => item.id === callBrief.source_call_id) || null : null;
  const repositoryJobActive = callIngestTarget === "repository" && Boolean(callIngestJob);
  const activeSectionIndex = activeSection ? filteredSections.findIndex((item) => item.id === activeSection.id) : -1;
  const previousSection = activeSectionIndex > 0 ? filteredSections[activeSectionIndex - 1] : null;
  const nextSection =
    activeSectionIndex >= 0 && activeSectionIndex < filteredSections.length - 1
      ? filteredSections[activeSectionIndex + 1]
      : null;

  if (!selectedProjectId || !project) {
    return <p className="muted-small">Select a project to start.</p>;
  }

  function renderCallWorkspace() {
    function renderCallIngestJobCard() {
      if (!callIngestJob) return null;
      return (
        <div className="proposal-call-job-card">
          <div className="proposal-call-job-head">
            <strong>
              {callIngestJob.stage === "queued"
                ? "Queued"
                : callIngestJob.stage === "extracting_text"
                  ? "Extracting text"
                  : callIngestJob.stage === "processing_chunks"
                    ? "Processing chunks"
                    : callIngestJob.stage === "reducing"
                      ? "Reducing results"
                      : callIngestJob.stage === "completed"
                        ? "Completed"
                        : "Failed"}
            </strong>
            <span>
              {callIngestJob.progress_total
                ? `${callIngestJob.progress_current}/${callIngestJob.progress_total} chunks`
                : "Preparing"}
            </span>
          </div>
          <div className="proposal-call-job-progress">
            <div className="proposal-call-job-progress-bar" style={{ width: `${callIngestProgressPercent}%` }} />
          </div>
          <div className="proposal-call-job-meta">
            <span>{callIngestProgressPercent}%</span>
            <span>{callIngestEtaSeconds !== null ? `ETA ${formatDuration(callIngestEtaSeconds)}` : "ETA -"}</span>
          </div>
          {callIngestJob.stream_text ? (
            <div className="proposal-call-job-stream">
              <pre>{callIngestJob.stream_text}</pre>
            </div>
          ) : null}
          {callIngestJob.error ? <div className="proposal-call-job-error">{callIngestJob.error}</div> : null}
        </div>
      );
    }

    return (
      <div className="card proposal-editor-card proposal-call-page-card">
        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <strong>{callBrief.call_title?.trim() || "No call"}</strong>
            <span className="setup-summary-sep" />
            <span>{callBrief.reference_code || "No reference"}</span>
            <span className="setup-summary-sep" />
            <span>{callBrief.submission_deadline || "No deadline"}</span>
            <span className="setup-summary-sep" />
            <span className={`chip small ${callReady ? "status-ok" : ""}`}>{callReady ? "Call ready" : "Call required"}</span>
            <span className={`chip small ${templateReady ? "status-ok" : ""}`}>{templateReady ? "Template assigned" : "Template pending"}</span>
            <span className={`chip small ${project?.proposal_template_id ? "status-ok" : ""}`}>{project?.proposal_template_id ? "Proposal unlocked" : "Proposal locked"}</span>
          </div>
        </div>

        <div className="delivery-tabs">
          <button type="button" className={`delivery-tab ${callTab === "repository" ? "active" : ""}`} onClick={() => setCallTab("repository")}>
            Repository
            <span className="delivery-tab-count">{callLibrary.length}</span>
          </button>
          <button type="button" className={`delivery-tab ${callTab === "details" ? "active" : ""}`} onClick={() => setCallTab("details")}>
            Details
          </button>
          <button type="button" className={`delivery-tab ${callTab === "documents" ? "active" : ""}`} onClick={() => setCallTab("documents")}>
            Documents
            {callDocuments.length > 0 ? <span className="delivery-tab-count">{callDocuments.length}</span> : null}
          </button>
          <button type="button" className={`delivery-tab ${callTab === "templates" ? "active" : ""}`} onClick={() => setCallTab("templates")}>
            Templates
            {templates.length > 0 ? <span className="delivery-tab-count">{templates.length}</span> : null}
          </button>
          <span className="delivery-tab-sep" />
          <button type="button" className={`delivery-tab ${callTab === "ask" ? "active" : ""}`} onClick={() => setCallTab("ask")}>
            Ask
          </button>
          <button type="button" className={`delivery-tab ${callTab === "findings" ? "active" : ""}`} onClick={() => setCallTab("findings")}>
            Findings
            {callFindingCount > 0 ? <span className="delivery-tab-count">{callFindingCount}</span> : null}
          </button>
          <div className="delivery-tab-action">
            <button type="button" className="meetings-new-btn" onClick={() => void handleSaveCallBrief()} disabled={callBriefBusy}>
              {callBriefBusy ? "Saving..." : "Save"}
            </button>
            {currentUser?.platform_role === "super_admin" ? (
              <button type="button" className="ghost" onClick={() => void handleCreateLibraryEntryFromBrief()} disabled={callBriefBusy}>
                Add to Repository
              </button>
            ) : null}
            {templateReady ? (
              <button type="button" className="ghost" onClick={() => onNavigateToProposal?.()}>
                <FontAwesomeIcon icon={faFileLines} /> Open Proposal
              </button>
            ) : null}
            <span className="setup-summary-sep" />
            <button type="button" className="ghost" onClick={() => { setCallTab("findings"); void handleRunCallCompliance("section"); }} disabled={callReviewBusy || !activeSection}>
              <FontAwesomeIcon icon={faBolt} /> {callReviewBusy ? "Checking..." : "Check Section"}
            </button>
            <button type="button" className="ghost" onClick={() => { setCallTab("findings"); void handleRunCallCompliance("proposal"); }} disabled={callReviewBusy}>
              <FontAwesomeIcon icon={faBolt} /> {callReviewBusy ? "Checking..." : "Check Proposal"}
            </button>
          </div>
        </div>

        {callTab === "repository" ? (
          <div className="call-tab-content">
            <div className="setup-summary-bar">
              <div className="setup-summary-stats">
                <span>{callLibraryBusy ? "Loading" : `${callLibrary.length} calls`}</span>
                <span className="setup-summary-sep" />
                <span>{callBrief.source_call_id ? "Source selected" : "No source selected"}</span>
                {activeSourceCall?.reference_code ? (
                  <>
                    <span className="setup-summary-sep" />
                    <strong>{activeSourceCall.reference_code}</strong>
                  </>
                ) : null}
              </div>
              {currentUser?.platform_role === "super_admin" ? (
                <div className="proposal-repository-actions">
                  <button type="button" className="ghost" onClick={openNewCallModal}>
                    <FontAwesomeIcon icon={faPlus} /> New Call
                  </button>
                  <button type="button" className="meetings-new-btn" onClick={openCreateFromPdfModal}>
                    <FontAwesomeIcon icon={faFilePdf} /> Create From PDF
                  </button>
                </div>
              ) : null}
            </div>
            <div className="meetings-toolbar">
              <div className="meetings-filter-group">
                <input
                  className="meetings-search proposal-call-library-search"
                  value={callLibrarySearch}
                  onChange={(event) => setCallLibrarySearch(event.target.value)}
                  placeholder="Search calls"
                />
              </div>
            </div>
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Title</th>
                    <th>Funder</th>
                    <th>Programme</th>
                    <th>Deadline</th>
                    <th>Ver</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {callLibrary.map((item) => {
                    const isCurrent = item.id === callBrief.source_call_id;
                    return (
                      <tr key={item.id} className={isCurrent ? "row-selected" : ""}>
                        <td><span className="chip small">{item.reference_code || "—"}</span></td>
                        <td><strong>{item.call_title}</strong></td>
                        <td>{item.funder_name || "—"}</td>
                        <td>{item.programme_name || "—"}</td>
                        <td>{item.submission_deadline || "—"}</td>
                        <td><span className="delivery-tab-count">v{item.version}</span></td>
                        <td>
                          <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                            <button
                              type="button"
                              className={isCurrent ? "ghost" : "meetings-new-btn"}
                              style={{ fontSize: 11, padding: "3px 8px" }}
                              onClick={() => { if (!callBriefBusy && !isCurrent) void handleImportCallFromLibrary(item.id); }}
                              disabled={callBriefBusy || isCurrent}
                            >
                              {isCurrent ? "In Use" : "Use"}
                            </button>
                            {currentUser?.platform_role === "super_admin" ? (
                              <button
                                type="button"
                                className="ghost docs-action-btn"
                                onClick={() => setConfirmDeleteCallLibraryEntry(item)}
                                title="Delete Call"
                              >
                                <FontAwesomeIcon icon={faTrash} />
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {!callLibraryBusy && callLibrary.length === 0 ? (
                    <tr>
                      <td colSpan={7}>
                        <div className="proposal-empty-action">
                          <p>{currentUser?.platform_role === "super_admin" ? "No calls in the repository yet. Create one manually or upload a PDF." : "No calls available. Ask an administrator to add calls to the repository."}</p>
                          {currentUser?.platform_role === "super_admin" ? (
                            <div style={{ display: "flex", gap: 6 }}>
                              <button type="button" className="ghost" onClick={openNewCallModal}>
                                <FontAwesomeIcon icon={faPlus} /> New Call
                              </button>
                              <button type="button" className="meetings-new-btn" onClick={openCreateFromPdfModal}>
                                <FontAwesomeIcon icon={faFilePdf} /> Create From PDF
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {callTab === "details" ? (
          <div className="call-tab-content">
            {callBrief.source_call_id ? (
              <>
                <div className="form-grid proposal-call-grid">
                  <label className="full-span">
                    Call Title
                    <input value={callBrief.call_title || ""} onChange={(event) => setCallBrief((current) => ({ ...current, call_title: event.target.value }))} placeholder="Full title of the funding call" />
                  </label>
                  <label>
                    Funder
                    <input value={callBrief.funder_name || ""} onChange={(event) => setCallBrief((current) => ({ ...current, funder_name: event.target.value }))} placeholder="e.g. European Commission" />
                  </label>
                  <label>
                    Programme
                    <input value={callBrief.programme_name || ""} onChange={(event) => setCallBrief((current) => ({ ...current, programme_name: event.target.value }))} placeholder="e.g. Horizon Europe" />
                  </label>
                  <label>
                    Reference Code
                    <input value={callBrief.reference_code || ""} onChange={(event) => setCallBrief((current) => ({ ...current, reference_code: event.target.value }))} placeholder="e.g. HORIZON-CL4-2026-01" />
                  </label>
                  <label>
                    Submission Deadline
                    <input type="date" value={callBrief.submission_deadline || ""} onChange={(event) => setCallBrief((current) => ({ ...current, submission_deadline: event.target.value || null }))} />
                  </label>
                  <label className="full-span">
                    Source URL
                    <input value={callBrief.source_url || ""} onChange={(event) => setCallBrief((current) => ({ ...current, source_url: event.target.value }))} placeholder="Link to the call page" />
                  </label>
                  <label className="full-span">
                    Summary
                    <textarea rows={4} value={callBrief.summary || ""} onChange={(event) => setCallBrief((current) => ({ ...current, summary: event.target.value }))} placeholder="Brief description of the call scope, objectives, and expected outcomes" />
                  </label>
                </div>

                <div className="call-details-section-head">Assessment</div>
                <div className="call-assessment-grid">
                  <label>
                    <strong>Eligibility</strong>
                    <textarea rows={6} value={callBrief.eligibility_notes || ""} onChange={(event) => setCallBrief((current) => ({ ...current, eligibility_notes: event.target.value }))} placeholder="Consortium composition rules, country requirements, TRL levels, etc." />
                  </label>
                  <label>
                    <strong>Budget</strong>
                    <textarea rows={6} value={callBrief.budget_notes || ""} onChange={(event) => setCallBrief((current) => ({ ...current, budget_notes: event.target.value }))} placeholder="Funding rate, budget ceiling, cost categories, co-financing, etc." />
                  </label>
                  <label>
                    <strong>Scoring Criteria</strong>
                    <textarea rows={6} value={callBrief.scoring_notes || ""} onChange={(event) => setCallBrief((current) => ({ ...current, scoring_notes: event.target.value }))} placeholder="Evaluation criteria, weights, thresholds, etc." />
                  </label>
                  <label>
                    <strong>Requirements</strong>
                    <textarea rows={6} value={callBrief.requirements_text || ""} onChange={(event) => setCallBrief((current) => ({ ...current, requirements_text: event.target.value }))} placeholder="Mandatory deliverables, page limits, formatting rules, etc." />
                  </label>
                </div>
              </>
            ) : (
              <div className="proposal-empty-action">
                <p>No call linked to this project yet.</p>
                <button type="button" className="meetings-new-btn" onClick={() => setCallTab("repository")}>
                  <FontAwesomeIcon icon={faFolderOpen} /> Go to Repository
                </button>
              </div>
            )}
          </div>
        ) : null}

        {callTab === "documents" ? (
          <div className="call-tab-content">
            {callBrief.source_call_id ? (
              <div className="proposal-call-documents-layout">
                <div className="proposal-call-documents-toolbar">
                  <div className="meetings-filter-group">
                    <select value={callDocumentsFilter} onChange={(event) => setCallDocumentsFilter(event.target.value as "all" | "active" | "superseded")}>
                      <option value="active">Active</option>
                      <option value="superseded">Superseded</option>
                      <option value="all">All</option>
                    </select>
                  </div>
                  {currentUser?.platform_role === "super_admin" ? (
                    <button type="button" className="meetings-new-btn" onClick={openAddCallDocumentModal}>
                      <FontAwesomeIcon icon={faPlus} /> Add Document
                    </button>
                  ) : null}
                </div>

                <div className="simple-table-wrap">
                  <table className="simple-table compact-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Document</th>
                        <th>Status</th>
                        <th>Indexing</th>
                        <th>Added</th>
                        <th>Size</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {filteredCallDocuments.map((document) => (
                        <tr key={document.id}>
                          <td><span className="chip small">{callDocumentCategoryLabel(document.category)}</span></td>
                          <td><strong>{document.original_filename}</strong></td>
                          <td><span className={`chip small ${document.status === "active" ? "status-ok" : ""}`}>{document.status}</span></td>
                          <td>
                            <span className={`chip small ${document.indexing_status === "indexed" ? "status-ok" : document.indexing_status === "failed" ? "status-danger" : ""}`}>
                              {callDocumentIndexingLabel(document.indexing_status)}
                            </span>
                          </td>
                          <td>{new Date(document.created_at).toLocaleDateString()}</td>
                          <td>{formatFileSize(document.file_size_bytes)}</td>
                          <td>
                            <div className="proposal-call-document-actions">
                              <a
                                className="ghost docs-action-btn"
                                href={`${import.meta.env.VITE_API_BASE}/proposal-call-library/${document.library_entry_id}/documents/${document.id}/content`}
                                target="_blank"
                                rel="noreferrer"
                                title="Open"
                              >
                                <FontAwesomeIcon icon={faArrowUpRightFromSquare} />
                              </a>
                              {currentUser?.platform_role === "super_admin" ? (
                                <>
                                  <button
                                    type="button"
                                    className="ghost docs-action-btn"
                                    title="Edit"
                                    onClick={() => openCallDocumentEditor(document)}
                                    disabled={callDocumentsBusy}
                                  >
                                    <FontAwesomeIcon icon={faPen} />
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost docs-action-btn"
                                    title="Re-index"
                                    onClick={() => void handleReindexCallDocument(document.id)}
                                    disabled={callDocumentsBusy}
                                  >
                                    <FontAwesomeIcon icon={faRotate} />
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost docs-action-btn"
                                    title={document.status === "active" ? "Supersede" : "Activate"}
                                    onClick={() => void (document.status === "active" ? handleSupersedeCallDocument(document.id) : handleActivateCallDocument(document.id))}
                                    disabled={callDocumentsBusy}
                                  >
                                    <FontAwesomeIcon icon={document.status === "active" ? faBoxArchive : faCheck} />
                                  </button>
                                  <button
                                    type="button"
                                    className="ghost docs-action-btn"
                                    title="Delete"
                                    onClick={() => void handleDeleteCallDocument(document.id)}
                                    disabled={callDocumentsBusy}
                                  >
                                    <FontAwesomeIcon icon={faTrash} />
                                  </button>
                                </>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!callDocumentsBusy && filteredCallDocuments.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="muted-small">No documents</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="proposal-empty-action">
                <p>No call linked to this project yet.</p>
                <button type="button" className="meetings-new-btn" onClick={() => setCallTab("repository")}>
                  <FontAwesomeIcon icon={faFolderOpen} /> Go to Repository
                </button>
              </div>
            )}
          </div>
        ) : null}

        {callTab === "templates" ? (
          <div className="call-tab-content">
            {callBrief.source_call_id ? (
              <>
                <div className="meetings-toolbar">
                  <div className="meetings-filter-group">
                    <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>{templates.length} template{templates.length !== 1 ? "s" : ""}</span>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button type="button" disabled={busy || !templateId} onClick={() => setConfirmAssignTemplateOpen(true)}>
                      <FontAwesomeIcon icon={faCheck} /> Use Template
                    </button>
                    {currentUser?.platform_role === "super_admin" ? (
                      <>
                        <button type="button" className="ghost docs-action-btn" onClick={openCreateTemplateEditor} disabled={busy} title="New Template">
                          <FontAwesomeIcon icon={faPlus} />
                        </button>
                        <button type="button" className="ghost docs-action-btn" onClick={openEditTemplateEditor} disabled={busy || !selectedTemplate} title="Edit Template">
                          <FontAwesomeIcon icon={faPen} />
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>
                <div className="simple-table-wrap">
                  <table className="simple-table compact-table">
                    <thead>
                      <tr>
                        <th></th>
                        <th>Name</th>
                        <th>Program</th>
                        <th>Sections</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {templates.map((template) => (
                        <tr
                          key={template.id}
                          className={template.id === templateId ? "row-selected" : ""}
                          onClick={() => setTemplateId(template.id)}
                          style={{ cursor: "pointer" }}
                        >
                          <td style={{ width: 28 }}>
                            <input
                              type="radio"
                              name="call-template"
                              checked={template.id === templateId}
                              onChange={() => setTemplateId(template.id)}
                              style={{ accentColor: "var(--brand)" }}
                            />
                          </td>
                          <td><strong>{template.name}</strong></td>
                          <td>{template.funding_program}</td>
                          <td>{template.sections.length}</td>
                          <td><span className="chip small">{template.is_active ? "active" : "inactive"}</span></td>
                        </tr>
                      ))}
                      {templates.length === 0 ? (
                        <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)" }}>No templates</td></tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="proposal-empty-action">
                <p>No call linked to this project yet.</p>
                <button type="button" className="meetings-new-btn" onClick={() => setCallTab("repository")}>
                  <FontAwesomeIcon icon={faFolderOpen} /> Go to Repository
                </button>
              </div>
            )}
          </div>
        ) : null}

        {templateEditorMode !== "closed" && currentUser?.platform_role === "super_admin" ? (
          <div className="modal-overlay" role="dialog" aria-modal="true">
            <div className="modal-card settings-modal-card" onKeyDown={(e) => { if (e.key === "Escape") { setTemplateEditorMode("closed"); resetTemplateSectionForm(); } }}>
              <div className="modal-head">
                <h3>{templateEditorMode === "create" ? "New Template" : "Edit Template"}</h3>
                <button type="button" className="ghost docs-action-btn" onClick={() => { setTemplateEditorMode("closed"); resetTemplateSectionForm(); }} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
              </div>

              <div className="form-grid">
                <label>
                  Name
                  <input value={templateFormName} onChange={(event) => setTemplateFormName(event.target.value)} />
                </label>
                <label>
                  Funding Program
                  <input value={templateFormFundingProgram} onChange={(event) => setTemplateFormFundingProgram(event.target.value)} />
                </label>
                <label className="full-span">
                  Description
                  <textarea rows={2} value={templateFormDescription} onChange={(event) => setTemplateFormDescription(event.target.value)} />
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={templateFormIsActive} onChange={(event) => setTemplateFormIsActive(event.target.checked)} />
                  <span>Active</span>
                </label>
              </div>
              <div className="row-actions">
                <button
                  type="button"
                  disabled={busy || !templateFormName.trim() || !templateFormFundingProgram.trim()}
                  onClick={() => void handleSaveTemplateEditor()}
                >
                  {templateEditorMode === "create" ? "Create Template" : "Save Template"}
                </button>
                {templateEditorMode === "edit" && selectedTemplate ? (
                  <button type="button" className="danger" disabled={busy} onClick={() => setConfirmDeleteTemplateOpen(true)}>
                    Delete Template
                  </button>
                ) : null}
              </div>

              {selectedTemplate && templateEditorMode === "edit" ? (
                <>
                  <div style={{ borderTop: "1px solid var(--line)", margin: "4px 0 0" }} />
                  <div style={{ padding: "0 14px" }}>
                    <div className="proposal-call-template-editor-head">
                      <strong>Sections</strong>
                    </div>
                  </div>
                  <div className="simple-table-wrap" style={{ padding: "0 14px" }}>
                    <table className="simple-table compact-table">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Key</th>
                          <th>Scope</th>
                          <th>Pos</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedTemplate.sections.map((section) => (
                          <tr key={section.id}>
                            <td><strong>{section.title}</strong></td>
                            <td>{section.key}</td>
                            <td>{section.scope_hint}</td>
                            <td>{section.position}</td>
                            <td style={{ textAlign: "right" }}>
                              <button type="button" className="ghost docs-action-btn" onClick={() => startEditTemplateSection(section)} disabled={busy} title="Edit">
                                <FontAwesomeIcon icon={faPen} />
                              </button>
                              <button type="button" className="ghost docs-action-btn" onClick={() => void handleDeleteTemplateSection(section.id)} disabled={busy} title="Delete">
                                <FontAwesomeIcon icon={faTrash} />
                              </button>
                            </td>
                          </tr>
                        ))}
                        {selectedTemplate.sections.length === 0 ? (
                          <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)" }}>No sections yet</td></tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>

                  <div style={{ padding: "0 14px 14px" }}>
                    <div className="proposal-call-template-editor-head" style={{ marginBottom: 8 }}>
                      <strong>{editingTemplateSectionId ? "Edit Section" : "Add Section"}</strong>
                      {editingTemplateSectionId ? (
                        <button type="button" className="ghost docs-action-btn" onClick={resetTemplateSectionForm} disabled={busy}>Cancel</button>
                      ) : null}
                    </div>
                    <div className="form-grid">
                      <label>
                        Key
                        <input value={templateSectionKey} onChange={(event) => setTemplateSectionKey(event.target.value)} />
                      </label>
                      <label>
                        Title
                        <input value={templateSectionTitle} onChange={(event) => setTemplateSectionTitle(event.target.value)} />
                      </label>
                      <label>
                        Position
                        <input type="number" min={1} value={templateSectionPosition} onChange={(event) => setTemplateSectionPosition(Number(event.target.value) || 1)} />
                      </label>
                      <label>
                        Scope
                        <select value={templateSectionScopeHint} onChange={(event) => setTemplateSectionScopeHint(event.target.value)}>
                          <option value="project">Project</option>
                          <option value="wp">WP</option>
                          <option value="task">Task</option>
                          <option value="deliverable">Deliverable</option>
                          <option value="milestone">Milestone</option>
                        </select>
                      </label>
                      <label className="full-span">
                        Guidance
                        <textarea rows={3} value={templateSectionGuidance} onChange={(event) => setTemplateSectionGuidance(event.target.value)} />
                      </label>
                      <label className="checkbox-label">
                        <input type="checkbox" checked={templateSectionRequired} onChange={(event) => setTemplateSectionRequired(event.target.checked)} />
                        <span>Required</span>
                      </label>
                    </div>
                    <div className="row-actions">
                      <button
                        type="button"
                        disabled={busy || !templateSectionKey.trim() || !templateSectionTitle.trim()}
                        onClick={() => void handleSaveTemplateSection()}
                      >
                        {editingTemplateSectionId ? "Save Section" : "Add Section"}
                      </button>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        ) : null}

        {confirmDeleteTemplateOpen && selectedTemplate ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setConfirmDeleteTemplateOpen(false); }}>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>Delete Template</h3>
                <button type="button" className="ghost docs-action-btn" onClick={() => setConfirmDeleteTemplateOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
              </div>
              <div className="project-confirm-body">
                <strong>{selectedTemplate.name}</strong>
                <span>{selectedTemplate.funding_program}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setConfirmDeleteTemplateOpen(false)} disabled={busy}>
                  Cancel
                </button>
                <button type="button" className="danger" onClick={() => void handleDeleteTemplate()} disabled={busy}>
                  Delete
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {confirmAssignTemplateOpen && selectedTemplate ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setConfirmAssignTemplateOpen(false); }}>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>Apply Template</h3>
                <button type="button" className="ghost docs-action-btn" onClick={() => setConfirmAssignTemplateOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
              </div>
              <div className="project-confirm-body">
                <p>This will create <strong>{selectedTemplate.sections.length} proposal section{selectedTemplate.sections.length !== 1 ? "s" : ""}</strong> from template <strong>{selectedTemplate.name}</strong>.</p>
                <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>Existing sections will not be removed.</p>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setConfirmAssignTemplateOpen(false)} disabled={busy}>
                  Cancel
                </button>
                <button type="button" onClick={() => { setConfirmAssignTemplateOpen(false); void handleAssignTemplate(); }} disabled={busy}>
                  Apply Template
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {confirmDeleteCallLibraryEntry ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setConfirmDeleteCallLibraryEntry(null); }}>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>Delete Call</h3>
                <button type="button" className="ghost docs-action-btn" onClick={() => setConfirmDeleteCallLibraryEntry(null)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
              </div>
              <div className="project-confirm-body">
                <strong>{confirmDeleteCallLibraryEntry.call_title}</strong>
                <span>{confirmDeleteCallLibraryEntry.reference_code || confirmDeleteCallLibraryEntry.programme_name || "Repository call"}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setConfirmDeleteCallLibraryEntry(null)} disabled={busy}>
                  Cancel
                </button>
                <button type="button" className="danger" onClick={() => void handleDeleteCallLibraryEntry()} disabled={busy}>
                  Delete
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {newCallModalOpen ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeNewCallModal(); }}>
            <FocusLock returnFocus>
              <div className="modal-card settings-modal-card">
              <div className="modal-head">
                <h3>New Call</h3>
                <button type="button" className="ghost docs-action-btn" onClick={closeNewCallModal} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
              </div>
              <div className="form-grid">
                <label className="full-span">
                  Title
                  <input value={newCallTitle} onChange={(event) => setNewCallTitle(event.target.value)} />
                </label>
                <label>
                  Funder
                  <input value={newCallFunder} onChange={(event) => setNewCallFunder(event.target.value)} />
                </label>
                <label>
                  Programme
                  <input value={newCallProgramme} onChange={(event) => setNewCallProgramme(event.target.value)} />
                </label>
                <label>
                  Reference
                  <input value={newCallReference} onChange={(event) => setNewCallReference(event.target.value)} />
                </label>
                <label>
                  Deadline
                  <input type="date" value={newCallDeadline} onChange={(event) => setNewCallDeadline(event.target.value)} />
                </label>
                <label className="full-span">
                  Source URL
                  <input value={newCallSourceUrl} onChange={(event) => setNewCallSourceUrl(event.target.value)} />
                </label>
                <label className="full-span">
                  Summary
                  <textarea rows={5} value={newCallSummary} onChange={(event) => setNewCallSummary(event.target.value)} />
                </label>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={closeNewCallModal} disabled={busy}>Cancel</button>
                <button type="button" onClick={() => void handleCreateRepositoryCall()} disabled={busy || !newCallTitle.trim()}>
                  Create
                </button>
              </div>
              </div>
            </FocusLock>
          </div>
        ) : null}

        {createFromPdfModalOpen ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeCreateFromPdfModal(); }}>
            <FocusLock returnFocus>
              <div className="modal-card settings-modal-card">
              <div className="modal-head">
                <h3>Create Call From PDF</h3>
                <button type="button" className="ghost docs-action-btn" onClick={closeCreateFromPdfModal} disabled={repositoryJobActive} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
              </div>
              <div className="form-grid">
                <label className="full-span">
                  Call PDF
                  <input
                    type="file"
                    accept="application/pdf"
                    className="proposal-call-file-input"
                    onChange={(event) => setCallLibraryPdf(event.target.files?.[0] || null)}
                  />
                </label>
                <label>
                  Category
                  <select value={callLibraryPdfCategory} onChange={(event) => setCallLibraryPdfCategory(event.target.value)}>
                    {CALL_DOCUMENT_CATEGORIES.map((category) => (
                      <option key={category.value} value={category.value}>{category.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Source URL
                  <input value={callLibrarySourceUrl} onChange={(event) => setCallLibrarySourceUrl(event.target.value)} />
                </label>
              </div>
              {repositoryJobActive ? renderCallIngestJobCard() : null}
              <div className="row-actions">
                <button type="button" className="ghost" onClick={closeCreateFromPdfModal} disabled={busy || repositoryJobActive}>Cancel</button>
                <button
                  type="button"
                  onClick={() => void handleIngestLibraryPdf()}
                  disabled={repositoryJobActive || !callLibraryPdf}
                >
                  {repositoryJobActive ? "Processing..." : "Create"}
                </button>
              </div>
              </div>
            </FocusLock>
          </div>
        ) : null}

        {callTab === "ask" ? (
          <div className="call-tab-content">
            {callBrief.source_call_id ? (
              <>
                {callDocuments.length > 0 && callDocuments.some((d) => d.indexing_status === "uploaded" || d.indexing_status === "processing") ? (
                  <div className="call-indexing-warning">
                    <FontAwesomeIcon icon={faRotate} className="fa-spin" /> Some documents are still being indexed. Answers may be incomplete.
                  </div>
                ) : null}
                {callDocuments.length === 0 ? (
                  <div className="call-indexing-warning">
                    No documents uploaded yet. Upload call documents in the Documents tab for better answers.
                  </div>
                ) : null}
                <div className="proposal-call-ask-form">
                  <textarea
                    rows={3}
                    value={callQuestion}
                    onChange={(event) => setCallQuestion(event.target.value)}
                    placeholder="Ask a question about the call requirements, eligibility, scoring criteria..."
                  />
                  <div className="row-actions">
                    <button type="button" disabled={callAskBusy || !callQuestion.trim()} onClick={() => void handleAskCallQuestion()}>
                      {callAskBusy ? "Asking..." : "Ask"}
                    </button>
                  </div>
                </div>

                {callAnswer ? (
                  <div className="proposal-call-answer-section">
                    <div className="proposal-call-answer-head">
                      <span className={`chip small ${callAnswer.grounded ? "status-ok" : "status-warning"}`}>
                        {callAnswer.grounded ? "grounded" : "insufficient"}
                      </span>
                    </div>
                    <div className="proposal-call-answer-text chat-markdown">
                      {renderMarkdown(callAnswer.answer)}
                    </div>
                    {callAnswer.insufficient_reason ? (
                      <div className="proposal-call-answer-note">{callAnswer.insufficient_reason}</div>
                    ) : null}
                    {callAnswer.citations.length > 0 ? (
                      <div className="proposal-call-answer-citations">
                        {callAnswer.citations.map((citation, index) => (
                          <a
                            key={`${citation.document_id}:${citation.chunk_index}`}
                            id={`call-citation-${index + 1}`}
                            className="proposal-call-answer-citation"
                            href={`${import.meta.env.VITE_API_BASE}/proposal-call-library/${citation.library_entry_id}/documents/${citation.document_id}/content`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <span className="proposal-call-answer-ref">[{index + 1}]</span>
                            <strong>{citation.document_title}</strong>
                            <span>Chunk {citation.chunk_index}</span>
                            <p>{citation.snippet}</p>
                          </a>
                        ))}
                      </div>
                    ) : null}
                    {callAnswer.retrieval_debug.length > 0 ? (
                      <div className="proposal-call-answer-citations">
                        {callAnswer.retrieval_debug.map((citation) => (
                          <div
                            key={`debug:${citation.document_id}:${citation.chunk_index}`}
                            className="proposal-call-answer-citation proposal-call-answer-debug"
                          >
                            <strong>{citation.document_title}</strong>
                            <span>
                              Chunk {citation.chunk_index} · lexical {citation.lexical_score.toFixed(2)} · vector {citation.vector_score.toFixed(2)} · combined {citation.combined_score.toFixed(2)}
                            </span>
                            <p>{citation.snippet}</p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="proposal-empty-action">
                <p>No call linked to this project yet.</p>
                <button type="button" className="meetings-new-btn" onClick={() => setCallTab("repository")}>
                  <FontAwesomeIcon icon={faFolderOpen} /> Go to Repository
                </button>
              </div>
            )}
          </div>
        ) : null}

        {callTab === "findings" ? (
          <div className="call-tab-content">
            {sectionCallFindings.length > 0 ? (
              <div className="proposal-review-group">
                <strong>Section Findings</strong>
                <div className="proposal-review-list">
                  {sectionCallFindings.map((item) => (
                    <div key={item.id} className={`proposal-review-item ${item.finding_type}`} data-status={item.status}>
                      <div className="proposal-review-item-head">
                        <strong>{item.summary}</strong>
                        <button type="button" className="ghost docs-action-btn" onClick={() => void handleResolveFinding(item, item.status === "resolved" ? "open" : "resolved")}>
                          {item.status === "resolved" ? "Reopen" : "Resolve"}
                        </button>
                      </div>
                      {item.details ? <p>{item.details}</p> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {proposalWideCallFindings.length > 0 ? (
              <div className="proposal-review-group">
                <strong>Proposal Findings</strong>
                <div className="proposal-review-list">
                  {proposalWideCallFindings.map((item) => (
                    <div key={item.id} className={`proposal-review-item ${item.finding_type}`} data-status={item.status}>
                      <div className="proposal-review-item-head">
                        <strong>{item.summary}</strong>
                        <button type="button" className="ghost docs-action-btn" onClick={() => void handleResolveFinding(item, item.status === "resolved" ? "open" : "resolved")}>
                          {item.status === "resolved" ? "Reopen" : "Resolve"}
                        </button>
                      </div>
                      {item.details ? <p>{item.details}</p> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {!callReviewBusy && sectionCallFindings.length === 0 && proposalWideCallFindings.length === 0 ? (
              <div className="proposal-empty-action">
                <p>No call compliance findings yet. Run a check to find issues.</p>
                <div style={{ display: "flex", gap: 6 }}>
                  <button type="button" className="meetings-new-btn" onClick={() => void handleRunCallCompliance("section")} disabled={callReviewBusy || !activeSection}>
                    <FontAwesomeIcon icon={faBolt} /> Check Section
                  </button>
                  <button type="button" className="meetings-new-btn" onClick={() => void handleRunCallCompliance("proposal")} disabled={callReviewBusy}>
                    <FontAwesomeIcon icon={faBolt} /> Check Proposal
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  function renderCallDocumentModals() {
    return (
      <>
        {addCallDocumentOpen ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeAddCallDocumentModal(); }}>
            <FocusLock returnFocus>
              <div className="modal-card proposal-call-document-modal-card">
                <div className="modal-head">
                  <h3>Add Document</h3>
                  <button type="button" className="ghost" onClick={closeAddCallDocumentModal}>
                    Close
                  </button>
                </div>
                <div className="form-grid">
                  <label className="full-span">
                    File
                    <input type="file" accept="application/pdf" onChange={(event) => setCallLibraryPdf(event.target.files?.[0] || null)} />
                  </label>
                  <label>
                    Category
                    <select value={callLibraryPdfCategory} onChange={(event) => setCallLibraryPdfCategory(event.target.value)}>
                      {CALL_DOCUMENT_CATEGORIES.map((category) => (
                        <option key={category.value} value={category.value}>{category.label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Source URL
                    <input value={callLibrarySourceUrl} onChange={(event) => setCallLibrarySourceUrl(event.target.value)} />
                  </label>
                </div>
                <div className="row-actions">
                  <button
                    type="button"
                    onClick={() => void handleIngestLibraryPdf(callBrief.source_call_id, "documents")}
                    disabled={(callIngestJob?.status === "queued" || callIngestJob?.status === "processing") || !callLibraryPdf}
                  >
                    {callIngestJob?.status === "queued" || callIngestJob?.status === "processing" ? "Processing..." : "Add"}
                  </button>
                </div>
              </div>
            </FocusLock>
          </div>
        ) : null}

        {editingCallDocument ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) closeCallDocumentEditor(); }}>
            <FocusLock returnFocus>
              <div className="modal-card proposal-call-document-modal-card">
                <div className="modal-head">
                  <h3>{editingCallDocument.original_filename}</h3>
                  <button type="button" className="ghost" onClick={closeCallDocumentEditor}>
                    Close
                  </button>
                </div>
                <div className="form-grid">
                  <label>
                    Category
                    <select value={editingCallDocumentCategory} onChange={(event) => setEditingCallDocumentCategory(event.target.value)}>
                      {CALL_DOCUMENT_CATEGORIES.map((category) => (
                        <option key={category.value} value={category.value}>{category.label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Status
                    <select value={editingCallDocumentStatus} onChange={(event) => setEditingCallDocumentStatus(event.target.value)}>
                      <option value="active">Active</option>
                      <option value="superseded">Superseded</option>
                    </select>
                  </label>
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => void handleSaveCallDocumentMetadata()} disabled={callDocumentsBusy}>
                    {callDocumentsBusy ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            </FocusLock>
          </div>
        ) : null}
      </>
    );
  }

  if (workspaceMode === "call") {
    return (
      <>
        {error ? <p className="error">{error}</p> : null}
        {status ? <p className="success">{status}</p> : null}
        {renderCallWorkspace()}
        {renderCallDocumentModals()}
      </>
    );
  }

  return (
    <>
      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          {proposalHasStarted ? (
            <span className="proposal-template-inline">
              <span>{selectedTemplate ? `${selectedTemplate.funding_program} · ${selectedTemplate.name}` : "No template"}</span>
              <span className="chip small">locked</span>
            </span>
          ) : (
            <span className="proposal-template-inline">
              <select value={templateId} disabled={busy} onChange={(event) => { setTemplateId(event.target.value); void handleAssignTemplate(event.target.value); }}>
                <option value="">No template</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.funding_program} · {template.name}
                  </option>
                ))}
              </select>
            </span>
          )}
          <span className="setup-summary-sep" />
          <span><strong>{sections.length}</strong> sections</span>
          <span className="setup-summary-sep" />
          <span><strong>{completedSections}</strong> approved</span>
          <span className="setup-summary-sep" />
          <span><strong>{activeWordCount}</strong> words</span>
        </div>
        <div className="proposal-summary-actions">
          <div style={{ position: "relative" }}>
            <button type="button" className="ghost" disabled={busy} onClick={() => setAssistantMenuOpen((o) => !o)}>
              <FontAwesomeIcon icon={faPaperPlane} /> Assistant <FontAwesomeIcon icon={faChevronDown} className="meetings-toggle-chevron" />
            </button>
            {assistantMenuOpen ? (
              <>
                <div style={{ position: "fixed", inset: 0, zIndex: 19 }} onClick={() => setAssistantMenuOpen(false)} />
                <div className="proposal-table-dropdown" style={{ right: 0, left: "auto" }}>
                  <button type="button" onClick={() => { setAssistantMenuOpen(false); handleDraftAbstract(); }}>
                    <FontAwesomeIcon icon={faFileLines} /> Draft Abstract
                  </button>
                  <button type="button" disabled={!abstractSection?.content} onClick={() => { setAssistantMenuOpen(false); handleGenerateWBS(); }}>
                    <FontAwesomeIcon icon={faListCheck} /> Generate WBS
                  </button>
                </div>
              </>
            ) : null}
          </div>
          <button
            type="button"
            className="meetings-new-btn"
            disabled={busy || !sections.length}
            onClick={async () => {
              try {
                setBusy(true);
                const blob = await api.exportProposalPdf(selectedProjectId);
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `${project?.code || "proposal"}-proposal.pdf`;
                a.click();
                URL.revokeObjectURL(url);
              } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "PDF export failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            <FontAwesomeIcon icon={faFilePdf} /> Export PDF
          </button>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      {/* Prompt preview modal */}
      {promptPreviewOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setPromptPreviewOpen(false); }}>
          <FocusLock returnFocus>
          <div className="modal-card settings-modal-card">
            <div className="modal-head">
              <h3>LLM Prompt</h3>
              <button type="button" className="ghost" onClick={() => setPromptPreviewOpen(false)}>
                Close
              </button>
            </div>
            <label className="full-span">
              Prompt
              <textarea rows={20} value={promptPreviewText} readOnly />
            </label>
            <div className="row-actions">
              <button type="button" className="ghost" onClick={() => void handleCopyPrompt()}>
                <FontAwesomeIcon icon={faCopy} /> Copy
              </button>
              <button
                type="button"
                onClick={() => void handleInlineGenerate()}
                disabled={inlineGenerating}
              >
                <FontAwesomeIcon icon={faBolt} /> Generate
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setPromptPreviewOpen(false);
                  navigateToAssistantWithPrompt(promptPreviewText);
                }}
              >
                <FontAwesomeIcon icon={faPaperPlane} /> Open in Assistant
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}

      {/* Section browser modal */}
      {sectionBrowserOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setSectionBrowserOpen(false); }}>
          <FocusLock returnFocus>
            <div className="modal-card settings-modal-card">
              <div className="modal-head">
                <h3>Sections</h3>
                <button type="button" className="ghost" onClick={() => setSectionBrowserOpen(false)}>
                  Close
                </button>
              </div>
              <div className="meetings-toolbar">
                <div className="meetings-filter-group">
                  <select value={filter} onChange={(event) => setFilter(event.target.value as SectionFilter)}>
                    <option value="all">All</option>
                    <option value="open">Open</option>
                    <option value="needs_docs">Needs Docs</option>
                    <option value="in_review">In Review</option>
                    <option value="approved">Approved</option>
                  </select>
                  <input
                    className="meetings-search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search sections"
                  />
                </div>
              </div>
              <div className="simple-table-wrap proposal-section-browser-scroll">
                <table className="simple-table compact-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Title</th>
                      <th>Key</th>
                      <th>Status</th>
                      <th>Docs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSections.map((section) => (
                      <tr
                        key={section.id}
                        className={section.id === activeSection?.id ? "row-selected" : ""}
                        onClick={() => {
                          setActiveSectionId(section.id);
                          setSectionBrowserOpen(false);
                        }}
                      >
                        <td>{section.position}</td>
                        <td><strong>{section.title}</strong></td>
                        <td><span className="chip small">{section.key}</span></td>
                        <td><span className={statusChipClass(section.status)}>{section.status.replace(/_/g, " ")}</span></td>
                        <td>{section.linked_documents_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!busy && filteredSections.length === 0 ? <div className="proposal-empty">No sections</div> : null}
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}

      {/* Section meta modal */}
      {sectionMetaOpen && activeSection ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setSectionMetaOpen(false); }}>
          <FocusLock returnFocus>
            <div className="modal-card settings-modal-card">
              <div className="modal-head">
                <h3>Section</h3>
                <button type="button" className="ghost" onClick={() => setSectionMetaOpen(false)}>
                  Close
                </button>
              </div>
              <div className="form-grid">
                <label>
                  Status
                  <select
                    value={activeSection.status}
                    onChange={(event) => void handleSectionMetaPatch(activeSection.id, { status: event.target.value })}
                  >
                    {STATUS_OPTIONS.map((item) => (
                      <option key={item} value={item}>{item.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Due Date
                  <input
                    type="date"
                    value={activeSection.due_date || ""}
                    onChange={(event) => void handleSectionMetaPatch(activeSection.id, { due_date: event.target.value || null })}
                  />
                </label>
                <label>
                  Owner
                  <select
                    value={activeSection.owner_member_id || ""}
                    onChange={(event) =>
                      void handleSectionMetaPatch(activeSection.id, { owner_member_id: event.target.value || null })
                    }
                  >
                    <option value="">None</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>{member.full_name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Reviewer
                  <select
                    value={activeSection.reviewer_member_id || ""}
                    onChange={(event) =>
                      void handleSectionMetaPatch(activeSection.id, { reviewer_member_id: event.target.value || null })
                    }
                  >
                    <option value="">None</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>{member.full_name}</option>
                    ))}
                  </select>
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={6} value={localNotes} onChange={(event) => setLocalNotes(event.target.value)} />
                </label>
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}

      {/* Context modal */}
      {contextPanelOpen && activeSection ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setContextPanelOpen(false); }}>
          <FocusLock returnFocus>
            <div className="modal-card settings-modal-card">
              <div className="modal-head">
                <h3>Context</h3>
                <button type="button" className="ghost" onClick={() => setContextPanelOpen(false)}>
                  Close
                </button>
              </div>
              <div className="proposal-context-grid">
                <div className="proposal-context-item">
                  <span className="meetings-source-icon">
                    <FontAwesomeIcon icon={faFolderOpen} />
                  </span>
                  <div>
                    <strong>{selectedTemplate ? `${selectedTemplate.funding_program} · ${selectedTemplate.name}` : "No template"}</strong>
                  </div>
                </div>
                <div className="proposal-context-item">
                  <span className="meetings-source-icon">
                    <FontAwesomeIcon icon={faUsersRectangle} />
                  </span>
                  <div>
                    <span className="muted-small">Owner</span>
                    <strong>{ownerName}</strong>
                  </div>
                </div>
                <div className="proposal-context-item">
                  <span className="meetings-source-icon">
                    <FontAwesomeIcon icon={faUserCheck} />
                  </span>
                  <div>
                    <span className="muted-small">Reviewer</span>
                    <strong>{reviewerName}</strong>
                  </div>
                </div>
                <div className="proposal-context-item">
                  <span className="meetings-source-icon">
                    <FontAwesomeIcon icon={faCheck} />
                  </span>
                  <div>
                    <strong>{activeSection.linked_documents_count} linked docs</strong>
                  </div>
                </div>
                <div className="proposal-context-item">
                  <span className="meetings-source-icon">
                    <FontAwesomeIcon icon={faCalendarDay} />
                  </span>
                  <div>
                    <strong>{activeSection.due_date || "No due date"}</strong>
                  </div>
                </div>
                <div className="proposal-context-item">
                  <span className="meetings-source-icon">
                    <FontAwesomeIcon icon={faBolt} />
                  </span>
                  <div>
                    <strong>{project.language ? LANGUAGE_LABELS[project.language] || project.language : "English (UK)"}</strong>
                  </div>
                </div>
                {activeSection.guidance ? (
                  <div className="meetings-detail-section">
                    <button
                      type="button"
                      className={`meetings-assistant-toggle ${guidanceOpen ? "open" : ""}`}
                      onClick={() => setGuidanceOpen((prev) => !prev)}
                    >
                      <FontAwesomeIcon icon={faFileLines} />
                      <span>Guidance</span>
                      <FontAwesomeIcon icon={faChevronDown} className="meetings-toggle-chevron" />
                    </button>
                    {guidanceOpen ? (
                      <div className="meetings-content-scroll proposal-guidance-scroll">
                        <pre className="meetings-content-text">{activeSection.guidance}</pre>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {project.description ? (
                  <div className="meetings-detail-section">
                    <button
                      type="button"
                      className={`meetings-assistant-toggle ${descriptionOpen ? "open" : ""}`}
                      onClick={() => setDescriptionOpen((prev) => !prev)}
                    >
                      <FontAwesomeIcon icon={faFileLines} />
                      <span>Project Description</span>
                      <FontAwesomeIcon icon={faChevronDown} className="meetings-toggle-chevron" />
                    </button>
                    {descriptionOpen ? (
                      <div className="meetings-content-scroll proposal-description-scroll">
                        <pre className="meetings-content-text">{project.description}</pre>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}

      {/* Review modal */}
      {reviewPanelOpen && activeSection ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setReviewPanelOpen(false); }}>
          <FocusLock returnFocus>
            <div className="modal-card settings-modal-card">
              <div className="modal-head">
                <h3>Review</h3>
                <div className="proposal-review-head-actions">
                  <span className="delivery-tab-count">{broadSectionFindings.length + proposalWideFindings.length}</span>
                  <button type="button" className="ghost" onClick={() => setReviewPanelOpen(false)}>
                    Close
                  </button>
                </div>
              </div>
              <div className="proposal-review-stack">
                <div className="row-actions">
                  <button type="button" onClick={() => void handleRunReview("proposal")} disabled={reviewBusy}>
                    <FontAwesomeIcon icon={faBolt} /> {reviewBusy ? "Reviewing..." : "Review Proposal"}
                  </button>
                </div>
                {broadSectionFindings.length > 0 ? (
                  <div className="proposal-review-group">
                    <strong>Section Findings</strong>
                    <div className="proposal-review-list">
                      {broadSectionFindings.map((item) => (
                        <div
                          key={item.id}
                          className={`proposal-review-item ${item.finding_type}`}
                          data-status={item.status}
                        >
                          <div className="proposal-review-item-head">
                            <strong>{item.summary}</strong>
                            <button
                              type="button"
                              className="ghost docs-action-btn"
                              onClick={() => void handleResolveFinding(item, item.status === "resolved" ? "open" : "resolved")}
                              title={item.status === "resolved" ? "Reopen" : "Resolve"}
                            >
                              {item.status === "resolved" ? "Reopen" : "Resolve"}
                            </button>
                          </div>
                          {item.details ? <p>{item.details}</p> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {proposalWideFindings.length > 0 ? (
                  <div className="proposal-review-group">
                    <strong>Proposal Findings</strong>
                    <div className="proposal-review-list">
                      {proposalWideFindings.map((item) => (
                        <div
                          key={item.id}
                          className={`proposal-review-item ${item.finding_type}`}
                          data-status={item.status}
                        >
                          <div className="proposal-review-item-head">
                            <strong>{item.summary}</strong>
                            <button
                              type="button"
                              className="ghost docs-action-btn"
                              onClick={() => void handleResolveFinding(item, item.status === "resolved" ? "open" : "resolved")}
                              title={item.status === "resolved" ? "Reopen" : "Resolve"}
                            >
                              {item.status === "resolved" ? "Reopen" : "Resolve"}
                            </button>
                          </div>
                          {item.details ? <p>{item.details}</p> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {!reviewBusy && broadSectionFindings.length === 0 && proposalWideFindings.length === 0 ? (
                  <p className="muted-small">No review findings.</p>
                ) : null}
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}

      {renderCallDocumentModals()}

      {/* Editor card — full-width single column */}
      <div className="card proposal-editor-card">
        {activeSection ? (
          <>
            <div className="proposal-section-bar">
              <div className="proposal-section-bar-main">
                <button
                  type="button"
                  className="ghost docs-action-btn"
                  onClick={() => previousSection && setActiveSectionId(previousSection.id)}
                  disabled={!previousSection}
                  title="Previous section"
                >
                  <FontAwesomeIcon icon={faChevronLeft} />
                </button>
                <select
                  className="proposal-section-select"
                  value={activeSection.id}
                  onChange={(event) => setActiveSectionId(event.target.value)}
                >
                  {filteredSections.map((section) => (
                    <option key={section.id} value={section.id}>
                      {section.position}. {section.title}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="ghost docs-action-btn"
                  onClick={() => nextSection && setActiveSectionId(nextSection.id)}
                  disabled={!nextSection}
                  title="Next section"
                >
                  <FontAwesomeIcon icon={faChevronRight} />
                </button>
                <span className={statusChipClass(activeSection.status)}>{activeSection.status.replace(/_/g, " ")}</span>
                <span className={`proposal-save-state ${saveState}`}>{saveStateLabel(saveState)}</span>
              </div>
              <div className="proposal-section-bar-actions">
                <button type="button" className="ghost icon-only" onClick={() => setSectionBrowserOpen(true)} title="Sections">
                  <FontAwesomeIcon icon={faFolderOpen} />
                </button>
                <button type="button" className="ghost icon-only" onClick={() => setSectionMetaOpen(true)} title="Details">
                  <FontAwesomeIcon icon={faCalendarDay} />
                </button>
                <button
                  type="button"
                  className={`ghost icon-only ${contextPanelOpen ? "active" : ""}`}
                  onClick={() => setContextPanelOpen((current) => !current)}
                  title="Context"
                >
                  <FontAwesomeIcon icon={faFileLines} />
                </button>
                <span className="setup-summary-sep" />
                <div style={{ position: "relative" }}>
                  <button type="button" className="ghost" onClick={() => setSectionAssistantMenuOpen((o) => !o)}>
                    <FontAwesomeIcon icon={faPaperPlane} /> Assistant
                    {(broadSectionFindings.length + proposalWideFindings.length) > 0 ? (
                      <span className="delivery-tab-count">{broadSectionFindings.length + proposalWideFindings.length}</span>
                    ) : null}
                    <FontAwesomeIcon icon={faChevronDown} className="meetings-toggle-chevron" />
                  </button>
                  {sectionAssistantMenuOpen ? (
                    <>
                      <div style={{ position: "fixed", inset: 0, zIndex: 19 }} onClick={() => setSectionAssistantMenuOpen(false)} />
                      <div className="proposal-table-dropdown" style={{ right: 0, left: "auto" }}>
                        <button type="button" onClick={() => { setSectionAssistantMenuOpen(false); handleSectionAIAssist(activeSection); }}>
                          <FontAwesomeIcon icon={faPaperPlane} /> AI Assist
                        </button>
                        <button type="button" disabled={reviewBusy} onClick={() => { setSectionAssistantMenuOpen(false); void handleRunReview("section"); }}>
                          <FontAwesomeIcon icon={faBolt} /> {reviewBusy ? "Reviewing..." : "Review"}
                        </button>
                        <button type="button" disabled={callReviewBusy} onClick={() => { setSectionAssistantMenuOpen(false); void handleRunCallCompliance("section"); }}>
                          <FontAwesomeIcon icon={faBolt} /> Call Check
                        </button>
                        <button type="button" onClick={() => { setSectionAssistantMenuOpen(false); setReviewPanelOpen((c) => !c); }}>
                          <FontAwesomeIcon icon={faBolt} /> Findings
                          {(broadSectionFindings.length + proposalWideFindings.length) > 0 ? (
                            <span className="delivery-tab-count">{broadSectionFindings.length + proposalWideFindings.length}</span>
                          ) : null}
                        </button>
                      </div>
                    </>
                  ) : null}
                </div>
              </div>
            </div>
            <ProposalRichEditor
              value={localContent}
              onChange={handleEditorContentChange}
              placeholder={`Write ${activeSection.title}`}
              projectId={selectedProjectId}
              sectionId={activeSection.id}
              hasCollabState={activeSection.has_collab_state}
              findings={anchoredFindings}
              currentUser={currentUser}
              onCreateComment={handleCreateComment}
              onReplyToFinding={handleReplyToFinding}
              onDeleteFinding={handleDeleteFinding}
            />
            {(inlineGenerating || inlineGeneratedContent) ? (
              <div className="proposal-generation-panel">
                <div className="proposal-generation-head">
                  <strong>{inlineGenerating ? "Generating..." : "Generated Content"}</strong>
                </div>
                <div className="proposal-generation-content">
                  <pre>{inlineGeneratedContent || "..."}</pre>
                </div>
                {!inlineGenerating && inlineGeneratedContent ? (
                  <div className="row-actions">
                    <button type="button" onClick={handleAcceptGenerated}>Accept</button>
                    <button type="button" className="ghost" onClick={handleDiscardGenerated}>Discard</button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </>
        ) : (
          <div className="proposal-empty">No active section</div>
        )}
      </div>
    </>
  );
}
