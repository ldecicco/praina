import { useCallback, useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArchive,
  faBookOpen,
  faCalendarDay,
  faChevronRight,
  faFileArrowUp,
  faFileImport,
  faFlask,
  faLink,
  faMagicWandSparkles,
  faPen,
  faPlus,
  faTrash,
  faUsers,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type {
  BibliographyReference,
  DocumentListItem,
  Member,
  MeetingRecord,
  ResearchCollection,
  ResearchCollectionDetail,
  ResearchCollectionMember,
  ResearchNote,
  ResearchReference,
  WorkEntity,
} from "../types";

const NOTE_TYPE_LABELS: Record<string, string> = {
  observation: "Observation",
  discussion: "Discussion",
  finding: "Finding",
  hypothesis: "Hypothesis",
  method: "Method",
  decision: "Decision",
  action_item: "Action Item",
  literature_review: "Lit Review",
  conclusion: "Conclusion",
};

type Tab = "references" | "notes" | "overview";
type CollectionModalMode = "create" | "edit";
type ReferenceModalMode = "create" | "edit";
type NoteModalMode = "create" | "edit";
type ReferenceModalTab = "manual" | "bibtex" | "pdf" | "document";
type BibliographyModalMode = "create" | "edit";

function csvToList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function toggleListValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function parseSummaryPayload(value: string | null): {
  summary?: string;
  contributions?: string[];
  results?: string[];
  limitations?: string[];
} | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as {
      summary?: string;
      contributions?: string[];
      results?: string[];
      limitations?: string[];
    };
    return typeof parsed === "object" && parsed ? parsed : null;
  } catch {
    return null;
  }
}

function parseSynthesisPayload(value: string | null): {
  summary?: string;
  knowledge_state?: string[];
  discussion_points?: string[];
  findings?: string[];
  decisions?: string[];
  tasks?: string[];
  output_readiness?: {
    status?: string;
    missing?: string[];
    next_actions?: string[];
  };
  open_questions?: string[];
  evidence?: { claim?: string; sources?: string[] }[];
} | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as {
      summary?: string;
      knowledge_state?: string[];
      discussion_points?: string[];
      findings?: string[];
      decisions?: string[];
      tasks?: string[];
      output_readiness?: {
        status?: string;
        missing?: string[];
        next_actions?: string[];
      };
      open_questions?: string[];
      evidence?: { claim?: string; sources?: string[] }[];
    };
    return typeof parsed === "object" && parsed ? parsed : null;
  } catch {
    return null;
  }
}

export function ResearchWorkspace({
  selectedProjectId,
  bibliographyOnly = false,
}: {
  selectedProjectId: string;
  bibliographyOnly?: boolean;
}) {
  const [collections, setCollections] = useState<ResearchCollection[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [collectionDetail, setCollectionDetail] = useState<ResearchCollectionDetail | null>(null);

  const [references, setReferences] = useState<ResearchReference[]>([]);
  const [bibliography, setBibliography] = useState<BibliographyReference[]>([]);
  const [notes, setNotes] = useState<ResearchNote[]>([]);
  const [allReferences, setAllReferences] = useState<ResearchReference[]>([]);
  const [projectDocuments, setProjectDocuments] = useState<DocumentListItem[]>([]);
  const [projectMeetings, setProjectMeetings] = useState<MeetingRecord[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [wps, setWps] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);

  const [tab, setTab] = useState<Tab>("references");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [collectionModalMode, setCollectionModalMode] = useState<CollectionModalMode>("create");
  const [referenceModalOpen, setReferenceModalOpen] = useState(false);
  const [referenceModalMode, setReferenceModalMode] = useState<ReferenceModalMode>("create");
  const [noteModalOpen, setNoteModalOpen] = useState(false);
  const [noteModalMode, setNoteModalMode] = useState<NoteModalMode>("create");
  const [bibliographyModalOpen, setBibliographyModalOpen] = useState(false);
  const [bibliographyPickerOpen, setBibliographyPickerOpen] = useState(false);
  const [bibliographyModalMode, setBibliographyModalMode] = useState<BibliographyModalMode>("create");
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [wbsModalOpen, setWbsModalOpen] = useState(false);

  const [editingCollectionId, setEditingCollectionId] = useState<string | null>(null);
  const [editingReferenceId, setEditingReferenceId] = useState<string | null>(null);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingBibliographyId, setEditingBibliographyId] = useState<string | null>(null);

  const [collectionTitle, setCollectionTitle] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [collectionHypothesis, setCollectionHypothesis] = useState("");
  const [collectionOpenQuestions, setCollectionOpenQuestions] = useState("");
  const [collectionStatus, setCollectionStatus] = useState("active");
  const [collectionOverleafUrl, setCollectionOverleafUrl] = useState("");
  const [collectionOutputTitle, setCollectionOutputTitle] = useState("");
  const [collectionOutputStatus, setCollectionOutputStatus] = useState("not_started");

  const [referenceTitle, setReferenceTitle] = useState("");
  const [referenceAuthors, setReferenceAuthors] = useState("");
  const [referenceYear, setReferenceYear] = useState("");
  const [referenceVenue, setReferenceVenue] = useState("");
  const [referenceDoi, setReferenceDoi] = useState("");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [referenceAbstract, setReferenceAbstract] = useState("");
  const [referenceCollectionId, setReferenceCollectionId] = useState("");
  const [referenceDocumentKey, setReferenceDocumentKey] = useState("");
  const [referenceReadingStatus, setReferenceReadingStatus] = useState("unread");

  const [referenceModalTab, setReferenceModalTab] = useState<ReferenceModalTab>("manual");
  const [bibtexInput, setBibtexInput] = useState("");
  const [bibtexResult, setBibtexResult] = useState<{ created: number; errors: string[] } | null>(null);
  const [referencePdfFile, setReferencePdfFile] = useState<File | null>(null);
  const [existingDocumentKey, setExistingDocumentKey] = useState("");

  const [noteTitle, setNoteTitle] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [noteType, setNoteType] = useState("observation");
  const [noteCollectionId, setNoteCollectionId] = useState("");
  const [noteReferenceIds, setNoteReferenceIds] = useState<string[]>([]);

  const [newMemberId, setNewMemberId] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("contributor");

  const [wbsWpIds, setWbsWpIds] = useState<string[]>([]);
  const [wbsTaskIds, setWbsTaskIds] = useState<string[]>([]);
  const [wbsDeliverableIds, setWbsDeliverableIds] = useState<string[]>([]);
  const [meetingIds, setMeetingIds] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [summarizingId, setSummarizingId] = useState<string | null>(null);

  const [refSearch, setRefSearch] = useState("");
  const [bibliographySearch, setBibliographySearch] = useState("");
  const [bibliographyVisibilityFilter, setBibliographyVisibilityFilter] = useState("");
  const [refStatusFilter, setRefStatusFilter] = useState("");
  const [noteTypeFilter, setNoteTypeFilter] = useState("");
  const [bibliographyTitle, setBibliographyTitle] = useState("");
  const [bibliographyAuthors, setBibliographyAuthors] = useState("");
  const [bibliographyYear, setBibliographyYear] = useState("");
  const [bibliographyVenue, setBibliographyVenue] = useState("");
  const [bibliographyDoi, setBibliographyDoi] = useState("");
  const [bibliographyUrl, setBibliographyUrl] = useState("");
  const [bibliographyAbstract, setBibliographyAbstract] = useState("");
  const [bibliographyVisibility, setBibliographyVisibility] = useState("shared");
  const [bibliographyBibtexInput, setBibliographyBibtexInput] = useState("");
  const [bibliographyBibtexResult, setBibliographyBibtexResult] = useState<{ created: number; errors: string[] } | null>(null);
  const [bibliographyAttachmentFile, setBibliographyAttachmentFile] = useState<File | null>(null);

  const activeCollections = collections.filter((item) => item.status === "active");
  const archivedCollections = collections.filter((item) => item.status !== "active");
  const readCount = references.filter((item) => item.reading_status === "read" || item.reading_status === "reviewed").length;
  const selectedCollection = collections.find((item) => item.id === selectedCollectionId) ?? null;
  const availableDocuments = useMemo(
    () => projectDocuments.filter((item) => item.status === "indexed" || item.status === "uploaded"),
    [projectDocuments]
  );

  async function loadCollections(projectId = selectedProjectId) {
    if (!projectId) return;
    const response = await api.listResearchCollections(projectId, { page_size: 100 });
    setCollections(response.items);
  }

  async function loadMembers(projectId = selectedProjectId) {
    if (!projectId) return;
    const response = await api.listMembers(projectId);
    setMembers(response.items.filter((item: Member) => item.is_active));
  }

  async function loadSupportData(projectId = selectedProjectId) {
    if (!projectId) return;
    const [docsRes, refsRes, meetingsRes, wpsRes, tasksRes, deliverablesRes] = await Promise.all([
      api.listDocuments(projectId),
      api.listResearchReferences(projectId, { page_size: 100 }),
      api.listMeetings(projectId),
      api.listWorkPackages(projectId),
      api.listTasks(projectId),
      api.listDeliverables(projectId),
    ]);
    setProjectDocuments(docsRes.items);
    setAllReferences(refsRes.items);
    setProjectMeetings(meetingsRes.items);
    setWps(wpsRes.items);
    setTasks(tasksRes.items);
    setDeliverables(deliverablesRes.items);
  }

  async function loadBibliography(projectId = selectedProjectId) {
    if (!projectId && !bibliographyOnly) return;
    const response = await api.listGlobalBibliography({
      q: bibliographySearch || undefined,
      visibility: bibliographyVisibilityFilter || undefined,
      page_size: 100,
    });
    setBibliography(response.items);
  }

  async function loadCollectionDetail(collectionId: string, projectId = selectedProjectId) {
    if (!projectId || !collectionId) return;
    const detail = await api.getResearchCollection(projectId, collectionId);
    setCollectionDetail(detail);
  }

  async function loadReferences(collectionId: string | null, projectId = selectedProjectId) {
    if (!projectId) return;
    const opts: Record<string, string> = {};
    if (collectionId) opts.collection_id = collectionId;
    if (refStatusFilter) opts.reading_status = refStatusFilter;
    if (refSearch) opts.q = refSearch;
    const response = await api.listResearchReferences(projectId, { ...opts, page_size: 100 });
    setReferences(response.items);
  }

  async function loadNotes(collectionId: string | null, projectId = selectedProjectId) {
    if (!projectId) return;
    const opts: Record<string, string> = {};
    if (collectionId) opts.collection_id = collectionId;
    if (noteTypeFilter) opts.note_type = noteTypeFilter;
    const response = await api.listResearchNotes(projectId, { ...opts, page_size: 100 });
    setNotes(response.items);
  }

  async function refreshWorkspace(projectId = selectedProjectId, collectionId = selectedCollectionId) {
    if (!projectId) return;
    const tasksToRun: Promise<unknown>[] = [loadReferences(collectionId, projectId), loadNotes(collectionId, projectId)];
    if (collectionId) {
      tasksToRun.push(loadCollectionDetail(collectionId, projectId));
    } else {
      setCollectionDetail(null);
    }
    await Promise.all(tasksToRun);
  }

  useEffect(() => {
    if (bibliographyOnly) {
      setLoading(true);
      setError("");
      setStatus("");
      Promise.all([loadBibliography(selectedProjectId)])
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to load bibliography");
        })
        .finally(() => setLoading(false));
      return;
    }
    if (!selectedProjectId) {
      setCollections([]);
      setCollectionDetail(null);
      setReferences([]);
      setBibliography([]);
      setNotes([]);
      setAllReferences([]);
      setProjectDocuments([]);
      setProjectMeetings([]);
      setMembers([]);
      setWps([]);
      setTasks([]);
      setDeliverables([]);
      setSelectedCollectionId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    setStatus("");
    setSelectedCollectionId(null);
    setCollectionDetail(null);
    Promise.all([
      loadCollections(selectedProjectId),
      loadMembers(selectedProjectId),
      loadSupportData(selectedProjectId),
      loadBibliography(selectedProjectId),
      loadReferences(null, selectedProjectId),
      loadNotes(null, selectedProjectId),
    ])
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load research workspace");
      })
      .finally(() => setLoading(false));
  }, [selectedProjectId, bibliographyOnly]);

  useEffect(() => {
    if (bibliographyOnly) return;
    if (!selectedProjectId) return;
    refreshWorkspace(selectedProjectId, selectedCollectionId).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to refresh research workspace");
    });
  }, [selectedProjectId, selectedCollectionId, refStatusFilter, refSearch, noteTypeFilter, bibliographyOnly]);

  useEffect(() => {
    if (!selectedProjectId && !bibliographyOnly) return;
    loadBibliography(selectedProjectId).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load bibliography");
    });
  }, [selectedProjectId, bibliographySearch, bibliographyVisibilityFilter, bibliographyOnly]);

  const stableLoad = useCallback(() => {
    if (bibliographyOnly) {
      void loadBibliography();
      return;
    }
    void refreshWorkspace();
  }, [selectedProjectId, selectedCollectionId, refStatusFilter, refSearch, noteTypeFilter, bibliographySearch, bibliographyVisibilityFilter, bibliographyOnly]);
  useAutoRefresh(stableLoad);

  function resetCollectionForm() {
    setCollectionTitle("");
    setCollectionDescription("");
    setCollectionHypothesis("");
    setCollectionOpenQuestions("");
    setCollectionStatus("active");
    setCollectionOverleafUrl("");
    setCollectionOutputTitle("");
    setCollectionOutputStatus("not_started");
    setEditingCollectionId(null);
  }

  function resetReferenceForm(collectionId?: string | null) {
    setReferenceTitle("");
    setReferenceAuthors("");
    setReferenceYear("");
    setReferenceVenue("");
    setReferenceDoi("");
    setReferenceUrl("");
    setReferenceAbstract("");
    setReferenceCollectionId(collectionId || "");
    setReferenceDocumentKey("");
    setReferenceReadingStatus("unread");
    setReferencePdfFile(null);
    setExistingDocumentKey("");
    setBibtexInput("");
    setBibtexResult(null);
    setEditingReferenceId(null);
    setReferenceModalTab("manual");
  }

  function resetNoteForm(collectionId?: string | null) {
    setNoteTitle("");
    setNoteContent("");
    setNoteType("observation");
    setNoteCollectionId(collectionId || "");
    setNoteReferenceIds([]);
    setEditingNoteId(null);
  }

  function resetBibliographyForm() {
    setBibliographyTitle("");
    setBibliographyAuthors("");
    setBibliographyYear("");
    setBibliographyVenue("");
    setBibliographyDoi("");
    setBibliographyUrl("");
    setBibliographyAbstract("");
    setBibliographyVisibility("shared");
    setBibliographyBibtexInput("");
    setBibliographyBibtexResult(null);
    setBibliographyAttachmentFile(null);
    setEditingBibliographyId(null);
  }

  function openCreateCollectionModal() {
    setCollectionModalMode("create");
    resetCollectionForm();
    setCollectionModalOpen(true);
  }

  function openCreateBibliographyModal() {
    setBibliographyModalMode("create");
    resetBibliographyForm();
    setBibliographyModalOpen(true);
  }

  function openEditBibliographyModal(item: BibliographyReference) {
    setBibliographyModalMode("edit");
    setEditingBibliographyId(item.id);
    setBibliographyTitle(item.title);
    setBibliographyAuthors(item.authors.join(", "));
    setBibliographyYear(item.year ? String(item.year) : "");
    setBibliographyVenue(item.venue || "");
    setBibliographyDoi(item.doi || "");
    setBibliographyUrl(item.url || "");
    setBibliographyAbstract(item.abstract || "");
    setBibliographyVisibility(item.visibility || "shared");
    setBibliographyBibtexInput(item.bibtex_raw || "");
    setBibliographyBibtexResult(null);
    setBibliographyAttachmentFile(null);
    setBibliographyModalOpen(true);
  }

  function openEditCollectionModal() {
    if (!collectionDetail) return;
    setCollectionModalMode("edit");
    setEditingCollectionId(collectionDetail.id);
    setCollectionTitle(collectionDetail.title);
    setCollectionDescription(collectionDetail.description || "");
    setCollectionHypothesis(collectionDetail.hypothesis || "");
    setCollectionOpenQuestions((collectionDetail.open_questions || []).join(", "));
    setCollectionStatus(collectionDetail.status);
    setCollectionOverleafUrl(collectionDetail.overleaf_url || "");
    setCollectionOutputTitle(collectionDetail.target_output_title || "");
    setCollectionOutputStatus(collectionDetail.output_status || "not_started");
    setCollectionModalOpen(true);
  }

  function openCreateReferenceModal(tabName: ReferenceModalTab = "manual") {
    if (!selectedCollectionId) {
      setError("Select a collection first.");
      return;
    }
    setReferenceModalMode("create");
    resetReferenceForm(selectedCollectionId);
    setReferenceModalTab(tabName);
    setReferenceModalOpen(true);
  }

  function openBibliographyPicker() {
    if (!selectedCollectionId) {
      setError("Select a collection first.");
      return;
    }
    setBibliographyPickerOpen(true);
  }

  function openEditReferenceModal(reference: ResearchReference) {
    setReferenceModalMode("edit");
    setEditingReferenceId(reference.id);
    setReferenceTitle(reference.title);
    setReferenceAuthors(reference.authors.join(", "));
    setReferenceYear(reference.year ? String(reference.year) : "");
    setReferenceVenue(reference.venue || "");
    setReferenceDoi(reference.doi || "");
    setReferenceUrl(reference.url || "");
    setReferenceAbstract(reference.abstract || "");
    setReferenceCollectionId(reference.collection_id || "");
    setReferenceDocumentKey(reference.document_key || "");
    setReferenceReadingStatus(reference.reading_status);
    setReferencePdfFile(null);
    setExistingDocumentKey(reference.document_key || "");
    setBibtexInput("");
    setBibtexResult(null);
    setReferenceModalTab(reference.document_key ? "document" : "manual");
    setReferenceModalOpen(true);
  }

  function openCreateNoteModal() {
    if (!selectedCollectionId) {
      setError("Select a collection first.");
      return;
    }
    setNoteModalMode("create");
    resetNoteForm(selectedCollectionId);
    setNoteModalOpen(true);
  }

  function openEditNoteModal(note: ResearchNote) {
    setNoteModalMode("edit");
    setEditingNoteId(note.id);
    setNoteTitle(note.title);
    setNoteContent(note.content);
    setNoteType(note.note_type);
    setNoteCollectionId(note.collection_id || selectedCollectionId || "");
    setNoteReferenceIds(note.linked_reference_ids);
    setNoteModalOpen(true);
  }

  function openWbsModal() {
    if (!collectionDetail) return;
    setWbsWpIds(collectionDetail.wp_ids);
    setWbsTaskIds(collectionDetail.task_ids);
    setWbsDeliverableIds(collectionDetail.deliverable_ids);
    setMeetingIds(collectionDetail.meetings.map((item) => item.id));
    setWbsModalOpen(true);
  }

  async function handleSaveCollection() {
    if (!selectedProjectId || !collectionTitle.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      if (collectionModalMode === "create") {
        const created = await api.createResearchCollection(selectedProjectId, {
          title: collectionTitle.trim(),
          description: collectionDescription.trim() || undefined,
          hypothesis: collectionHypothesis.trim() || undefined,
          open_questions: csvToList(collectionOpenQuestions),
          overleaf_url: collectionOverleafUrl.trim() || undefined,
          target_output_title: collectionOutputTitle.trim() || undefined,
          output_status: collectionOutputStatus,
        });
        await loadCollections();
        setSelectedCollectionId(created.id);
        setStatus("Collection created.");
      } else if (editingCollectionId) {
        await api.updateResearchCollection(selectedProjectId, editingCollectionId, {
          title: collectionTitle.trim(),
          description: collectionDescription.trim() || null,
          hypothesis: collectionHypothesis.trim() || null,
          open_questions: csvToList(collectionOpenQuestions),
          status: collectionStatus,
          overleaf_url: collectionOverleafUrl.trim() || null,
          target_output_title: collectionOutputTitle.trim() || null,
          output_status: collectionOutputStatus,
        });
        await loadCollections();
        await loadCollectionDetail(editingCollectionId);
        setStatus("Collection updated.");
      }
      setCollectionModalOpen(false);
      resetCollectionForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save collection");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteCollection(collectionId: string) {
    if (!selectedProjectId || !confirm("Delete this collection?")) return;
    try {
      await api.deleteResearchCollection(selectedProjectId, collectionId);
      await loadCollections();
      if (selectedCollectionId === collectionId) {
        setSelectedCollectionId(null);
        setCollectionDetail(null);
      } else if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setStatus("Collection deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete collection");
    }
  }

  async function handleArchiveCollection(collectionId: string) {
    if (!selectedProjectId) return;
    try {
      await api.updateResearchCollection(selectedProjectId, collectionId, { status: "archived" });
      await loadCollections();
      if (selectedCollectionId === collectionId) {
        await loadCollectionDetail(collectionId);
      }
      setStatus("Collection archived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive collection");
    }
  }

  function buildReferencePayload(overrides?: Partial<Record<string, unknown>>) {
    return {
      title: referenceTitle.trim(),
      collection_id: referenceCollectionId || undefined,
      authors: csvToList(referenceAuthors),
      year: referenceYear ? Number(referenceYear) : undefined,
      venue: referenceVenue.trim() || undefined,
      doi: referenceDoi.trim() || undefined,
      url: referenceUrl.trim() || undefined,
      abstract: referenceAbstract.trim() || undefined,
      document_key: referenceDocumentKey || undefined,
      reading_status: referenceReadingStatus,
      ...overrides,
    };
  }

  async function refreshResearchDataAfterReferenceChange(targetCollectionId?: string) {
    await Promise.all([
      loadCollections(),
      loadSupportData(),
      loadReferences(targetCollectionId ?? selectedCollectionId),
    ]);
    if (selectedCollectionId) {
      await loadCollectionDetail(selectedCollectionId);
    }
  }

  async function handleSaveReference() {
    if (!selectedProjectId || !referenceTitle.trim() || !referenceCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      if (referenceModalMode === "create") {
        await api.createResearchReference(selectedProjectId, buildReferencePayload());
        setStatus("Reference added.");
      } else if (editingReferenceId) {
        await api.updateResearchReference(selectedProjectId, editingReferenceId, buildReferencePayload());
        setStatus("Reference updated.");
      }
      await refreshResearchDataAfterReferenceChange(referenceCollectionId || selectedCollectionId || undefined);
      setReferenceModalOpen(false);
      resetReferenceForm(selectedCollectionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save reference");
    } finally {
      setSaving(false);
    }
  }

  async function handleImportBibtex() {
    if (!selectedProjectId || !bibtexInput.trim() || !referenceCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    setBibtexResult(null);
    try {
      const result = await api.importBibtexReferences(selectedProjectId, bibtexInput.trim(), referenceCollectionId);
      setBibtexResult({ created: result.created.length, errors: result.errors });
      await refreshResearchDataAfterReferenceChange(referenceCollectionId);
      setStatus(result.created.length > 0 ? "References imported." : "No references imported.");
      if (result.errors.length === 0) {
        setReferenceModalOpen(false);
        resetReferenceForm(selectedCollectionId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "BibTeX import failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveReferenceFromExistingDocument() {
    if (!selectedProjectId || !existingDocumentKey || !referenceCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const selectedDocument = projectDocuments.find((item) => item.document_key === existingDocumentKey) || null;
      const metadata = await api.extractPdfMetadata(selectedProjectId, existingDocumentKey).catch(() => null);
      const payload = buildReferencePayload({
        title: referenceTitle.trim() || metadata?.title || selectedDocument?.title || "Untitled Reference",
        authors: csvToList(referenceAuthors).length > 0 ? csvToList(referenceAuthors) : metadata?.authors || [],
        year: referenceYear ? Number(referenceYear) : metadata?.year || undefined,
        venue: referenceVenue.trim() || metadata?.venue || undefined,
        abstract: referenceAbstract.trim() || metadata?.abstract || undefined,
        document_key: existingDocumentKey,
      });
      if (referenceModalMode === "create") {
        await api.createResearchReference(selectedProjectId, payload);
      } else if (editingReferenceId) {
        await api.updateResearchReference(selectedProjectId, editingReferenceId, payload);
      }
      await refreshResearchDataAfterReferenceChange(referenceCollectionId);
      setReferenceModalOpen(false);
      resetReferenceForm(selectedCollectionId);
      setStatus(referenceModalMode === "create" ? "Reference added from document." : "Reference updated from document.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save reference from document");
    } finally {
      setSaving(false);
    }
  }

  async function handleUploadPdfReference() {
    if (!selectedProjectId || !referencePdfFile || !referenceCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: referencePdfFile,
        scope: "project",
        title: referenceTitle.trim() || referencePdfFile.name.replace(/\.pdf$/i, ""),
        metadata_json: JSON.stringify({ category: "research_reference" }),
      });
      const reindexResult = await api.reindexDocument(selectedProjectId, uploaded.id, false).catch(() => null);
      const metadata =
        reindexResult?.status === "indexed"
          ? await api.extractPdfMetadata(selectedProjectId, uploaded.document_key).catch(() => null)
          : null;
      const payload = buildReferencePayload({
        title: referenceTitle.trim() || metadata?.title || uploaded.title,
        authors: csvToList(referenceAuthors).length > 0 ? csvToList(referenceAuthors) : metadata?.authors || [],
        year: referenceYear ? Number(referenceYear) : metadata?.year || undefined,
        venue: referenceVenue.trim() || metadata?.venue || undefined,
        abstract: referenceAbstract.trim() || metadata?.abstract || undefined,
        document_key: uploaded.document_key,
      });
      if (referenceModalMode === "create") {
        await api.createResearchReference(selectedProjectId, payload);
      } else if (editingReferenceId) {
        await api.updateResearchReference(selectedProjectId, editingReferenceId, payload);
      }
      await Promise.all([refreshResearchDataAfterReferenceChange(referenceCollectionId), loadSupportData()]);
      setReferenceModalOpen(false);
      resetReferenceForm(selectedCollectionId);
      if (referenceModalMode === "create") {
        setStatus(
          reindexResult?.status === "indexed"
            ? "PDF uploaded and reference added."
            : "PDF uploaded and reference added. Reindex the document later for retrieval."
        );
      } else {
        setStatus(
          reindexResult?.status === "indexed"
            ? "PDF uploaded and reference updated."
            : "PDF uploaded and reference updated. Reindex the document later for retrieval."
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload PDF reference");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteReference(referenceId: string) {
    if (!selectedProjectId || !confirm("Delete this reference?")) return;
    try {
      await api.deleteResearchReference(selectedProjectId, referenceId);
      await refreshResearchDataAfterReferenceChange(selectedCollectionId || undefined);
      setStatus("Reference deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete reference");
    }
  }

  async function handleStatusChange(referenceId: string, nextStatus: string) {
    if (!selectedProjectId) return;
    try {
      const updated = await api.updateReferenceStatus(selectedProjectId, referenceId, nextStatus);
      setReferences((items) => items.map((item) => (item.id === referenceId ? updated : item)));
      setAllReferences((items) => items.map((item) => (item.id === referenceId ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update reference status");
    }
  }

  async function handleSummarize(referenceId: string) {
    if (!selectedProjectId) return;
    setSummarizingId(referenceId);
    setError("");
    setStatus("");
    try {
      const result = await api.summarizeReference(selectedProjectId, referenceId);
      setReferences((items) =>
        items.map((item) => (item.id === referenceId ? { ...item, ai_summary: result.ai_summary, ai_summary_at: result.ai_summary_at } : item))
      );
      setAllReferences((items) =>
        items.map((item) => (item.id === referenceId ? { ...item, ai_summary: result.ai_summary, ai_summary_at: result.ai_summary_at } : item))
      );
      setStatus("Reference summarized.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Summarization failed");
    } finally {
      setSummarizingId(null);
    }
  }

  function buildBibliographyPayload(overrides?: Partial<Record<string, unknown>>) {
    return {
      title: bibliographyTitle.trim(),
      authors: csvToList(bibliographyAuthors),
      year: bibliographyYear ? Number(bibliographyYear) : undefined,
      venue: bibliographyVenue.trim() || undefined,
      doi: bibliographyDoi.trim() || undefined,
      url: bibliographyUrl.trim() || undefined,
      abstract: bibliographyAbstract.trim() || undefined,
      visibility: bibliographyVisibility,
      ...overrides,
    };
  }

  async function handleSaveBibliography() {
    if (!selectedProjectId || !bibliographyTitle.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const payload = buildBibliographyPayload({ bibtex_raw: bibliographyBibtexInput.trim() || undefined });
      const item =
        bibliographyModalMode === "create"
          ? await api.createGlobalBibliography(payload)
          : await api.updateGlobalBibliography(editingBibliographyId!, payload);
      if (bibliographyAttachmentFile) {
        if (!selectedProjectId) throw new Error("Select a project before attaching a PDF.");
        await api.uploadGlobalBibliographyAttachment(item.id, selectedProjectId, bibliographyAttachmentFile);
      }
      await loadBibliography();
      setBibliographyModalOpen(false);
      resetBibliographyForm();
      setStatus(bibliographyModalMode === "create" ? "Paper added." : "Paper updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save paper");
    } finally {
      setSaving(false);
    }
  }

  async function handleImportBibliographyBibtex() {
    if (!selectedProjectId || !bibliographyBibtexInput.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    setBibliographyBibtexResult(null);
    try {
      const result = await api.importGlobalBibliographyBibtex(bibliographyBibtexInput.trim(), bibliographyVisibility);
      if (bibliographyAttachmentFile && result.created.length === 1) {
        if (!selectedProjectId) throw new Error("Select a project before attaching a PDF.");
        await api.uploadGlobalBibliographyAttachment(result.created[0].id, selectedProjectId, bibliographyAttachmentFile);
      }
      setBibliographyBibtexResult({ created: result.created.length, errors: result.errors });
      await loadBibliography();
      if (bibliographyAttachmentFile && result.created.length > 1) {
        setStatus("BibTeX imported. PDF was not attached because multiple papers were created.");
      } else {
        setStatus(result.created.length > 0 ? "BibTeX imported." : "No papers imported.");
      }
      if (result.errors.length === 0) {
        setBibliographyModalOpen(false);
        resetBibliographyForm();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "BibTeX import failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleLinkBibliography(item: BibliographyReference) {
    if (!selectedProjectId || !selectedCollectionId) {
      setError("Select a collection first.");
      return;
    }
    try {
      await api.linkBibliographyReference(selectedProjectId, {
        bibliography_reference_id: item.id,
        collection_id: selectedCollectionId,
        reading_status: "unread",
      });
      await refreshResearchDataAfterReferenceChange(selectedCollectionId);
      await loadBibliography();
      setBibliographyPickerOpen(false);
      setStatus("Paper linked.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to link paper");
    }
  }

  async function handleDeleteBibliography(id: string) {
    if (!selectedProjectId || !confirm("Delete this paper?")) return;
    try {
      await api.deleteGlobalBibliography(id);
      await loadBibliography();
      setStatus("Paper deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete paper");
    }
  }

  async function handleOpenBibliographyAttachment(item: BibliographyReference) {
    if (!selectedProjectId) return;
    try {
      const blob = await api.getGlobalBibliographyAttachment(item.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open paper PDF");
    }
  }

  async function handleSaveNote() {
    if (!selectedProjectId || !noteTitle.trim() || !noteContent.trim() || !noteCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      if (noteModalMode === "create") {
        await api.createResearchNote(selectedProjectId, {
          title: noteTitle.trim(),
          content: noteContent.trim(),
          collection_id: noteCollectionId,
          note_type: noteType,
          linked_reference_ids: noteReferenceIds,
        });
        setStatus("Note added.");
      } else if (editingNoteId) {
        await api.updateResearchNote(selectedProjectId, editingNoteId, {
          title: noteTitle.trim(),
          content: noteContent.trim(),
          collection_id: noteCollectionId,
          note_type: noteType,
        });
        await api.setNoteReferences(selectedProjectId, editingNoteId, noteReferenceIds);
        setStatus("Note updated.");
      }
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId), loadSupportData()]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setNoteModalOpen(false);
      resetNoteForm(selectedCollectionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save note");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!selectedProjectId || !confirm("Delete this note?")) return;
    try {
      await api.deleteResearchNote(selectedProjectId, noteId);
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId)]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setStatus("Note deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete note");
    }
  }

  async function handleAddMember() {
    if (!selectedProjectId || !selectedCollectionId || !newMemberId) return;
    setSaving(true);
    setError("");
    try {
      await api.addCollectionMember(selectedProjectId, selectedCollectionId, {
        member_id: newMemberId,
        role: newMemberRole,
      });
      await Promise.all([loadCollections(), loadCollectionDetail(selectedCollectionId)]);
      setMemberModalOpen(false);
      setNewMemberId("");
      setNewMemberRole("contributor");
      setStatus("Member added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add member");
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdateMemberRole(memberRecordId: string, role: string) {
    if (!selectedProjectId || !selectedCollectionId) return;
    try {
      await api.updateCollectionMember(selectedProjectId, selectedCollectionId, memberRecordId, { role });
      await Promise.all([loadCollections(), loadCollectionDetail(selectedCollectionId)]);
      setStatus("Member role updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update member role");
    }
  }

  async function handleRemoveMember(memberRecordId: string) {
    if (!selectedProjectId || !selectedCollectionId) return;
    try {
      await api.removeCollectionMember(selectedProjectId, selectedCollectionId, memberRecordId);
      await Promise.all([loadCollections(), loadCollectionDetail(selectedCollectionId)]);
      setStatus("Member removed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove member");
    }
  }

  async function handleSaveWbsLinks() {
    if (!selectedProjectId || !selectedCollectionId) return;
    setSaving(true);
    setError("");
    try {
      await Promise.all([
        api.setCollectionWbsLinks(selectedProjectId, selectedCollectionId, {
          wp_ids: wbsWpIds,
          task_ids: wbsTaskIds,
          deliverable_ids: wbsDeliverableIds,
        }),
        api.setCollectionMeetings(selectedProjectId, selectedCollectionId, {
          meeting_ids: meetingIds,
        }),
      ]);
      await loadCollectionDetail(selectedCollectionId);
      setWbsModalOpen(false);
      setStatus("Context links updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update context links");
    } finally {
      setSaving(false);
    }
  }

  async function handleSynthesize() {
    if (!selectedProjectId || !selectedCollectionId) return;
    setSynthesizing(true);
    setError("");
    try {
      const result = await api.synthesizeCollection(selectedProjectId, selectedCollectionId);
      setCollectionDetail((current) => (current ? { ...current, ai_synthesis: result.ai_synthesis, ai_synthesis_at: result.ai_synthesis_at } : current));
      setStatus("Synthesis updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Synthesis failed");
    } finally {
      setSynthesizing(false);
    }
  }

  if (!selectedProjectId && !bibliographyOnly) return <p className="empty-message">Select a project to manage research.</p>;
  if (loading) return <p className="muted-small">Loading...</p>;

  return (
    <>
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          {!bibliographyOnly ? (
            <>
              <span>{collections.length} collections</span>
              <span className="setup-summary-sep" />
            </>
          ) : null}
          <span>{bibliography.length} papers</span>
          {!bibliographyOnly ? (
            <>
              <span className="setup-summary-sep" />
              <span>{references.length} references</span>
              <span className="setup-summary-sep" />
              <span>{readCount} read</span>
              <span className="setup-summary-sep" />
              <span>{notes.length} notes</span>
            </>
          ) : null}
        </div>
        <button type="button" className="meetings-new-btn" onClick={bibliographyOnly ? openCreateBibliographyModal : openCreateCollectionModal}>
          <FontAwesomeIcon icon={faPlus} /> {bibliographyOnly ? "Add Paper" : "New Collection"}
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="muted-small">{status}</p> : null}

      {!bibliographyOnly ? <div className="meetings-toolbar">
        <div className="meetings-filter-group research-collection-strip">
          <button
            type="button"
            className={`chip small ${!selectedCollectionId ? "status-active" : ""}`}
            onClick={() => setSelectedCollectionId(null)}
          >
            <FontAwesomeIcon icon={faBookOpen} /> All
          </button>
          {activeCollections.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`chip small ${selectedCollectionId === item.id ? "status-active" : ""}`}
              onClick={() => setSelectedCollectionId(item.id)}
              title={item.title}
            >
              <FontAwesomeIcon icon={faFlask} /> {item.title}
              <span className="delivery-tab-count">{item.reference_count + item.note_count}</span>
            </button>
          ))}
          {archivedCollections.length > 0 ? (
            <button type="button" className="chip small" onClick={() => setShowArchived((value) => !value)}>
              <FontAwesomeIcon icon={faChevronRight} className={showArchived ? "research-chevron-open" : ""} />
              Archived ({archivedCollections.length})
            </button>
          ) : null}
          {showArchived
            ? archivedCollections.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`chip small ${selectedCollectionId === item.id ? "status-active" : ""}`}
                  onClick={() => setSelectedCollectionId(item.id)}
                >
                  <FontAwesomeIcon icon={faArchive} /> {item.title}
                </button>
              ))
            : null}
        </div>
      </div> : null}

      {!bibliographyOnly && collectionDetail && selectedCollection ? (
        <div className="research-collection-header">
          <div className="research-collection-title-row">
            <strong>{collectionDetail.title}</strong>
            <span className={`chip small ${collectionDetail.status === "active" ? "status-ok" : ""}`}>{collectionDetail.status}</span>
            <span className="chip small">{collectionDetail.output_status.replace(/_/g, " ")}</span>
            <span className="muted-small">{collectionDetail.reference_count} refs</span>
            <span className="setup-summary-sep" />
            <span className="muted-small">{collectionDetail.note_count} notes</span>
            <span className="setup-summary-sep" />
            <span className="muted-small">{collectionDetail.member_count} members</span>
          </div>
          {collectionDetail.hypothesis ? <p className="muted-small research-hypothesis">{collectionDetail.hypothesis}</p> : null}
          <div className="research-header-actions">
            <button type="button" className="meetings-new-btn" onClick={() => openCreateReferenceModal("manual")}>
              <FontAwesomeIcon icon={faPlus} /> Add Reference
            </button>
            <button type="button" className="meetings-new-btn" onClick={() => openCreateReferenceModal("pdf")}>
              <FontAwesomeIcon icon={faFileArrowUp} /> Upload PDF
            </button>
            <button type="button" className="meetings-new-btn" onClick={openCreateNoteModal}>
              <FontAwesomeIcon icon={faPlus} /> Add Note
            </button>
            <button type="button" className="ghost docs-action-btn" title="Edit Collection" onClick={openEditCollectionModal}>
              <FontAwesomeIcon icon={faPen} />
            </button>
            <button type="button" className="ghost docs-action-btn" title="Link Context" onClick={openWbsModal}>
              <FontAwesomeIcon icon={faLink} />
            </button>
            <button type="button" className="ghost docs-action-btn" title="Archive" onClick={() => handleArchiveCollection(selectedCollection.id)}>
              <FontAwesomeIcon icon={faArchive} />
            </button>
            <button type="button" className="ghost docs-action-btn" title="Delete" onClick={() => handleDeleteCollection(selectedCollection.id)}>
              <FontAwesomeIcon icon={faTrash} />
            </button>
          </div>
        </div>
      ) : null}

      {!bibliographyOnly ? <div className="delivery-tabs">
        <button className={`delivery-tab ${tab === "references" ? "active" : ""}`} onClick={() => setTab("references")}>
          References <span className="delivery-tab-count">{references.length}</span>
        </button>
        <button className={`delivery-tab ${tab === "notes" ? "active" : ""}`} onClick={() => setTab("notes")}>
          Notes <span className="delivery-tab-count">{notes.length}</span>
        </button>
        <button className={`delivery-tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          Overview
        </button>
        {tab === "references" ? (
          <>
            <button
              type="button"
              className="meetings-new-btn delivery-tab-action"
              onClick={openBibliographyPicker}
              disabled={!selectedCollectionId}
            >
              <FontAwesomeIcon icon={faFileImport} /> Import
            </button>
            <button
              type="button"
              className="meetings-new-btn delivery-tab-action"
              onClick={() => openCreateReferenceModal("manual")}
              disabled={!selectedCollectionId}
            >
              <FontAwesomeIcon icon={faPlus} /> Add Reference
            </button>
          </>
        ) : null}
        {tab === "notes" ? (
          <button
            type="button"
            className="meetings-new-btn delivery-tab-action"
            onClick={openCreateNoteModal}
            disabled={!selectedCollectionId}
          >
            <FontAwesomeIcon icon={faPlus} /> Add Note
          </button>
        ) : null}
      </div>
      : null}

      {tab === "references" && !bibliographyOnly ? renderReferencesTab() : null}
      {bibliographyOnly ? renderBibliographyTab() : null}
      {tab === "notes" && !bibliographyOnly ? renderNotesTab() : null}
      {tab === "overview" && !bibliographyOnly ? renderOverviewTab() : null}

      {!bibliographyOnly && collectionModalOpen ? renderCollectionModal() : null}
      {!bibliographyOnly && referenceModalOpen ? renderReferenceModal() : null}
      {bibliographyModalOpen ? renderBibliographyModal() : null}
      {!bibliographyOnly && bibliographyPickerOpen ? renderBibliographyPickerModal() : null}
      {!bibliographyOnly && noteModalOpen ? renderNoteModal() : null}
      {!bibliographyOnly && memberModalOpen ? renderMemberModal() : null}
      {!bibliographyOnly && wbsModalOpen ? renderWbsModal() : null}
    </>
  );

  function renderReferencesTab() {
    if (!selectedCollectionId) {
      return <p className="empty-message">Select a collection to add and manage references.</p>;
    }

    return (
      <>
        <div className="meetings-toolbar">
          <div className="meetings-filter-group">
            <select value={refStatusFilter} onChange={(event) => setRefStatusFilter(event.target.value)}>
              <option value="">All statuses</option>
              <option value="unread">Unread</option>
              <option value="reading">Reading</option>
              <option value="read">Read</option>
              <option value="reviewed">Reviewed</option>
            </select>
            <input
              className="meetings-search"
              type="text"
              placeholder="Search references"
              value={refSearch}
              onChange={(event) => setRefSearch(event.target.value)}
            />
          </div>
        </div>

        {references.length === 0 ? (
          <p className="empty-message">No references in this collection.</p>
        ) : (
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Year</th>
                  <th>Status</th>
                  <th>Source</th>
                  <th className="col-icon" />
                  <th className="col-icon" />
                  <th className="col-icon" />
                </tr>
              </thead>
              <tbody>
                {references.map((reference) => (
                  <tr key={reference.id}>
                    <td>
                      <strong>{reference.title}</strong>
                      <span className="muted-small research-inline-meta">{reference.authors.join(", ") || "-"}</span>
                      {reference.venue ? <span className="muted-small research-inline-meta">{reference.venue}</span> : null}
                      {reference.ai_summary ? (() => {
                        const summary = parseSummaryPayload(reference.ai_summary);
                        return (
                          <details className="research-inline-summary">
                            <summary>AI Summary</summary>
                            {summary?.summary ? <p>{summary.summary}</p> : <p>{reference.ai_summary}</p>}
                            {summary?.contributions?.length ? (
                              <div className="research-bullet-stack">
                                {summary.contributions.slice(0, 2).map((item) => (
                                  <span key={item} className="chip small">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                            {summary?.results?.length ? (
                              <div className="research-bullet-stack">
                                {summary.results.slice(0, 2).map((item) => (
                                  <span key={item} className="chip small">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </details>
                        );
                      })() : null}
                    </td>
                    <td>{reference.year ?? "-"}</td>
                    <td>
                      <select
                        className="research-status-select"
                        value={reference.reading_status}
                        onChange={(event) => handleStatusChange(reference.id, event.target.value)}
                      >
                        <option value="unread">Unread</option>
                        <option value="reading">Reading</option>
                        <option value="read">Read</option>
                        <option value="reviewed">Reviewed</option>
                      </select>
                    </td>
                    <td>
                      <span className="muted-small">{reference.document_key ? "PDF" : "Manual"}</span>
                    </td>
                    <td className="col-icon">
                      <button
                        type="button"
                        className="ghost docs-action-btn"
                        title="Summarize"
                        disabled={summarizingId === reference.id}
                        onClick={() => handleSummarize(reference.id)}
                      >
                        <FontAwesomeIcon icon={faMagicWandSparkles} spin={summarizingId === reference.id} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openEditReferenceModal(reference)}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Delete" onClick={() => handleDeleteReference(reference.id)}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  function renderBibliographyTab() {
    return (
      <>
        <div className="meetings-toolbar">
          <div className="meetings-filter-group">
            <select value={bibliographyVisibilityFilter} onChange={(event) => setBibliographyVisibilityFilter(event.target.value)}>
              <option value="">All visibility</option>
              <option value="shared">Shared</option>
              <option value="private">Private</option>
            </select>
            <input
              className="meetings-search"
              type="text"
              placeholder="Search papers"
              value={bibliographySearch}
              onChange={(event) => setBibliographySearch(event.target.value)}
            />
          </div>
        </div>

        {bibliography.length === 0 ? (
          <p className="empty-message">No papers.</p>
        ) : (
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Visibility</th>
                  <th>Links</th>
                  <th>File</th>
                  <th className="col-icon" />
                  <th className="col-icon" />
                  <th className="col-icon" />
                </tr>
              </thead>
              <tbody>
                {bibliography.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.title}</strong>
                      <span className="muted-small research-inline-meta">{item.authors.join(", ") || "-"}</span>
                      {item.venue || item.year ? (
                        <span className="muted-small research-inline-meta">
                          {[item.venue, item.year].filter(Boolean).join(" · ")}
                        </span>
                      ) : null}
                      {item.doi ? <span className="muted-small research-inline-meta">DOI: {item.doi}</span> : null}
                    </td>
                    <td>
                      <span className="chip small">{item.visibility}</span>
                    </td>
                    <td>{item.linked_project_count}</td>
                    <td>
                      {item.attachment_url ? (
                        <button
                          type="button"
                          className="ghost research-file-link"
                          onClick={() => void handleOpenBibliographyAttachment(item)}
                        >
                          {item.attachment_filename || "Open"}
                        </button>
                      ) : (
                        <span className="muted-small">-</span>
                      )}
                    </td>
                    <td className="col-icon">
                      <button
                        type="button"
                        className="ghost docs-action-btn"
                        title="Link"
                        onClick={() => void handleLinkBibliography(item)}
                        disabled={!selectedCollectionId}
                      >
                        <FontAwesomeIcon icon={faLink} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openEditBibliographyModal(item)}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Delete" onClick={() => void handleDeleteBibliography(item.id)}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  function renderBibliographyPickerModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setBibliographyPickerOpen(false)}>
        <div className="modal-card settings-modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>Import</h3>
            <div className="modal-head-actions">
              <button type="button" className="ghost docs-action-btn" onClick={() => setBibliographyPickerOpen(false)} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>
          <div className="meetings-toolbar">
            <div className="meetings-filter-group">
              <select value={bibliographyVisibilityFilter} onChange={(event) => setBibliographyVisibilityFilter(event.target.value)}>
                <option value="">All visibility</option>
                <option value="shared">Shared</option>
                <option value="private">Private</option>
              </select>
              <input
                className="meetings-search"
                type="text"
                placeholder="Search papers"
                value={bibliographySearch}
                onChange={(event) => setBibliographySearch(event.target.value)}
              />
            </div>
          </div>
          {bibliography.length === 0 ? (
            <p className="empty-message">No papers.</p>
          ) : (
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Visibility</th>
                    <th>File</th>
                    <th className="col-icon" />
                  </tr>
                </thead>
                <tbody>
                  {bibliography.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.title}</strong>
                        <span className="muted-small research-inline-meta">{item.authors.join(", ") || "-"}</span>
                        {item.venue || item.year ? (
                          <span className="muted-small research-inline-meta">
                            {[item.venue, item.year].filter(Boolean).join(" · ")}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span className="chip small">{item.visibility}</span>
                      </td>
                      <td>
                        {item.attachment_url ? (
                          <button
                            type="button"
                            className="ghost research-file-link"
                            onClick={() => void handleOpenBibliographyAttachment(item)}
                          >
                            {item.attachment_filename || "Open"}
                          </button>
                        ) : (
                          <span className="muted-small">-</span>
                        )}
                      </td>
                      <td className="col-icon">
                        <button
                          type="button"
                          className="meetings-new-btn"
                          onClick={() => void handleLinkBibliography(item)}
                        >
                          <FontAwesomeIcon icon={faLink} /> Link
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    );
  }

  function renderNotesTab() {
    if (!selectedCollectionId) {
      return <p className="empty-message">Select a collection to add and manage notes.</p>;
    }

    return (
      <>
        <div className="meetings-toolbar">
          <div className="meetings-filter-group">
            <select value={noteTypeFilter} onChange={(event) => setNoteTypeFilter(event.target.value)}>
              <option value="">All types</option>
              {Object.entries(NOTE_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {notes.length === 0 ? (
          <p className="empty-message">No notes in this collection.</p>
        ) : (
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Title</th>
                  <th>Author</th>
                  <th>Refs</th>
                  <th className="col-icon" />
                  <th className="col-icon" />
                </tr>
              </thead>
              <tbody>
                {notes.map((note) => (
                  <tr key={note.id}>
                    <td>
                      <span className="chip small">{NOTE_TYPE_LABELS[note.note_type] || note.note_type}</span>
                    </td>
                    <td>
                      <strong>{note.title}</strong>
                      <span className="muted-small research-note-preview">
                        {note.content.slice(0, 120)}
                        {note.content.length > 120 ? "..." : ""}
                      </span>
                    </td>
                    <td>
                      <span className="muted-small">{note.author_name || "-"}</span>
                    </td>
                    <td>{note.linked_reference_ids.length || "-"}</td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openEditNoteModal(note)}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Delete" onClick={() => handleDeleteNote(note.id)}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  function renderOverviewTab() {
    if (!collectionDetail || !selectedCollectionId) {
      return <p className="empty-message">Select a collection to manage it.</p>;
    }

    const synthesis = parseSynthesisPayload(collectionDetail.ai_synthesis);

    return (
      <div className="research-overview">
        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Collection</strong>
            </div>
            <button type="button" className="meetings-new-btn" onClick={openEditCollectionModal}>
              <FontAwesomeIcon icon={faPen} /> Edit
            </button>
          </div>
          <div className="research-overview-body">
            <p>{collectionDetail.description || "No description."}</p>
            {collectionDetail.hypothesis ? <p className="research-hypothesis">{collectionDetail.hypothesis}</p> : null}
            {collectionDetail.open_questions.length > 0 ? (
              <div className="research-bullet-stack">
                {collectionDetail.open_questions.map((item) => (
                  <span key={item} className="chip small">
                    {item}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="research-meta-grid">
              <span className="muted-small">Output: {collectionDetail.target_output_title || "-"}</span>
              <span className="muted-small">Status: {collectionDetail.output_status.replace(/_/g, " ")}</span>
              <span className="muted-small">
                Overleaf:{" "}
                {collectionDetail.overleaf_url ? (
                  <a href={collectionDetail.overleaf_url} target="_blank" rel="noreferrer">
                    Open
                  </a>
                ) : (
                  "-"
                )}
              </span>
            </div>
          </div>
        </div>

        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <FontAwesomeIcon icon={faLink} />
              <strong>Context Links</strong>
            </div>
            <button type="button" className="meetings-new-btn" onClick={openWbsModal}>
              <FontAwesomeIcon icon={faPen} /> Edit
            </button>
          </div>
          <div className="research-overview-body">
            <div className="research-chip-group">
              {collectionDetail.wp_ids.map((id) => {
                const item = wps.find((entry) => entry.id === id);
                return item ? (
                  <span key={id} className="chip small">
                    {item.code}
                  </span>
                ) : null;
              })}
              {collectionDetail.task_ids.map((id) => {
                const item = tasks.find((entry) => entry.id === id);
                return item ? (
                  <span key={id} className="chip small">
                    {item.code}
                  </span>
                ) : null;
              })}
              {collectionDetail.deliverable_ids.map((id) => {
                const item = deliverables.find((entry) => entry.id === id);
                return item ? (
                  <span key={id} className="chip small">
                    {item.code}
                  </span>
                ) : null;
              })}
              {collectionDetail.wp_ids.length === 0 &&
              collectionDetail.task_ids.length === 0 &&
              collectionDetail.deliverable_ids.length === 0 &&
              collectionDetail.meetings.length === 0 ? (
                <span className="muted-small">No links.</span>
              ) : null}
            </div>
            {collectionDetail.meetings.length > 0 ? (
              <div className="research-meeting-list">
                {collectionDetail.meetings.map((meeting) => (
                  <div key={meeting.id} className="research-meeting-row">
                    <span className="chip small">
                      <FontAwesomeIcon icon={faCalendarDay} /> {meeting.title}
                    </span>
                    <span className="muted-small">{new Date(meeting.starts_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <FontAwesomeIcon icon={faUsers} />
              <strong>Team Members</strong>
              <span className="delivery-tab-count">{collectionDetail.members.length}</span>
            </div>
            <button type="button" className="meetings-new-btn" onClick={() => setMemberModalOpen(true)}>
              <FontAwesomeIcon icon={faPlus} /> Add
            </button>
          </div>
          {collectionDetail.members.length === 0 ? (
            <p className="muted-small research-overview-body">No members.</p>
          ) : (
            <div className="research-member-list">
              {collectionDetail.members.map((member: ResearchCollectionMember) => (
                <div key={member.id} className="research-member-row">
                  <div>
                    <strong>{member.member_name}</strong>
                    <span className="muted-small research-inline-meta">{member.organization_short_name}</span>
                  </div>
                  <div className="research-member-actions">
                    <select value={member.role} onChange={(event) => void handleUpdateMemberRole(member.id, event.target.value)}>
                      <option value="lead">Lead</option>
                      <option value="contributor">Contributor</option>
                      <option value="reviewer">Reviewer</option>
                    </select>
                    <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => handleRemoveMember(member.id)}>
                      <FontAwesomeIcon icon={faXmark} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <FontAwesomeIcon icon={faMagicWandSparkles} />
              <strong>AI Synthesis</strong>
            </div>
            <button type="button" className="meetings-new-btn" disabled={synthesizing} onClick={handleSynthesize}>
              {synthesizing ? "Synthesizing..." : "Synthesize"}
            </button>
          </div>
          <div className="research-overview-body">
            {collectionDetail.ai_synthesis ? (
              <>
                {synthesis?.summary ? <p className="research-synthesis-text">{synthesis.summary}</p> : <p className="research-synthesis-text">{collectionDetail.ai_synthesis}</p>}
                {synthesis?.knowledge_state?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Knowledge State</strong>
                    <div className="research-bullet-stack">
                      {synthesis.knowledge_state.map((item) => (
                        <span key={item} className="chip small">{item}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesis?.findings?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Findings</strong>
                    <div className="research-bullet-stack">
                      {synthesis.findings.map((item) => (
                        <span key={item} className="chip small">{item}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesis?.discussion_points?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Discussions</strong>
                    <div className="research-bullet-stack">
                      {synthesis.discussion_points.map((item) => (
                        <span key={item} className="chip small">{item}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesis?.decisions?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Decisions</strong>
                    <div className="research-bullet-stack">
                      {synthesis.decisions.map((item) => (
                        <span key={item} className="chip small">{item}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesis?.tasks?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Tasks</strong>
                    <div className="research-bullet-stack">
                      {synthesis.tasks.map((item) => (
                        <span key={item} className="chip small">{item}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesis?.output_readiness ? (
                  <div className="research-synthesis-group">
                    <strong>Output Readiness</strong>
                    <div className="research-meta-grid">
                      <span className="muted-small">Status: {synthesis.output_readiness.status || "-"}</span>
                    </div>
                    {synthesis.output_readiness.missing?.length ? (
                      <div className="research-bullet-stack">
                        {synthesis.output_readiness.missing.map((item) => (
                          <span key={item} className="chip small">{item}</span>
                        ))}
                      </div>
                    ) : null}
                    {synthesis.output_readiness.next_actions?.length ? (
                      <div className="research-bullet-stack">
                        {synthesis.output_readiness.next_actions.map((item) => (
                          <span key={item} className="chip small">{item}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {synthesis?.open_questions?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Open Questions</strong>
                    <div className="research-bullet-stack">
                      {synthesis.open_questions.map((item) => (
                        <span key={item} className="chip small">{item}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {synthesis?.evidence?.length ? (
                  <div className="research-synthesis-group">
                    <strong>Evidence</strong>
                    <div className="research-evidence-list">
                      {synthesis.evidence.map((item, index) => (
                        <div key={`${item.claim || "claim"}-${index}`} className="research-evidence-row">
                          <span>{item.claim || "-"}</span>
                          {item.sources?.length ? <span className="muted-small">{item.sources.join(", ")}</span> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {collectionDetail.ai_synthesis_at ? (
                  <span className="muted-small">Generated: {new Date(collectionDetail.ai_synthesis_at).toLocaleString()}</span>
                ) : null}
              </>
            ) : (
              <p className="muted-small">No synthesis.</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  function renderCollectionModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setCollectionModalOpen(false)}>
        <div className="modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{collectionModalMode === "create" ? "New Collection" : "Edit Collection"}</h3>
            <button type="button" className="ghost" onClick={() => setCollectionModalOpen(false)}>
              Close
            </button>
          </div>
          <div className="form-grid">
            <label className="full-span">
              Title *
              <input value={collectionTitle} onChange={(event) => setCollectionTitle(event.target.value)} autoFocus />
            </label>
            <label className="full-span">
              Description
              <textarea value={collectionDescription} onChange={(event) => setCollectionDescription(event.target.value)} rows={4} />
            </label>
            <label className="full-span">
              Hypothesis
              <textarea value={collectionHypothesis} onChange={(event) => setCollectionHypothesis(event.target.value)} rows={3} />
            </label>
            <label className="full-span">
              Open Questions
              <input value={collectionOpenQuestions} onChange={(event) => setCollectionOpenQuestions(event.target.value)} />
            </label>
            <label className="full-span">
              Output Title
              <input value={collectionOutputTitle} onChange={(event) => setCollectionOutputTitle(event.target.value)} />
            </label>
            <label className="full-span">
              Overleaf URL
              <input value={collectionOverleafUrl} onChange={(event) => setCollectionOverleafUrl(event.target.value)} />
            </label>
            <label>
              Output Status
              <select value={collectionOutputStatus} onChange={(event) => setCollectionOutputStatus(event.target.value)}>
                <option value="not_started">Not started</option>
                <option value="drafting">Drafting</option>
                <option value="internal_review">Internal review</option>
                <option value="submitted">Submitted</option>
                <option value="published">Published</option>
              </select>
            </label>
            {collectionModalMode === "edit" ? (
              <label>
                Status
                <select value={collectionStatus} onChange={(event) => setCollectionStatus(event.target.value)}>
                  <option value="active">Active</option>
                  <option value="archived">Archived</option>
                  <option value="completed">Completed</option>
                </select>
              </label>
            ) : null}
          </div>
          <div className="row-actions">
            <button type="button" disabled={!collectionTitle.trim() || saving} onClick={handleSaveCollection}>
              {saving ? "Saving..." : collectionModalMode === "create" ? "Create Collection" : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderReferenceModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setReferenceModalOpen(false)}>
        <div className="modal-card settings-modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{referenceModalMode === "create" ? "Reference" : "Edit Reference"}</h3>
            <button type="button" className="ghost" onClick={() => setReferenceModalOpen(false)}>
              Close
            </button>
          </div>
          <div className="delivery-tabs" style={{ marginBottom: 0 }}>
            <button className={`delivery-tab ${referenceModalTab === "manual" ? "active" : ""}`} onClick={() => setReferenceModalTab("manual")}>
              Manual
            </button>
            <button className={`delivery-tab ${referenceModalTab === "pdf" ? "active" : ""}`} onClick={() => setReferenceModalTab("pdf")}>
              <FontAwesomeIcon icon={faFileArrowUp} /> Upload PDF
            </button>
            <button className={`delivery-tab ${referenceModalTab === "document" ? "active" : ""}`} onClick={() => setReferenceModalTab("document")}>
              <FontAwesomeIcon icon={faLink} /> Link Document
            </button>
            {referenceModalMode === "create" ? (
              <button className={`delivery-tab ${referenceModalTab === "bibtex" ? "active" : ""}`} onClick={() => setReferenceModalTab("bibtex")}>
                <FontAwesomeIcon icon={faFileImport} /> BibTeX
              </button>
            ) : null}
          </div>

          <div className="form-grid">
            <label className="full-span">
              Collection *
              <select value={referenceCollectionId} onChange={(event) => setReferenceCollectionId(event.target.value)}>
                <option value="">Select collection</option>
                {activeCollections.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>

            {referenceModalTab === "pdf" ? (
              <label className="full-span">
                PDF *
                <input type="file" accept="application/pdf" onChange={(event) => setReferencePdfFile(event.target.files?.[0] || null)} />
              </label>
            ) : null}

            {referenceModalTab === "document" ? (
              <label className="full-span">
                Document *
                <select value={existingDocumentKey} onChange={(event) => setExistingDocumentKey(event.target.value)}>
                  <option value="">Select document</option>
                  {availableDocuments.map((item) => (
                    <option key={item.document_key} value={item.document_key}>
                      {item.title} [{item.status}]
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            {referenceModalTab !== "bibtex" ? (
              <>
                <label className="full-span">
                  Title *
                  <input value={referenceTitle} onChange={(event) => setReferenceTitle(event.target.value)} autoFocus />
                </label>
                <label className="full-span">
                  Authors
                  <input value={referenceAuthors} onChange={(event) => setReferenceAuthors(event.target.value)} />
                </label>
                <label>
                  Year
                  <input type="number" value={referenceYear} onChange={(event) => setReferenceYear(event.target.value)} />
                </label>
                <label>
                  Venue
                  <input value={referenceVenue} onChange={(event) => setReferenceVenue(event.target.value)} />
                </label>
                <label>
                  DOI
                  <input value={referenceDoi} onChange={(event) => setReferenceDoi(event.target.value)} />
                </label>
                <label>
                  URL
                  <input value={referenceUrl} onChange={(event) => setReferenceUrl(event.target.value)} />
                </label>
                <label>
                  Status
                  <select value={referenceReadingStatus} onChange={(event) => setReferenceReadingStatus(event.target.value)}>
                    <option value="unread">Unread</option>
                    <option value="reading">Reading</option>
                    <option value="read">Read</option>
                    <option value="reviewed">Reviewed</option>
                  </select>
                </label>
                <label className="full-span">
                  Abstract
                  <textarea value={referenceAbstract} onChange={(event) => setReferenceAbstract(event.target.value)} rows={5} />
                </label>
              </>
            ) : null}

            {referenceModalTab === "bibtex" ? (
              <label className="full-span">
                BibTeX *
                <textarea value={bibtexInput} onChange={(event) => setBibtexInput(event.target.value)} rows={12} autoFocus />
              </label>
            ) : null}
          </div>

          {bibtexResult ? (
            <div className="research-bibtex-result">
              {bibtexResult.created > 0 ? <span className="chip small">{bibtexResult.created} imported</span> : null}
              {bibtexResult.errors.map((item, index) => (
                <span key={`${item}-${index}`} className="chip small research-bibtex-error">
                  {item}
                </span>
              ))}
            </div>
          ) : null}

          <div className="row-actions">
            {referenceModalTab === "bibtex" ? (
              <button type="button" disabled={!referenceCollectionId || !bibtexInput.trim() || saving} onClick={handleImportBibtex}>
                {saving ? "Importing..." : "Import"}
              </button>
            ) : null}
            {referenceModalTab === "pdf" ? (
              <button type="button" disabled={!referenceCollectionId || !referencePdfFile || saving} onClick={handleUploadPdfReference}>
                {saving ? "Uploading..." : referenceModalMode === "create" ? "Upload PDF" : "Upload PDF and Save"}
              </button>
            ) : null}
            {referenceModalTab === "document" ? (
              <button type="button" disabled={!referenceCollectionId || !existingDocumentKey || saving} onClick={handleSaveReferenceFromExistingDocument}>
                {saving ? "Saving..." : referenceModalMode === "create" ? "Add Reference" : "Save"}
              </button>
            ) : null}
            {referenceModalTab === "manual" ? (
              <button
                type="button"
                disabled={!referenceCollectionId || !referenceTitle.trim() || saving}
                onClick={handleSaveReference}
              >
                {saving ? "Saving..." : referenceModalMode === "create" ? "Add Reference" : "Save"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  function renderBibliographyModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setBibliographyModalOpen(false)}>
        <div className="modal-card settings-modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{bibliographyModalMode === "create" ? "Paper" : "Edit Paper"}</h3>
            <div className="modal-head-actions">
              <button
                type="button"
                disabled={(!bibliographyTitle.trim() && !bibliographyBibtexInput.trim()) || saving}
                onClick={() => void (bibliographyBibtexInput.trim() ? handleImportBibliographyBibtex() : handleSaveBibliography())}
              >
                {saving ? (bibliographyBibtexInput.trim() ? "Importing..." : "Saving...") : bibliographyModalMode === "create" ? "Add" : "Save"}
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={() => setBibliographyModalOpen(false)} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>

          <div className="form-grid">
            <label>
              Visibility
              <select value={bibliographyVisibility} onChange={(event) => setBibliographyVisibility(event.target.value)}>
                <option value="shared">Shared</option>
                <option value="private">Private</option>
              </select>
            </label>
            <label>
              PDF
              <input type="file" accept="application/pdf" onChange={(event) => setBibliographyAttachmentFile(event.target.files?.[0] || null)} />
            </label>
            <label className="full-span">
              BibTeX
              <textarea value={bibliographyBibtexInput} onChange={(event) => setBibliographyBibtexInput(event.target.value)} rows={10} autoFocus={bibliographyModalMode === "create"} />
            </label>
            <label className="full-span">
              Title
              <input value={bibliographyTitle} onChange={(event) => setBibliographyTitle(event.target.value)} />
            </label>
            <label className="full-span">
              Authors
              <input value={bibliographyAuthors} onChange={(event) => setBibliographyAuthors(event.target.value)} />
            </label>
            <label>
              Year
              <input type="number" value={bibliographyYear} onChange={(event) => setBibliographyYear(event.target.value)} />
            </label>
            <label>
              DOI
              <input value={bibliographyDoi} onChange={(event) => setBibliographyDoi(event.target.value)} />
            </label>
            <label className="full-span">
              Venue
              <input value={bibliographyVenue} onChange={(event) => setBibliographyVenue(event.target.value)} />
            </label>
            <label className="full-span">
              URL
              <input value={bibliographyUrl} onChange={(event) => setBibliographyUrl(event.target.value)} />
            </label>
            <label className="full-span">
              Abstract
              <textarea value={bibliographyAbstract} onChange={(event) => setBibliographyAbstract(event.target.value)} rows={6} />
            </label>
          </div>

          {bibliographyBibtexResult ? (
            <div className="research-bibtex-result">
              {bibliographyBibtexResult.created > 0 ? <span className="chip small">{bibliographyBibtexResult.created} imported</span> : null}
              {bibliographyBibtexResult.errors.map((item, index) => (
                <span key={`${item}-${index}`} className="chip small research-bibtex-error">
                  {item}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  function renderNoteModal() {
    const linkableReferences = allReferences.filter((item) => !noteCollectionId || item.collection_id === noteCollectionId);

    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setNoteModalOpen(false)}>
        <div className="modal-card settings-modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{noteModalMode === "create" ? "Note" : "Edit Note"}</h3>
            <button type="button" className="ghost" onClick={() => setNoteModalOpen(false)}>
              Close
            </button>
          </div>
          <div className="form-grid">
            <label className="full-span">
              Collection *
              <select value={noteCollectionId} onChange={(event) => setNoteCollectionId(event.target.value)}>
                <option value="">Select collection</option>
                {activeCollections.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="full-span">
              Title *
              <input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} autoFocus />
            </label>
            <label>
              Type
              <select value={noteType} onChange={(event) => setNoteType(event.target.value)}>
                {Object.entries(NOTE_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="full-span">
              Content *
              <textarea value={noteContent} onChange={(event) => setNoteContent(event.target.value)} rows={8} />
            </label>
            <div className="full-span">
              <strong>References</strong>
              <div className="research-checkbox-list">
                {linkableReferences.length === 0 ? <span className="muted-small">No references.</span> : null}
                {linkableReferences.map((item) => (
                  <label key={item.id} className="research-check-item">
                    <input
                      type="checkbox"
                      checked={noteReferenceIds.includes(item.id)}
                      onChange={() => setNoteReferenceIds((current) => toggleListValue(current, item.id))}
                    />
                    <span>{item.title}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="row-actions">
            <button type="button" disabled={!noteCollectionId || !noteTitle.trim() || !noteContent.trim() || saving} onClick={handleSaveNote}>
              {saving ? "Saving..." : noteModalMode === "create" ? "Add Note" : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderMemberModal() {
    const existingMemberIds = new Set(collectionDetail?.members.map((item) => item.member_id) || []);
    const availableMembersForCollection = members.filter((item) => !existingMemberIds.has(item.id));

    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setMemberModalOpen(false)}>
        <div className="modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>Add Member</h3>
            <button type="button" className="ghost" onClick={() => setMemberModalOpen(false)}>
              Close
            </button>
          </div>
          <div className="form-grid">
            <label>
              Member
              <select value={newMemberId} onChange={(event) => setNewMemberId(event.target.value)}>
                <option value="">Select member</option>
                {availableMembersForCollection.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Role
              <select value={newMemberRole} onChange={(event) => setNewMemberRole(event.target.value)}>
                <option value="lead">Lead</option>
                <option value="contributor">Contributor</option>
                <option value="reviewer">Reviewer</option>
              </select>
            </label>
          </div>
          <div className="row-actions">
            <button type="button" disabled={!newMemberId || saving} onClick={handleAddMember}>
              {saving ? "Adding..." : "Add Member"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderWbsModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setWbsModalOpen(false)}>
        <div className="modal-card settings-modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>Context Links</h3>
            <button type="button" className="ghost" onClick={() => setWbsModalOpen(false)}>
              Close
            </button>
          </div>
          <div className="form-grid">
            <div>
              <strong>Work Packages</strong>
              <div className="research-checkbox-list">
                {wps.map((item) => (
                  <label key={item.id} className="research-check-item">
                    <input type="checkbox" checked={wbsWpIds.includes(item.id)} onChange={() => setWbsWpIds((current) => toggleListValue(current, item.id))} />
                    <span>{item.code}</span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <strong>Tasks</strong>
              <div className="research-checkbox-list">
                {tasks.map((item) => (
                  <label key={item.id} className="research-check-item">
                    <input type="checkbox" checked={wbsTaskIds.includes(item.id)} onChange={() => setWbsTaskIds((current) => toggleListValue(current, item.id))} />
                    <span>{item.code}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="full-span">
              <strong>Deliverables</strong>
              <div className="research-checkbox-list research-checkbox-list-wide">
                {deliverables.map((item) => (
                  <label key={item.id} className="research-check-item">
                    <input
                      type="checkbox"
                      checked={wbsDeliverableIds.includes(item.id)}
                      onChange={() => setWbsDeliverableIds((current) => toggleListValue(current, item.id))}
                    />
                    <span>{item.code}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="full-span">
              <strong>Meetings</strong>
              <div className="research-checkbox-list research-checkbox-list-wide">
                {projectMeetings.map((item) => (
                  <label key={item.id} className="research-check-item">
                    <input
                      type="checkbox"
                      checked={meetingIds.includes(item.id)}
                      onChange={() => setMeetingIds((current) => toggleListValue(current, item.id))}
                    />
                    <span>{item.title}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="row-actions">
            <button type="button" disabled={saving} onClick={handleSaveWbsLinks}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }
}
