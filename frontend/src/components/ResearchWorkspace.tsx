import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArchive,
  faBookOpen,
  faCalendarDay,
  faChevronRight,
  faChevronUp,
  faChevronDown,
  faFileArrowUp,
  faComment,
  faFileExport,
  faFileImport,
  faFilter,
  faFlask,
  faInbox,
  faLink,
  faMagicWandSparkles,
  faPen,
  faPlus,
  faSearch,
  faShareNodes,
  faTrash,
  faUsers,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import { useStatusToast } from "../lib/useStatusToast";
import { BibliographyGraphModal } from "./BibliographyGraphModal";
import { renderMarkdown } from "../lib/renderMarkdown";
import { formatRelativeTime } from "../lib/formatRelativeTime";
import { SkeletonTable, SkeletonCards } from "./Skeleton";
import { useConfirmDelete } from "../lib/useConfirmDelete";
import { useQuickSearch } from "../lib/useQuickSearch";
import type {
  BibliographyCollection,
  BibliographyDuplicateMatch,
  BibliographyNote,
  BibliographyReference,
  BibliographyTag,
  DocumentListItem,
  Member,
  MeetingRecord,
  Project,
  ResearchCollection,
  ResearchCollectionDetail,
  ResearchCollectionMember,
  ResearchNote,
  ResearchPaperAuthor,
  ResearchPaperClaim,
  ResearchPaperQuestion,
  ResearchPaperSection,
  ResearchStudyIteration,
  ResearchResultComparison,
  ResearchStudyResult,
  ResearchReference,
  WorkEntity,
} from "../types";

const NOTE_LANE_LABELS: Record<string, string> = {
  gap: "Gap",
  method: "Method",
  evaluation: "Evaluation",
  writing: "Writing",
  decision: "Decision",
};

const NOTE_LANE_OPTIONS = Object.entries(NOTE_LANE_LABELS);

type Tab = "references" | "notes" | "paper" | "iterations" | "overview";
type CollectionModalMode = "create" | "edit";
type ReferenceModalMode = "create" | "edit";
type NoteModalMode = "create" | "edit";
type ReferenceModalTab = "manual" | "bibtex" | "pdf" | "document";
type BibliographyModalMode = "create" | "edit";
type BibliographyCreateTab = "manual" | "batch";
type BibTab = "papers" | "collections";

function csvToList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function toggleListValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function moveItem<T>(items: T[], fromIndex: number, toIndex: number): T[] {
  if (toIndex < 0 || toIndex >= items.length || fromIndex === toIndex) return items;
  const next = [...items];
  const [item] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, item);
  return next;
}

function normalizeTagLabel(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function bibliographyDocumentStatusLabel(status: string | null): string {
  if (status === "indexed") return "Indexed";
  if (status === "uploaded") return "Pending";
  if (status === "failed") return "Failed";
  if (status === "no_pdf") return "No PDF";
  return "Pending";
}

type PaperSummaryPayload = {
  summary?: string | { text?: string; chunk_ids?: string[] };
  problem?: string | { text?: string; chunk_ids?: string[] };
  contributions?: Array<string | { text?: string; chunk_ids?: string[] }>;
  approach?: Array<string | { text?: string; chunk_ids?: string[] }>;
  experimental_setup?: Array<string | { text?: string; chunk_ids?: string[] }>;
  datasets_or_benchmarks?: Array<string | { text?: string; chunk_ids?: string[] }>;
  baselines?: Array<string | { text?: string; chunk_ids?: string[] }>;
  methods?: Array<string | { text?: string; chunk_ids?: string[] }>;
  results?: Array<string | { text?: string; chunk_ids?: string[] }>;
  quantitative_results?: Array<string | { text?: string; chunk_ids?: string[] }>;
  limitations?: Array<string | { text?: string; chunk_ids?: string[] }>;
  failure_modes?: Array<string | { text?: string; chunk_ids?: string[] }>;
  conclusion?: string | { text?: string; chunk_ids?: string[] };
  takeaways?: Array<string | { text?: string; chunk_ids?: string[] }>;
  open_questions?: Array<string | { text?: string; chunk_ids?: string[] }>;
};

type SummaryItem = {
  text: string;
  chunkIds: string[];
};

function parseSummaryPayload(value: string | null): PaperSummaryPayload | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as PaperSummaryPayload;
    return typeof parsed === "object" && parsed ? parsed : null;
  } catch {
    return null;
  }
}

function normalizeSummaryItem(value: string | { text?: string; chunk_ids?: string[] } | undefined | null): SummaryItem | null {
  if (!value) return null;
  if (typeof value === "string") {
    const text = value.trim();
    return text ? { text, chunkIds: [] } : null;
  }
  const text = String(value.text || "").trim();
  if (!text) return null;
  const chunkIds = Array.isArray(value.chunk_ids)
    ? value.chunk_ids.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  return { text, chunkIds };
}

function renderSummarySingle(title: string, item: string | { text?: string; chunk_ids?: string[] } | undefined) {
  const normalized = normalizeSummaryItem(item);
  if (!normalized) return null;
  return (
    <section className="research-summary-section research-summary-section-single">
      <div className="research-summary-head">
        <span className="bib-section-label">{title}</span>
      </div>
      <p className="research-summary-item research-summary-item-strong">
        {normalized.text}
        {normalized.chunkIds.length ? normalized.chunkIds.map((chunkId) => (
          <span key={`${title}-${chunkId}`} className="chip small research-summary-cite-inline">{chunkId}</span>
        )) : null}
      </p>
    </section>
  );
}

function renderSummaryList(title: string, items: Array<string | { text?: string; chunk_ids?: string[] }> | undefined, limit?: number) {
  if (!items?.length) return null;
  const normalized = items.map((item) => normalizeSummaryItem(item)).filter(Boolean) as SummaryItem[];
  if (!normalized.length) return null;
  const visible = typeof limit === "number" ? normalized.slice(0, limit) : normalized;
  return (
    <section className="research-summary-section">
      <div className="research-summary-head">
        <span className="bib-section-label">{title}</span>
        <span className="delivery-tab-count">{visible.length}</span>
      </div>
      <div className="research-summary-list">
        {visible.map((item, index) => (
          <div key={`${title}-${item.text}`} className="research-summary-cited-item">
            <div className="research-summary-row">
              <span className="research-summary-index">{index + 1}</span>
              <p className="research-summary-item">
                {item.text}
                {item.chunkIds.length ? item.chunkIds.map((chunkId) => (
                  <span key={`${title}-${item.text}-${chunkId}`} className="chip small research-summary-cite-inline">{chunkId}</span>
                )) : null}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function renderPaperSummary(summary: PaperSummaryPayload | null, rawValue: string, options?: { compact?: boolean }) {
  if (!summary) {
    return <p>{rawValue}</p>;
  }

  const compact = options?.compact ?? false;
  return (
    <div className={`research-summary-brief${compact ? " compact" : ""}`}>
      {renderSummarySingle("Summary", summary.summary)}
      {renderSummarySingle("Problem", summary.problem)}
      {renderSummaryList("Contributions", summary.contributions, compact ? 3 : undefined)}
      {renderSummaryList("Approach", summary.approach, compact ? 2 : undefined)}
      {renderSummaryList("Setup", summary.experimental_setup, compact ? 2 : undefined)}
      {renderSummaryList("Data", summary.datasets_or_benchmarks, compact ? 2 : undefined)}
      {renderSummaryList("Baselines", summary.baselines, compact ? 2 : undefined)}
      {renderSummaryList("Methods", summary.methods, compact ? 2 : undefined)}
      {renderSummaryList("Results", summary.results, compact ? 3 : undefined)}
      {renderSummaryList("Numbers", summary.quantitative_results, compact ? 3 : undefined)}
      {renderSummaryList("Limitations", summary.limitations, compact ? 2 : undefined)}
      {renderSummaryList("Failure Modes", summary.failure_modes, compact ? 2 : undefined)}
      {renderSummarySingle("Conclusion", summary.conclusion)}
      {renderSummaryList("Takeaways", summary.takeaways, compact ? 3 : undefined)}
      {renderSummaryList("Open Questions", summary.open_questions, compact ? 2 : undefined)}
    </div>
  );
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

function formatLogTimestamp(value: string): string {
  const date = new Date(value);
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatLogDate(value: string): string {
  const date = new Date(value);
  return date.toLocaleDateString([], {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function deriveLogTitle(content: string): string {
  const firstLine = content
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);
  const base = firstLine || content.trim();
  const collapsed = base.replace(/\s+/g, " ").trim();
  if (!collapsed) return "";
  return collapsed.length > 72 ? `${collapsed.slice(0, 72).trimEnd()}...` : collapsed;
}

export function ResearchWorkspace({
  selectedProjectId,
  bibliographyOnly = false,
  isAdmin = false,
  currentProject = null,
  openBibliographyReferenceId = null,
  onOpenBibliographyReferenceConsumed,
}: {
  selectedProjectId: string;
  bibliographyOnly?: boolean;
  isAdmin?: boolean;
  currentProject?: Project | null;
  openBibliographyReferenceId?: string | null;
  onOpenBibliographyReferenceConsumed?: () => void;
}) {
  const [collections, setCollections] = useState<ResearchCollection[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [bulkResearchTargetCollectionId, setBulkResearchTargetCollectionId] = useState("");
  const [collectionDetail, setCollectionDetail] = useState<ResearchCollectionDetail | null>(null);

  const [references, setReferences] = useState<ResearchReference[]>([]);
  const [bibliography, setBibliography] = useState<BibliographyReference[]>([]);
  const [bibliographyCollections, setBibliographyCollections] = useState<BibliographyCollection[]>([]);
  const [selectedBibliographyCollectionId, setSelectedBibliographyCollectionId] = useState<string | null>(null);
  const [selectedBibliographyCollectionPaperIds, setSelectedBibliographyCollectionPaperIds] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState<ResearchNote[]>([]);
  const [allReferences, setAllReferences] = useState<ResearchReference[]>([]);
  const [projectDocuments, setProjectDocuments] = useState<DocumentListItem[]>([]);
  const [projectMeetings, setProjectMeetings] = useState<MeetingRecord[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [wps, setWps] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);

  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const { error, setError, status, setStatus } = useStatusToast();
  const [showArchived, setShowArchived] = useState(false);

  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [collectionModalMode, setCollectionModalMode] = useState<CollectionModalMode>("create");
  const [referenceModalOpen, setReferenceModalOpen] = useState(false);
  const [referenceModalMode, setReferenceModalMode] = useState<ReferenceModalMode>("create");
  const [noteModalOpen, setNoteModalOpen] = useState(false);
  const [noteModalMode, setNoteModalMode] = useState<NoteModalMode>("create");
  const [bibliographyModalOpen, setBibliographyModalOpen] = useState(false);
  const [bibliographyCollectionModalOpen, setBibliographyCollectionModalOpen] = useState(false);
  const [bibliographyDuplicateModalOpen, setBibliographyDuplicateModalOpen] = useState(false);
  const [bibliographyPickerOpen, setBibliographyPickerOpen] = useState(false);
  const [bibliographyModalMode, setBibliographyModalMode] = useState<BibliographyModalMode>("create");
  const [bibliographyCreateTab, setBibliographyCreateTab] = useState<BibliographyCreateTab>("manual");
  const [bibliographyCollectionModalMode, setBibliographyCollectionModalMode] = useState<"create" | "edit">("create");
  const [memberModalOpen, setMemberModalOpen] = useState(false);
  const [wbsModalOpen, setWbsModalOpen] = useState(false);

  const [editingCollectionId, setEditingCollectionId] = useState<string | null>(null);
  const [editingReferenceId, setEditingReferenceId] = useState<string | null>(null);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingBibliographyId, setEditingBibliographyId] = useState<string | null>(null);
  const [editingBibliographyCollectionId, setEditingBibliographyCollectionId] = useState<string | null>(null);

  const [collectionTitle, setCollectionTitle] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [collectionStatus, setCollectionStatus] = useState("active");
  const [paperTitle, setPaperTitle] = useState("");
  const [paperMotivation, setPaperMotivation] = useState("");
  const [paperVenue, setPaperVenue] = useState("");
  const [paperOverleafUrl, setPaperOverleafUrl] = useState("");
  const [paperStatus, setPaperStatus] = useState("not_started");
  const [paperRegistrationDeadline, setPaperRegistrationDeadline] = useState("");
  const [paperSubmissionDeadline, setPaperSubmissionDeadline] = useState("");
  const [paperDecisionDate, setPaperDecisionDate] = useState("");
  const [studyIterations, setStudyIterations] = useState<ResearchStudyIteration[]>([]);
  const [studyResults, setStudyResults] = useState<ResearchStudyResult[]>([]);
  const [resultComparison, setResultComparison] = useState<ResearchResultComparison | null>(null);
  const [paperAuthors, setPaperAuthors] = useState<ResearchPaperAuthor[]>([]);
  const [paperQuestions, setPaperQuestions] = useState<ResearchPaperQuestion[]>([]);
  const [paperClaims, setPaperClaims] = useState<ResearchPaperClaim[]>([]);
  const [paperSections, setPaperSections] = useState<ResearchPaperSection[]>([]);
  const [paperExpanded, setPaperExpanded] = useState(false);
  const [paperDirty, setPaperDirty] = useState(false);

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
  const [noteLane, setNoteLane] = useState("");
  const [noteReferenceIds, setNoteReferenceIds] = useState<string[]>([]);
  const [quickLogContent, setQuickLogContent] = useState("");
  const [quickLogTitle, setQuickLogTitle] = useState("");
  const [quickLogLane, setQuickLogLane] = useState("");
  const [quickLogRefIds, setQuickLogRefIds] = useState<string[]>([]);

  const [newMemberId, setNewMemberId] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("contributor");

  const [wbsWpIds, setWbsWpIds] = useState<string[]>([]);
  const [wbsTaskIds, setWbsTaskIds] = useState<string[]>([]);
  const [wbsDeliverableIds, setWbsDeliverableIds] = useState<string[]>([]);
  const [meetingIds, setMeetingIds] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [summarizingId, setSummarizingId] = useState<string | null>(null);
  const [auditingPaperClaims, setAuditingPaperClaims] = useState(false);
  const [buildingPaperOutline, setBuildingPaperOutline] = useState(false);
  const [draftingGapPaper, setDraftingGapPaper] = useState(false);
  const [reviewingIterationId, setReviewingIterationId] = useState<string | null>(null);
  const [comparingResults, setComparingResults] = useState(false);
  const [expandedIterationId, setExpandedIterationId] = useState<string | null>(null);

  const [refSearch, setRefSearch] = useState("");
  const [bibTab, setBibTab] = useState<BibTab>("papers");
  const [addToCollectionId, setAddToCollectionId] = useState("");
  const [addToCollectionModalOpen, setAddToCollectionModalOpen] = useState(false);
  const [bibliographySearch, setBibliographySearch] = useState("");
  const [bibliographyVisibilityFilter, setBibliographyVisibilityFilter] = useState("");
  const [bibliographyTagFilter, setBibliographyTagFilter] = useState("");
  const [bibliographyStatusFilter, setBibliographyStatusFilter] = useState("");
  const [bibliographyFiltersOpen, setBibliographyFiltersOpen] = useState(false);
  const [bibSortKey, setBibSortKey] = useState<"title" | "year" | "status" | "created_at">("created_at");
  const [bibSortDir, setBibSortDir] = useState<"asc" | "desc">("desc");
  const { confirmingId: confirmingDeleteId, requestConfirm: requestConfirmDelete } = useConfirmDelete();

  function toggleBibSort(key: typeof bibSortKey) {
    if (bibSortKey === key) {
      setBibSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setBibSortKey(key);
      setBibSortDir("asc");
    }
  }
  const [selectedBibIds, setSelectedBibIds] = useState<Set<string>>(new Set());
  const [semanticSearch, setSemanticSearch] = useState(false);
  const [searchingBibliography, setSearchingBibliography] = useState(false);
  const [expandedBibId, setExpandedBibId] = useState<string | null>(null);
  const [expandedBibNotes, setExpandedBibNotes] = useState<BibliographyNote[]>([]);
  const [expandedBibNotesLoading, setExpandedBibNotesLoading] = useState(false);
  const [newNoteContent, setNewNoteContent] = useState("");
  const [newNoteType, setNewNoteType] = useState("comment");
  const [newNoteVisibility, setNewNoteVisibility] = useState("shared");
  const [refStatusFilter, setRefStatusFilter] = useState("");
  const [noteLaneFilter, setNoteLaneFilter] = useState("");
  const [noteSearchQuery, setNoteSearchQuery] = useState("");
  const [composerExpanded, setComposerExpanded] = useState(false);
  const [inlineEditNoteId, setInlineEditNoteId] = useState<string | null>(null);
  const [inlineEditTitle, setInlineEditTitle] = useState("");
  const [inlineEditContent, setInlineEditContent] = useState("");
  const [inlineEditLane, setInlineEditLane] = useState("");
  const [inlineEditRefIds, setInlineEditRefIds] = useState<string[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionActiveIndex, setMentionActiveIndex] = useState(0);
  const [mentionTarget, setMentionTarget] = useState<"composer" | "inline">("composer");
  const [mentionAnchor, setMentionAnchor] = useState<{ top: number; left: number } | null>(null);
  const [mentionCursorStart, setMentionCursorStart] = useState(0);
  const inlineEditContentRef = useRef<HTMLTextAreaElement | null>(null);
  const [selectedInboxLogIds, setSelectedInboxLogIds] = useState<Set<string>>(new Set());
  const [bibliographyTitle, setBibliographyTitle] = useState("");
  const [bibliographyCollectionTitle, setBibliographyCollectionTitle] = useState("");
  const [bibliographyCollectionDescription, setBibliographyCollectionDescription] = useState("");
  const [bibliographyCollectionVisibility, setBibliographyCollectionVisibility] = useState("private");
  const [bibliographyAuthors, setBibliographyAuthors] = useState("");
  const [bibliographyYear, setBibliographyYear] = useState("");
  const [bibliographyVenue, setBibliographyVenue] = useState("");
  const [bibliographyDoi, setBibliographyDoi] = useState("");
  const [bibliographyUrl, setBibliographyUrl] = useState("");
  const [bibliographyAbstract, setBibliographyAbstract] = useState("");
  const [bibliographyTags, setBibliographyTags] = useState<string[]>([]);
  const [bibliographyTagInput, setBibliographyTagInput] = useState("");
  const [bibliographyTagOptions, setBibliographyTagOptions] = useState<BibliographyTag[]>([]);
  const [bibliographyTagMenuOpen, setBibliographyTagMenuOpen] = useState(false);
  const [bibliographyTagActiveIndex, setBibliographyTagActiveIndex] = useState(0);
  const [bibliographyVisibility, setBibliographyVisibility] = useState("shared");
  const [bibliographyBibtexInput, setBibliographyBibtexInput] = useState("");
  const [bibliographyBibtexResult, setBibliographyBibtexResult] = useState<{ created: number; errors: string[] } | null>(null);
  const [bibliographyIdentifierInput, setBibliographyIdentifierInput] = useState("");
  const [bibliographyIdentifierResult, setBibliographyIdentifierResult] = useState<{ created: number; reused: number; errors: string[] } | null>(null);
  const [bibliographyAttachmentFile, setBibliographyAttachmentFile] = useState<File | null>(null);
  const [bibliographyDuplicateMatches, setBibliographyDuplicateMatches] = useState<BibliographyDuplicateMatch[]>([]);
  const [bibliographyPreview, setBibliographyPreview] = useState<{ title: string; filename: string; url: string } | null>(null);
  const [openingBibliographyAttachmentId, setOpeningBibliographyAttachmentId] = useState<string | null>(null);
  const [ingestingBibliographyId, setIngestingBibliographyId] = useState<string | null>(null);
  const [extractingBibliographyAbstractId, setExtractingBibliographyAbstractId] = useState<string | null>(null);
  const [extractingBibliographyConceptsId, setExtractingBibliographyConceptsId] = useState<string | null>(null);
  const [bibliographyGraphOpen, setBibliographyGraphOpen] = useState(false);
  const [bibliographyGraphReferences, setBibliographyGraphReferences] = useState<BibliographyReference[]>([]);
  const quickLogInputRef = useRef<HTMLTextAreaElement | null>(null);

  const activeCollections = collections.filter((item) => item.status === "active");
  const archivedCollections = collections.filter((item) => item.status !== "active");
  const readCount = references.filter((item) => item.reading_status === "read" || item.reading_status === "reviewed").length;
  const selectedCollection = collections.find((item) => item.id === selectedCollectionId) ?? null;
  const selectedBibliographyCollection = bibliographyCollections.find((item) => item.id === selectedBibliographyCollectionId) ?? null;
  const availableDocuments = useMemo(
    () => projectDocuments.filter((item) => item.status === "indexed" || item.status === "uploaded"),
    [projectDocuments]
  );

  const filteredBibliography = useMemo(() => {
    let items = bibliography;
    if (selectedBibliographyCollectionId && selectedBibliographyCollectionPaperIds.size > 0) {
      items = items.filter((item) => selectedBibliographyCollectionPaperIds.has(item.id));
    }
    if (bibliographyTagFilter) {
      items = items.filter((item) => item.tags.includes(bibliographyTagFilter));
    }
    if (bibliographyStatusFilter) {
      items = items.filter((item) => item.reading_status === bibliographyStatusFilter);
    }
    const sorted = [...items].sort((a, b) => {
      let cmp = 0;
      if (bibSortKey === "title") cmp = (a.title || "").localeCompare(b.title || "");
      else if (bibSortKey === "year") cmp = (a.year ?? 0) - (b.year ?? 0);
      else if (bibSortKey === "status") cmp = (a.reading_status || "").localeCompare(b.reading_status || "");
      else cmp = (a.created_at || "").localeCompare(b.created_at || "");
      return bibSortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [bibliography, selectedBibliographyCollectionId, selectedBibliographyCollectionPaperIds, bibliographyTagFilter, bibliographyStatusFilter, bibSortKey, bibSortDir]);

  const bibliographyTagsInUse = useMemo(() => {
    const tags = new Set<string>();
    for (const item of bibliography) {
      for (const tag of item.tags) tags.add(tag);
    }
    return Array.from(tags).sort();
  }, [bibliography]);

  useEffect(() => {
    return () => {
      if (bibliographyPreview?.url) {
        URL.revokeObjectURL(bibliographyPreview.url);
      }
    };
  }, [bibliographyPreview]);

  useEffect(() => {
    setPaperTitle(collectionDetail?.target_output_title || "");
    setPaperMotivation(collectionDetail?.paper_motivation || "");
    setPaperVenue(collectionDetail?.target_venue || "");
    setPaperOverleafUrl(collectionDetail?.overleaf_url || "");
    setPaperStatus(collectionDetail?.output_status || "not_started");
    setPaperRegistrationDeadline(collectionDetail?.registration_deadline || "");
    setPaperSubmissionDeadline(collectionDetail?.submission_deadline || "");
    setPaperDecisionDate(collectionDetail?.decision_date || "");
    setStudyIterations(collectionDetail?.study_iterations || []);
    setStudyResults(collectionDetail?.study_results || []);
    setResultComparison(null);
    setPaperAuthors(collectionDetail?.paper_authors || []);
    setPaperQuestions(collectionDetail?.paper_questions || []);
    setPaperClaims(collectionDetail?.paper_claims || []);
    setPaperSections(collectionDetail?.paper_sections || []);
    setPaperDirty(false);
    paperSyncedRef.current = false;
  }, [collectionDetail]);

  // Warn before leaving with unsaved paper changes
  useEffect(() => {
    if (!paperDirty) return;
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [paperDirty]);

  // Ctrl+F / Cmd+F → quick search piped into active list filter
  const quickSearch = useQuickSearch(useCallback((q: string) => {
    if (bibliographyOnly || (tab === "references" && !selectedCollectionId)) {
      setBibliographySearch(q);
    } else if (tab === "references") {
      setRefSearch(q);
    } else if (tab === "notes") {
      setNoteSearchQuery(q);
    } else {
      setBibliographySearch(q);
    }
  }, [tab, bibliographyOnly, selectedCollectionId]));

  // Auto-save paper after 3s of inactivity when dirty
  useEffect(() => {
    if (!paperDirty || !selectedProjectId || !selectedCollectionId || saving) return;
    const timer = setTimeout(() => {
      void persistPaperWorkspace(undefined, { successMessage: "Auto-saved." });
    }, 3000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperDirty, paperTitle, paperMotivation, paperVenue, paperOverleafUrl, paperStatus, paperRegistrationDeadline, paperSubmissionDeadline, paperDecisionDate, paperAuthors, paperQuestions, paperClaims, paperSections]);

  // Mark paper dirty when any paper field changes (skip the initial sync)
  const paperSyncedRef = useRef(false);
  useEffect(() => {
    if (!paperSyncedRef.current) {
      paperSyncedRef.current = true;
      return;
    }
    setPaperDirty(true);
  }, [paperTitle, paperMotivation, paperVenue, paperOverleafUrl, paperStatus, paperRegistrationDeadline, paperSubmissionDeadline, paperDecisionDate, paperAuthors, paperQuestions, paperClaims, paperSections]);

  async function loadCollections(projectId = selectedProjectId) {
    if (!projectId) return;
    const response = await api.listResearchCollections(projectId, { page_size: 100 });
    setCollections(response.items);
    if (bibliographyOnly && !bulkResearchTargetCollectionId && response.items.length > 0) {
      setBulkResearchTargetCollectionId(response.items[0].id);
    }
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
      q: (!semanticSearch ? bibliographySearch : undefined) || undefined,
      visibility: bibliographyVisibilityFilter || undefined,
      page_size: 100,
    });
    setBibliography(response.items);
    setSelectedBibIds(new Set());
  }

  async function loadBibliographyCollections() {
    const response = await api.listBibliographyCollections({ page_size: 100 });
    setBibliographyCollections(response.items);
  }

  async function loadSelectedBibliographyCollectionPaperIds(collectionId = selectedBibliographyCollectionId) {
    if (!collectionId) {
      setSelectedBibliographyCollectionPaperIds(new Set());
      return;
    }
    const ids = await api.listBibliographyCollectionPaperIds(collectionId);
    setSelectedBibliographyCollectionPaperIds(new Set(ids));
  }

  async function runSemanticSearch() {
    if (!bibliographySearch.trim()) return;
    setSearchingBibliography(true);
    setError("");
    try {
      const response = await api.searchGlobalBibliographySemantic(
        bibliographySearch.trim(),
        { visibility: bibliographyVisibilityFilter || undefined, top_k: 50 },
      );
      setBibliography(response.items);
      setSelectedBibIds(new Set());
      setStatus(`Found ${response.items.length} result${response.items.length !== 1 ? "s" : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Semantic search failed.");
    } finally {
      setSearchingBibliography(false);
    }
  }

  async function loadBibliographyTags() {
    const response = await api.listBibliographyTags({ page_size: 200 });
    setBibliographyTagOptions(response.items);
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
    if (noteLaneFilter !== "") opts.lane = noteLaneFilter === "__none__" ? "" : noteLaneFilter;
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
      Promise.all([
        loadBibliographyCollections(),
        currentProject?.project_kind === "research" && selectedProjectId ? loadCollections(selectedProjectId) : Promise.resolve(),
        loadBibliography(selectedProjectId),
      ])
        .then(() => loadBibliographyTags())
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
      loadBibliographyCollections(),
      loadCollections(selectedProjectId),
      loadMembers(selectedProjectId),
      loadSupportData(selectedProjectId),
      loadBibliography(selectedProjectId),
      loadBibliographyTags(),
      loadReferences(null, selectedProjectId),
      loadNotes(null, selectedProjectId),
    ])
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load research workspace");
      })
      .finally(() => setLoading(false));
  }, [selectedProjectId, bibliographyOnly, currentProject?.project_kind]);

  useEffect(() => {
    if (bibliographyOnly) return;
    if (!selectedProjectId) return;
    refreshWorkspace(selectedProjectId, selectedCollectionId).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to refresh research workspace");
    });
  }, [selectedProjectId, selectedCollectionId, refStatusFilter, refSearch, noteLaneFilter, bibliographyOnly]);

  useEffect(() => {
    if (!selectedProjectId && !bibliographyOnly) return;
    loadBibliography(selectedProjectId).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load bibliography");
    });
  }, [selectedProjectId, bibliographyVisibilityFilter, bibliographyOnly, semanticSearch, selectedBibliographyCollectionId]);

  useEffect(() => {
    if (semanticSearch) return; // in semantic mode, search is triggered by Enter
    if (!selectedProjectId && !bibliographyOnly) return;
    loadBibliography(selectedProjectId).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load bibliography");
    });
  }, [bibliographySearch, selectedBibliographyCollectionId]);

  useEffect(() => {
    loadSelectedBibliographyCollectionPaperIds().catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load bibliography collection papers");
    });
  }, [selectedBibliographyCollectionId]);

  const stableLoad = useCallback(() => {
    if (bibliographyOnly) {
      void loadBibliography();
      return;
    }
    void refreshWorkspace();
  }, [selectedProjectId, selectedCollectionId, refStatusFilter, refSearch, noteLaneFilter, bibliographySearch, bibliographyVisibilityFilter, bibliographyOnly, selectedBibliographyCollectionId]);
  useAutoRefresh(stableLoad);

  useEffect(() => {
    if (!openBibliographyReferenceId || bibliography.length === 0) return;
    const target = bibliography.find((item) => item.id === openBibliographyReferenceId);
    if (!target) return;
    openEditBibliographyModal(target);
    setExpandedBibId(target.id);
    onOpenBibliographyReferenceConsumed?.();
  }, [openBibliographyReferenceId, bibliography]);

  function resetCollectionForm() {
    setCollectionTitle("");
    setCollectionDescription("");
    setCollectionStatus("active");
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
    setNoteLane("");
    setNoteReferenceIds([]);
    setEditingNoteId(null);
  }

  function resetBibliographyForm() {
    setBibliographyCreateTab("manual");
    setBibliographyTitle("");
    setBibliographyAuthors("");
    setBibliographyYear("");
    setBibliographyVenue("");
    setBibliographyDoi("");
    setBibliographyUrl("");
    setBibliographyAbstract("");
    setBibliographyTags([]);
    setBibliographyTagInput("");
    setBibliographyTagMenuOpen(false);
    setBibliographyTagActiveIndex(0);
    setBibliographyVisibility("shared");
    setBibliographyBibtexInput("");
    setBibliographyBibtexResult(null);
    setBibliographyIdentifierInput("");
    setBibliographyIdentifierResult(null);
    setBibliographyAttachmentFile(null);
    setBibliographyDuplicateMatches([]);
    setBibliographyDuplicateModalOpen(false);
    setEditingBibliographyId(null);
  }

  function resetBibliographyCollectionForm() {
    setBibliographyCollectionTitle("");
    setBibliographyCollectionDescription("");
    setBibliographyCollectionVisibility("private");
    setEditingBibliographyCollectionId(null);
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

  function openCreateBibliographyCollectionModal() {
    setBibliographyCollectionModalMode("create");
    resetBibliographyCollectionForm();
    setBibliographyCollectionModalOpen(true);
  }

  function openEditBibliographyModal(item: BibliographyReference) {
    setBibliographyModalMode("edit");
    setBibliographyCreateTab("manual");
    setEditingBibliographyId(item.id);
    setBibliographyTitle(item.title);
    setBibliographyAuthors(item.authors.join(", "));
    setBibliographyYear(item.year ? String(item.year) : "");
    setBibliographyVenue(item.venue || "");
    setBibliographyDoi(item.doi || "");
    setBibliographyUrl(item.url || "");
    setBibliographyAbstract(item.abstract || "");
    setBibliographyTags(item.tags || []);
    setBibliographyTagInput("");
    setBibliographyTagMenuOpen(false);
    setBibliographyTagActiveIndex(0);
    setBibliographyVisibility(item.visibility || "shared");
    setBibliographyBibtexInput(item.bibtex_raw || "");
    setBibliographyBibtexResult(null);
    setBibliographyIdentifierInput("");
    setBibliographyIdentifierResult(null);
    setBibliographyAttachmentFile(null);
    setBibliographyModalOpen(true);
  }

  async function handleCopyBibliographyPermalink(item: BibliographyReference) {
    if (typeof window === "undefined" || !selectedProjectId) return;
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("view", "bibliography");
    url.searchParams.set("project", selectedProjectId);
    url.searchParams.set("paper", item.id);
    try {
      const text = url.toString();
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "true");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        textarea.style.pointerEvents = "none";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(textarea);
        if (!ok) throw new Error("copy-failed");
      }
      setStatus("Link copied.");
    } catch {
      setError("Failed to copy link.");
    }
  }

  function openEditBibliographyCollectionModal(item: BibliographyCollection) {
    setBibliographyCollectionModalMode("edit");
    setEditingBibliographyCollectionId(item.id);
    setBibliographyCollectionTitle(item.title);
    setBibliographyCollectionDescription(item.description || "");
    setBibliographyCollectionVisibility(item.visibility || "private");
    setBibliographyCollectionModalOpen(true);
  }

  function openEditCollectionModal() {
    if (!collectionDetail) return;
    setCollectionModalMode("edit");
    setEditingCollectionId(collectionDetail.id);
    setCollectionTitle(collectionDetail.title);
    setCollectionDescription(collectionDetail.description || collectionDetail.hypothesis || "");
    setCollectionStatus(collectionDetail.status);
    setCollectionModalOpen(true);
  }

  function openCreateReferenceModal(tabName: ReferenceModalTab = "manual") {
    if (!selectedCollectionId) {
      setError("Select a study first.");
      return;
    }
    setReferenceModalMode("create");
    resetReferenceForm(selectedCollectionId);
    setReferenceModalTab(tabName);
    setReferenceModalOpen(true);
  }

  function openBibliographyPicker() {
    if (!selectedCollectionId) {
      setError("Select a study first.");
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
      setError("Select a study first.");
      return;
    }
    setTab("notes");
    setTimeout(() => {
      quickLogInputRef.current?.focus();
    }, 0);
  }

  function openEditNoteModal(note: ResearchNote) {
    setNoteModalMode("edit");
    setEditingNoteId(note.id);
    setNoteTitle(note.title);
    setNoteContent(note.content);
    setNoteType(note.note_type);
    setNoteCollectionId(note.collection_id || selectedCollectionId || "");
    setNoteLane(note.lane || "");
    setNoteReferenceIds(note.linked_reference_ids);
    setNoteModalOpen(true);
  }

  function startInlineEdit(note: ResearchNote) {
    setInlineEditNoteId(note.id);
    setInlineEditTitle(note.title);
    setInlineEditContent(note.content);
    setInlineEditLane(note.lane || "");
    setInlineEditRefIds([...note.linked_reference_ids]);
  }

  function cancelInlineEdit() {
    setInlineEditNoteId(null);
    setInlineEditTitle("");
    setInlineEditContent("");
    setInlineEditLane("");
    setInlineEditRefIds([]);
    closeMention();
  }

  async function handleInlineEditSave(noteId: string) {
    if (!selectedProjectId || !inlineEditTitle.trim() || !inlineEditContent.trim()) return;
    setSaving(true);
    setError("");
    try {
      const existingNote = notes.find((item) => item.id === noteId);
      await api.updateResearchNote(selectedProjectId, noteId, {
        title: inlineEditTitle.trim(),
        content: inlineEditContent.trim(),
        lane: inlineEditLane || null,
        note_type: existingNote?.note_type || "observation",
      });
      await api.setNoteReferences(selectedProjectId, noteId, inlineEditRefIds);
      setStatus("Log updated.");
      cancelInlineEdit();
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId), loadSupportData()]);
      if (selectedCollectionId) await loadCollectionDetail(selectedCollectionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save log");
    } finally {
      setSaving(false);
    }
  }

  function formatRefLabel(ref: ResearchReference | BibliographyReference): string {
    const firstAuthor = ref.authors.length > 0 ? ref.authors[0].split(",")[0].split(" ").pop() : "Unknown";
    return ref.year ? `${firstAuthor} ${ref.year}` : `${firstAuthor}`;
  }

  const mentionResults = useMemo(() => {
    if (!mentionOpen || !mentionQuery) return references.slice(0, 6);
    const q = mentionQuery.toLowerCase();
    return references
      .filter((ref) =>
        ref.title.toLowerCase().includes(q) ||
        ref.authors.some((a) => a.toLowerCase().includes(q)) ||
        (ref.year && String(ref.year).includes(q))
      )
      .slice(0, 6);
  }, [mentionOpen, mentionQuery, references]);

  function getTextareaCaretCoords(textarea: HTMLTextAreaElement): { top: number; left: number } {
    const div = document.createElement("div");
    const style = window.getComputedStyle(textarea);
    for (const prop of ["fontFamily", "fontSize", "fontWeight", "lineHeight", "padding", "border", "letterSpacing", "wordSpacing", "whiteSpace", "overflowWrap"] as const) {
      div.style[prop] = style[prop];
    }
    div.style.position = "absolute";
    div.style.visibility = "hidden";
    div.style.whiteSpace = "pre-wrap";
    div.style.wordWrap = "break-word";
    div.style.width = `${textarea.clientWidth}px`;
    const text = textarea.value.substring(0, textarea.selectionStart);
    div.textContent = text;
    const span = document.createElement("span");
    span.textContent = "|";
    div.appendChild(span);
    document.body.appendChild(div);
    const rect = textarea.getBoundingClientRect();
    const spanRect = span.getBoundingClientRect();
    const divRect = div.getBoundingClientRect();
    const top = rect.top + (spanRect.top - divRect.top) - textarea.scrollTop + spanRect.height;
    const left = rect.left + (spanRect.left - divRect.left);
    document.body.removeChild(div);
    return { top, left };
  }

  function openMention(textarea: HTMLTextAreaElement, target: "composer" | "inline") {
    const coords = getTextareaCaretCoords(textarea);
    setMentionTarget(target);
    setMentionAnchor(coords);
    setMentionCursorStart(textarea.selectionStart);
    setMentionQuery("");
    setMentionActiveIndex(0);
    setMentionOpen(true);
  }

  function closeMention() {
    setMentionOpen(false);
    setMentionQuery("");
    setMentionActiveIndex(0);
    setMentionAnchor(null);
  }

  function selectMention(ref: ResearchReference) {
    const label = `@[${formatRefLabel(ref)}]`;
    if (mentionTarget === "composer") {
      const before = quickLogContent.substring(0, mentionCursorStart - 1);
      const after = quickLogContent.substring(mentionCursorStart + mentionQuery.length);
      setQuickLogContent(before + label + " " + after);
      setQuickLogRefIds((current) => current.includes(ref.id) ? current : [...current, ref.id]);
    } else {
      const before = inlineEditContent.substring(0, mentionCursorStart - 1);
      const after = inlineEditContent.substring(mentionCursorStart + mentionQuery.length);
      setInlineEditContent(before + label + " " + after);
      setInlineEditRefIds((current) => current.includes(ref.id) ? current : [...current, ref.id]);
    }
    closeMention();
  }

  function handleMentionKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!mentionOpen) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setMentionActiveIndex((i) => (i + 1) % Math.max(mentionResults.length, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setMentionActiveIndex((i) => (i - 1 + mentionResults.length) % Math.max(mentionResults.length, 1));
    } else if (event.key === "Enter" && !event.shiftKey && !(event.metaKey || event.ctrlKey)) {
      if (mentionResults.length > 0) {
        event.preventDefault();
        selectMention(mentionResults[mentionActiveIndex]);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeMention();
    }
  }

  function handleContentChange(value: string, cursorPos: number, textarea: HTMLTextAreaElement, target: "composer" | "inline") {
    if (target === "composer") {
      setQuickLogContent(value);
    } else {
      setInlineEditContent(value);
    }

    if (mentionOpen) {
      const textSinceAt = value.substring(mentionCursorStart, cursorPos);
      if (textSinceAt.includes(" ") || textSinceAt.includes("\n") || cursorPos < mentionCursorStart) {
        closeMention();
      } else {
        setMentionQuery(textSinceAt);
        setMentionActiveIndex(0);
      }
      return;
    }

    if (cursorPos > 0 && value[cursorPos - 1] === "@") {
      const charBefore = cursorPos > 1 ? value[cursorPos - 2] : " ";
      if (charBefore === " " || charBefore === "\n" || cursorPos === 1) {
        openMention(textarea, target);
      }
    }
  }

  function openWbsModal() {
    if (!collectionDetail) return;
    setWbsWpIds(collectionDetail.wp_ids);
    setWbsTaskIds(collectionDetail.task_ids);
    setWbsDeliverableIds(collectionDetail.deliverable_ids);
    setMeetingIds(collectionDetail.meetings.map((item) => item.id));
    setWbsModalOpen(true);
  }

  function newPaperQuestion(): ResearchPaperQuestion {
    return { id: crypto.randomUUID(), text: "", note_ids: [] };
  }

  function newPaperAuthor(member: ResearchCollectionMember): ResearchPaperAuthor {
    return {
      id: crypto.randomUUID(),
      member_id: member.member_id,
      display_name: member.member_name || "Author",
      is_corresponding: false,
    };
  }

  function newStudyIteration(): ResearchStudyIteration {
    const today = new Date().toISOString().slice(0, 10);
    return {
      id: crypto.randomUUID(),
      title: "",
      start_date: today,
      end_date: today,
      note_ids: [],
      reference_ids: [],
      result_ids: [],
      summary: null,
      what_changed: [],
      improvements: [],
      regressions: [],
      unclear_points: [],
      next_actions: [],
      user_comments: null,
      reviewed_at: null,
    };
  }

  function newStudyResult(): ResearchStudyResult {
    const now = new Date().toISOString();
    return {
      id: crypto.randomUUID(),
      iteration_id: null,
      title: "",
      note_ids: [],
      reference_ids: [],
      summary: null,
      what_changed: [],
      improvements: [],
      regressions: [],
      unclear_points: [],
      next_actions: [],
      user_comments: null,
      created_at: now,
      updated_at: now,
    };
  }

  function newPaperClaim(): ResearchPaperClaim {
    return {
      id: crypto.randomUUID(),
      text: "",
      question_ids: [],
      reference_ids: [],
      note_ids: [],
      result_ids: [],
      status: "draft",
      audit_status: null,
      audit_summary: null,
      supporting_reference_ids: [],
      supporting_note_ids: [],
      missing_evidence: [],
      audit_confidence: null,
      audited_at: null,
    };
  }

  function newPaperSection(): ResearchPaperSection {
    return { id: crypto.randomUUID(), title: "", question_ids: [], claim_ids: [], reference_ids: [], note_ids: [], result_ids: [], status: "not_started" };
  }

  function notePromotionText(note: ResearchNote): string {
    return note.content.trim() || note.title.trim();
  }

  function noteIterationState(noteId: string) {
    const iteration = studyIterations.find((item) => item.note_ids.includes(noteId));
    return {
      assigned: Boolean(iteration),
      iterationId: iteration?.id || null,
      iterationTitle: iteration?.title || null,
    };
  }

  function iterationResults(iterationId: string) {
    return studyResults.filter((item) => item.iteration_id === iterationId);
  }

  function createResultFromIteration(iteration: ResearchStudyIteration): ResearchStudyResult {
    const now = new Date().toISOString();
    const existing = iterationResults(iteration.id)[0];
    const base = existing || newStudyResult();
    return {
      ...base,
      iteration_id: iteration.id,
      title: iteration.title || `Result ${studyResults.length + 1}`,
      note_ids: [...iteration.note_ids],
      reference_ids: [...iteration.reference_ids],
      summary: iteration.summary,
      what_changed: [...iteration.what_changed],
      improvements: [...iteration.improvements],
      regressions: [...iteration.regressions],
      unclear_points: [...iteration.unclear_points],
      next_actions: [...iteration.next_actions],
      user_comments: iteration.user_comments,
      created_at: existing?.created_at || now,
      updated_at: now,
    };
  }

  function resultTimestamp(result: ResearchStudyResult): number {
    return Date.parse(result.updated_at || result.created_at || "") || 0;
  }

  function sortedStudyResults(items: ResearchStudyResult[] = studyResults): ResearchStudyResult[] {
    return [...items].sort((a, b) => resultTimestamp(b) - resultTimestamp(a));
  }

  function previousStudyResult(resultId: string): ResearchStudyResult | null {
    const ordered = sortedStudyResults().reverse();
    const index = ordered.findIndex((item) => item.id === resultId);
    if (index <= 0) return null;
    return ordered[index - 1] || null;
  }

  function resultDeltaLabel(current: ResearchStudyResult, previous: ResearchStudyResult | null) {
    if (!previous) return null;
    const improvementDelta = current.improvements.length - previous.improvements.length;
    const regressionDelta = current.regressions.length - previous.regressions.length;
    const unclearDelta = current.unclear_points.length - previous.unclear_points.length;
    const parts: string[] = [];
    if (improvementDelta !== 0) parts.push(`${improvementDelta > 0 ? "+" : ""}${improvementDelta} improvements`);
    if (regressionDelta !== 0) parts.push(`${regressionDelta > 0 ? "+" : ""}${regressionDelta} regressions`);
    if (unclearDelta !== 0) parts.push(`${unclearDelta > 0 ? "+" : ""}${unclearDelta} unclear`);
    return parts.length > 0 ? parts.join(" · ") : "No major shift";
  }

  function toggleId(values: string[], value: string): string[] {
    return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
  }

  function buildPaperWorkspacePayload(
    overrides?: Partial<{
      paper_motivation: string | null;
      target_output_title: string | null;
      target_venue: string | null;
      overleaf_url: string | null;
      output_status: string;
      registration_deadline: string | null;
      submission_deadline: string | null;
      decision_date: string | null;
      study_iterations: ResearchStudyIteration[];
      study_results: ResearchStudyResult[];
      paper_authors: ResearchPaperAuthor[];
      paper_questions: ResearchPaperQuestion[];
      paper_claims: ResearchPaperClaim[];
      paper_sections: ResearchPaperSection[];
    }>
  ) {
    const payload = {
      paper_motivation: paperMotivation.trim() || null,
      target_output_title: paperTitle.trim() || null,
      target_venue: paperVenue.trim() || null,
      overleaf_url: paperOverleafUrl.trim() || null,
      output_status: paperStatus,
      registration_deadline: paperRegistrationDeadline || null,
      submission_deadline: paperSubmissionDeadline || null,
      decision_date: paperDecisionDate || null,
      study_iterations: studyIterations,
      study_results: studyResults,
      paper_authors: paperAuthors,
      paper_questions: paperQuestions,
      paper_claims: paperClaims,
      paper_sections: paperSections,
      ...overrides,
    };

    return {
      paper_motivation: payload.paper_motivation,
      target_output_title: payload.target_output_title,
      target_venue: payload.target_venue,
      overleaf_url: payload.overleaf_url,
      output_status: payload.output_status,
      registration_deadline: payload.registration_deadline,
      submission_deadline: payload.submission_deadline,
      decision_date: payload.decision_date,
      study_iterations: payload.study_iterations.map((item) => ({
        id: item.id,
        title: item.title,
        start_date: item.start_date,
        end_date: item.end_date,
        note_ids: item.note_ids,
        reference_ids: item.reference_ids,
        result_ids: item.result_ids,
        summary: item.summary,
        what_changed: item.what_changed,
        improvements: item.improvements,
        regressions: item.regressions,
        unclear_points: item.unclear_points,
        next_actions: item.next_actions,
        user_comments: item.user_comments,
        reviewed_at: item.reviewed_at,
      })),
      study_results: payload.study_results.map((item) => ({
        id: item.id,
        iteration_id: item.iteration_id,
        title: item.title,
        note_ids: item.note_ids,
        reference_ids: item.reference_ids,
        summary: item.summary,
        what_changed: item.what_changed,
        improvements: item.improvements,
        regressions: item.regressions,
        unclear_points: item.unclear_points,
        next_actions: item.next_actions,
        user_comments: item.user_comments,
        created_at: item.created_at,
        updated_at: item.updated_at,
      })),
      paper_authors: payload.paper_authors.map((item) => ({
        id: item.id,
        member_id: item.member_id,
        display_name: item.display_name,
        is_corresponding: item.is_corresponding,
      })),
      paper_questions: payload.paper_questions.map((item) => ({ id: item.id, text: item.text, note_ids: item.note_ids })),
      paper_claims: payload.paper_claims.map((item) => ({
        id: item.id,
        text: item.text,
        question_ids: item.question_ids,
        reference_ids: item.reference_ids,
        note_ids: item.note_ids,
        result_ids: item.result_ids,
        status: item.status,
        audit_status: item.audit_status,
        audit_summary: item.audit_summary,
        supporting_reference_ids: item.supporting_reference_ids,
        supporting_note_ids: item.supporting_note_ids,
        missing_evidence: item.missing_evidence,
        audit_confidence: item.audit_confidence,
        audited_at: item.audited_at,
      })),
      paper_sections: payload.paper_sections.map((item) => ({
        id: item.id,
        title: item.title,
        question_ids: item.question_ids,
        claim_ids: item.claim_ids,
        reference_ids: item.reference_ids,
        note_ids: item.note_ids,
        result_ids: item.result_ids,
        status: item.status,
      })),
    };
  }

  async function persistPaperWorkspace(
    overrides?: Partial<{
      paper_motivation: string | null;
      target_output_title: string | null;
      target_venue: string | null;
      overleaf_url: string | null;
      output_status: string;
      registration_deadline: string | null;
      submission_deadline: string | null;
      decision_date: string | null;
      study_iterations: ResearchStudyIteration[];
      study_results: ResearchStudyResult[];
      paper_authors: ResearchPaperAuthor[];
      paper_questions: ResearchPaperQuestion[];
      paper_claims: ResearchPaperClaim[];
      paper_sections: ResearchPaperSection[];
    }>,
    options?: {
      requireSubmissionDeadline?: boolean;
      successMessage?: string;
    }
  ) {
    if (!selectedProjectId || !selectedCollectionId) return;
    const requireSubmissionDeadline = options?.requireSubmissionDeadline ?? false;
    const payload = buildPaperWorkspacePayload(overrides);
    if (requireSubmissionDeadline && !payload.submission_deadline) {
      setError("Submission deadline is required.");
      return;
    }
    setSaving(true);
    setError("");
    setStatus("");
    try {
      await api.updateResearchCollection(selectedProjectId, selectedCollectionId, payload);
      await Promise.all([loadCollections(), loadCollectionDetail(selectedCollectionId)]);
      setStatus(options?.successMessage || "Paper updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update paper");
    } finally {
      setSaving(false);
    }
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
        });
        await loadCollections();
        setSelectedCollectionId(created.id);
        setStatus("Study created.");
      } else if (editingCollectionId) {
        await api.updateResearchCollection(selectedProjectId, editingCollectionId, {
          title: collectionTitle.trim(),
          description: collectionDescription.trim() || null,
          status: collectionStatus,
        });
        await loadCollections();
        await loadCollectionDetail(editingCollectionId);
        setStatus("Study updated.");
      }
      setCollectionModalOpen(false);
      resetCollectionForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save study");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteCollection(collectionId: string) {
    if (!selectedProjectId) return;
    try {
      await api.deleteResearchCollection(selectedProjectId, collectionId);
      await loadCollections();
      if (selectedCollectionId === collectionId) {
        setSelectedCollectionId(null);
        setCollectionDetail(null);
      } else if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setStatus("Study deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete study");
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
      setStatus("Study archived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive study");
    }
  }

  async function handleSavePaperWorkspace() {
    await persistPaperWorkspace(undefined, { requireSubmissionDeadline: true, successMessage: "Paper updated." });
  }

  async function handleAuditPaperClaims() {
    if (!selectedProjectId || !selectedCollectionId) return;
    setAuditingPaperClaims(true);
    setError("");
    setStatus("");
    try {
      const detail = await api.auditResearchPaperClaims(selectedProjectId, selectedCollectionId);
      setCollectionDetail(detail);
      setStatus("Claims audited.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to audit claims");
    } finally {
      setAuditingPaperClaims(false);
    }
  }

  async function handleBuildPaperOutline() {
    if (!selectedProjectId || !selectedCollectionId) return;
    setBuildingPaperOutline(true);
    setError("");
    setStatus("");
    try {
      const detail = await api.buildResearchPaperOutline(selectedProjectId, selectedCollectionId);
      setCollectionDetail(detail);
      setPaperExpanded(true);
      setStatus("Outline built.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to build outline");
    } finally {
      setBuildingPaperOutline(false);
    }
  }

  async function handleDraftPaperFromGap() {
    if (!selectedProjectId || !selectedCollectionId) return;
    setDraftingGapPaper(true);
    setError("");
    setStatus("");
    try {
      const detail = await api.draftResearchPaperFromGap(selectedProjectId, selectedCollectionId);
      setCollectionDetail(detail);
      setPaperExpanded(true);
      setStatus("Motivation and questions drafted from gap logs.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to draft from gap logs");
    } finally {
      setDraftingGapPaper(false);
    }
  }

  async function handleReviewIteration(iterationId: string) {
    if (!selectedProjectId || !selectedCollectionId) return;
    setReviewingIterationId(iterationId);
    setError("");
    setStatus("");
    try {
      const detail = await api.reviewResearchIteration(selectedProjectId, selectedCollectionId, iterationId);
      setCollectionDetail(detail);
      setStatus("Iteration reviewed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to review iteration");
    } finally {
      setReviewingIterationId(null);
    }
  }

  async function handleCreateResultFromIteration(iterationId: string) {
    if (!selectedProjectId || !selectedCollectionId) return;
    const iteration = studyIterations.find((item) => item.id === iterationId);
    if (!iteration || !iteration.summary) {
      setError("Review the iteration first.");
      return;
    }
    const result = createResultFromIteration(iteration);
    const nextResults = [
      result,
      ...studyResults.filter((item) => item.id !== result.id),
    ];
    const nextIterations = studyIterations.map((item) =>
      item.id === iterationId
        ? {
            ...item,
            result_ids: Array.from(new Set([...(item.result_ids || []), result.id])),
          }
        : item
    );
    setStudyResults(nextResults);
    setStudyIterations(nextIterations);
    await persistPaperWorkspace(
      {
        study_results: nextResults,
        study_iterations: nextIterations,
      },
      { successMessage: "Result created." }
    );
  }

  async function handleCompareResults() {
    if (!selectedProjectId || !selectedCollectionId) return;
    setComparingResults(true);
    setError("");
    setStatus("");
    try {
      const report = await api.compareResearchResults(selectedProjectId, selectedCollectionId);
      setResultComparison(report);
      setStatus("Results compared.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to compare results");
    } finally {
      setComparingResults(false);
    }
  }

  async function handleCreateIterationFromLogs(noteIds: string[]) {
    if (!selectedCollectionId) return;
    const logs = notes
      .filter((item) => item.collection_id === selectedCollectionId && noteIds.includes(item.id))
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
    if (logs.length === 0) return;
    const referenceIds = Array.from(new Set(logs.flatMap((item) => item.linked_reference_ids)));
    const iteration: ResearchStudyIteration = {
      ...newStudyIteration(),
      title: `Iteration ${studyIterations.length + 1}`,
      start_date: logs[0].created_at.slice(0, 10),
      end_date: logs[logs.length - 1].created_at.slice(0, 10),
      note_ids: logs.map((item) => item.id),
      reference_ids: referenceIds,
      result_ids: [],
    };
    const nextIterations = [iteration, ...studyIterations];
    setTab("iterations");
    setExpandedIterationId(iteration.id);
    setSelectedInboxLogIds(new Set());
    await persistPaperWorkspace(
      { study_iterations: nextIterations },
      { successMessage: "Iteration created." }
    );
  }

  async function handlePromoteNoteToQuestion(note: ResearchNote) {
    if (!selectedCollectionId || note.collection_id !== selectedCollectionId) return;
    const text = notePromotionText(note);
    if (!text) return;
    setTab("paper");
    const nextQuestions = [...paperQuestions, { id: crypto.randomUUID(), text, note_ids: [note.id] }];
    await persistPaperWorkspace(
      {
        paper_questions: nextQuestions,
      },
      { successMessage: "Question added from note." }
    );
  }

  async function handlePromoteNoteToClaim(note: ResearchNote) {
    if (!selectedCollectionId || note.collection_id !== selectedCollectionId) return;
    const text = notePromotionText(note);
    if (!text) return;
    setTab("paper");
    const nextClaims = [
      ...paperClaims,
      {
        ...newPaperClaim(),
        text,
        reference_ids: [...note.linked_reference_ids],
        note_ids: [note.id],
      },
    ];
    await persistPaperWorkspace(
      {
        paper_claims: nextClaims,
      },
      { successMessage: "Claim added from note." }
    );
  }

  async function handlePromoteNoteToSection(note: ResearchNote) {
    if (!selectedCollectionId || note.collection_id !== selectedCollectionId) return;
    const title = note.title.trim() || notePromotionText(note).slice(0, 120);
    if (!title) return;
    setTab("paper");
    const nextSections = [
      ...paperSections,
      {
        ...newPaperSection(),
        title,
        reference_ids: [...note.linked_reference_ids],
        note_ids: [note.id],
      },
    ];
    await persistPaperWorkspace(
      {
        paper_sections: nextSections,
      },
      { successMessage: "Section added from note." }
    );
  }

  async function handlePromoteReferenceToQuestion(reference: ResearchReference) {
    if (!selectedCollectionId || reference.collection_id !== selectedCollectionId) return;
    const text = reference.title.trim();
    if (!text) return;
    setTab("paper");
    const nextQuestions = [...paperQuestions, { id: crypto.randomUUID(), text, note_ids: [] }];
    await persistPaperWorkspace({ paper_questions: nextQuestions }, { successMessage: "Question drafted from reference." });
  }

  async function handlePromoteReferenceToClaim(reference: ResearchReference) {
    if (!selectedCollectionId || reference.collection_id !== selectedCollectionId) return;
    const text = reference.title.trim();
    if (!text) return;
    setTab("paper");
    const nextClaims = [
      ...paperClaims,
      {
        ...newPaperClaim(),
        text,
        reference_ids: [reference.id],
      },
    ];
    await persistPaperWorkspace({ paper_claims: nextClaims }, { successMessage: "Claim drafted from reference." });
  }

  async function handleGeneratePaperFromStudy() {
    if (!selectedCollectionId) return;
    const collectionNotes = notes.filter((item) => item.collection_id === selectedCollectionId);
    const nextQuestions = [...paperQuestions];
    const nextClaims = [...paperClaims];
    const nextSections = [...paperSections];
    const existingQuestionTexts = new Set(nextQuestions.map((item) => item.text.trim().toLowerCase()).filter(Boolean));
    const existingClaimTexts = new Set(nextClaims.map((item) => item.text.trim().toLowerCase()).filter(Boolean));
    const existingSectionTitles = new Set(nextSections.map((item) => item.title.trim().toLowerCase()).filter(Boolean));

    for (const note of collectionNotes) {
      const text = notePromotionText(note);
      const title = note.title.trim() || text.slice(0, 120);
      const normalizedText = text.toLowerCase();
      const normalizedTitle = title.toLowerCase();
      if (["hypothesis", "discussion"].includes(note.note_type) && text && !existingQuestionTexts.has(normalizedText)) {
        nextQuestions.push({ id: crypto.randomUUID(), text, note_ids: [note.id] });
        existingQuestionTexts.add(normalizedText);
        continue;
      }
      if (["finding", "conclusion", "decision", "observation"].includes(note.note_type) && text && !existingClaimTexts.has(normalizedText)) {
        nextClaims.push({
          ...newPaperClaim(),
          text,
          reference_ids: [...note.linked_reference_ids],
          note_ids: [note.id],
        });
        existingClaimTexts.add(normalizedText);
        continue;
      }
      if (["method", "literature_review", "action_item"].includes(note.note_type) && title && !existingSectionTitles.has(normalizedTitle)) {
        nextSections.push({
          ...newPaperSection(),
          title,
          reference_ids: [...note.linked_reference_ids],
          note_ids: [note.id],
        });
        existingSectionTitles.add(normalizedTitle);
      }
    }

    if (
      nextQuestions.length === paperQuestions.length &&
      nextClaims.length === paperClaims.length &&
      nextSections.length === paperSections.length
    ) {
      setStatus("No new paper items generated.");
      return;
    }

    setPaperExpanded(true);
    await persistPaperWorkspace(
      {
        paper_questions: nextQuestions,
        paper_claims: nextClaims,
        paper_sections: nextSections,
      },
      { successMessage: "Paper workspace generated from study." }
    );
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
    if (!selectedProjectId) return;
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
    const reference = references.find((item) => item.id === referenceId) ?? allReferences.find((item) => item.id === referenceId);
    if (reference?.bibliography_reference_id) {
      await handleSummarizeBibliography(reference.bibliography_reference_id);
      return;
    }
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

  async function handleSummarizeBibliography(bibliographyReferenceId: string) {
    setSummarizingId(bibliographyReferenceId);
    setError("");
    setStatus("");
    try {
      const result = await api.summarizeBibliographyReference(bibliographyReferenceId);
      setBibliography((items) =>
        items.map((item) => (item.id === bibliographyReferenceId ? { ...item, ai_summary: result.ai_summary, ai_summary_at: result.ai_summary_at } : item))
      );
      setReferences((items) =>
        items.map((item) =>
          item.bibliography_reference_id === bibliographyReferenceId ? { ...item, ai_summary: result.ai_summary, ai_summary_at: result.ai_summary_at } : item
        )
      );
      setAllReferences((items) =>
        items.map((item) =>
          item.bibliography_reference_id === bibliographyReferenceId ? { ...item, ai_summary: result.ai_summary, ai_summary_at: result.ai_summary_at } : item
        )
      );
      setStatus("Paper summarized.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Summarization failed");
    } finally {
      setSummarizingId(null);
    }
  }

  async function handleExtractBibliographyAbstract(bibliographyReferenceId: string) {
    setExtractingBibliographyAbstractId(bibliographyReferenceId);
    setError("");
    setStatus("");
    try {
      const result = await api.extractGlobalBibliographyAbstract(bibliographyReferenceId);
      setBibliography((items) => items.map((item) => (item.id === bibliographyReferenceId ? result : item)));
      setReferences((items) =>
        items.map((item) =>
          item.bibliography_reference_id === bibliographyReferenceId
            ? { ...item, abstract: result.abstract || item.abstract }
            : item
        )
      );
      setAllReferences((items) =>
        items.map((item) =>
          item.bibliography_reference_id === bibliographyReferenceId
            ? { ...item, abstract: result.abstract || item.abstract }
            : item
        )
      );
      setBibliographyAbstract(result.abstract || "");
      setStatus(result.abstract ? "Abstract extracted." : result.warning || "Abstract not found.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to extract abstract");
    } finally {
      setExtractingBibliographyAbstractId(null);
    }
  }

  async function handleExtractBibliographyConcepts(bibliographyReferenceId: string) {
    setExtractingBibliographyConceptsId(bibliographyReferenceId);
    setError("");
    setStatus("");
    try {
      const result = await api.extractGlobalBibliographyConcepts(bibliographyReferenceId);
      setBibliography((items) => items.map((item) => (item.id === bibliographyReferenceId ? result : item)));
      setStatus(result.concepts.length > 0 ? "Concepts extracted." : "No concepts extracted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to extract concepts");
    } finally {
      setExtractingBibliographyConceptsId(null);
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
      tags: bibliographyTags,
      visibility: bibliographyVisibility,
      ...overrides,
    };
  }

  const bibliographyTagSuggestions = useMemo(() => {
    const query = normalizeTagLabel(bibliographyTagInput).toLowerCase();
    return bibliographyTagOptions
      .filter((item) => !bibliographyTags.some((tag) => tag.toLowerCase() === item.label.toLowerCase()))
      .filter((item) => (query ? item.label.toLowerCase().includes(query) : true))
      .sort((a, b) => {
        if (!query) return a.label.localeCompare(b.label);
        const aStarts = a.label.toLowerCase().startsWith(query);
        const bStarts = b.label.toLowerCase().startsWith(query);
        if (aStarts !== bStarts) return aStarts ? -1 : 1;
        return a.label.localeCompare(b.label);
      })
      .slice(0, 8);
  }, [bibliographyTagInput, bibliographyTagOptions, bibliographyTags]);

  function addBibliographyTag(rawValue: string) {
    const label = normalizeTagLabel(rawValue);
    if (!label) return;
    setBibliographyTags((current) => {
      if (current.some((item) => item.toLowerCase() === label.toLowerCase())) return current;
      const existing = bibliographyTagOptions.find((item) => item.label.toLowerCase() === label.toLowerCase());
      return [...current, existing?.label ?? label];
    });
    setBibliographyTagInput("");
    setBibliographyTagMenuOpen(false);
    setBibliographyTagActiveIndex(0);
  }

  function removeBibliographyTag(label: string) {
    setBibliographyTags((current) => current.filter((item) => item.toLowerCase() !== label.toLowerCase()));
  }

  async function persistBibliography(options?: { allowDuplicate?: boolean; reuseExistingId?: string | null }) {
    if (!selectedProjectId || !bibliographyTitle.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const payload = buildBibliographyPayload({
        bibtex_raw: bibliographyBibtexInput.trim() || undefined,
        allow_duplicate: options?.allowDuplicate || undefined,
        reuse_existing_id: options?.reuseExistingId || undefined,
      });
      const item =
        bibliographyModalMode === "create"
          ? await api.createGlobalBibliography(payload)
          : await api.updateGlobalBibliography(editingBibliographyId!, payload);
      let finalItem = item;
      if (bibliographyAttachmentFile) {
        if (!selectedProjectId) throw new Error("Select a project before attaching a PDF.");
        if (!item.attachment_url || options?.allowDuplicate) {
          finalItem = await api.uploadGlobalBibliographyAttachment(item.id, selectedProjectId, bibliographyAttachmentFile);
        }
      }
      await Promise.all([loadBibliography(), loadBibliographyTags()]);
      setBibliographyModalOpen(false);
      setBibliographyDuplicateModalOpen(false);
      setBibliographyDuplicateMatches([]);
      resetBibliographyForm();
      setStatus(
        finalItem.warning ||
        (bibliographyModalMode === "create"
          ? options?.reuseExistingId
            ? "Existing paper reused."
            : "Paper added."
          : "Paper updated.")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save paper");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveBibliography() {
    if (bibliographyModalMode === "create" && bibliographyTitle.trim()) {
      try {
        setSaving(true);
        setError("");
        const result = await api.checkGlobalBibliographyDuplicates({
          title: bibliographyTitle.trim(),
          doi: bibliographyDoi.trim() || null,
        });
        if (result.matches.length > 0) {
          setBibliographyDuplicateMatches(result.matches);
          setBibliographyDuplicateModalOpen(true);
          return;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to check duplicates");
        return;
      } finally {
        setSaving(false);
      }
    }
    await persistBibliography();
  }

  async function handleImportBibliographyIdentifiers() {
    if (!bibliographyIdentifierInput.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const result = await api.importGlobalBibliographyIdentifiers({
        identifiers: bibliographyIdentifierInput.trim(),
        visibility: bibliographyVisibility,
        source_project_id: selectedProjectId || null,
      });
      setBibliographyIdentifierResult({
        created: result.created.length,
        reused: result.reused.length,
        errors: result.errors,
      });
      await Promise.all([loadBibliography(), loadBibliographyTags()]);
      const abstractWarning = [...result.created, ...result.reused].find((item) => item.warning)?.warning;
      setStatus(abstractWarning || "Import completed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Identifier import failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveBibliographyCollection() {
    if (!bibliographyCollectionTitle.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      if (bibliographyCollectionModalMode === "create") {
        const created = await api.createBibliographyCollection({
          title: bibliographyCollectionTitle.trim(),
          description: bibliographyCollectionDescription.trim() || null,
          visibility: bibliographyCollectionVisibility,
        });
        setSelectedBibliographyCollectionId(created.id);
      } else if (editingBibliographyCollectionId) {
        await api.updateBibliographyCollection(editingBibliographyCollectionId, {
          title: bibliographyCollectionTitle.trim(),
          description: bibliographyCollectionDescription.trim() || null,
          visibility: bibliographyCollectionVisibility,
        });
      }
      await loadBibliographyCollections();
      await loadBibliography();
      setBibliographyCollectionModalOpen(false);
      resetBibliographyCollectionForm();
      setStatus(bibliographyCollectionModalMode === "create" ? "Collection added." : "Collection updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save bibliography collection");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteBibliographyCollection(collectionId: string) {
    setSaving(true);
    setError("");
    setStatus("");
    try {
      await api.deleteBibliographyCollection(collectionId);
      if (selectedBibliographyCollectionId === collectionId) {
        setSelectedBibliographyCollectionId(null);
      }
      await Promise.all([loadBibliographyCollections(), loadBibliography()]);
      setStatus("Collection deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete bibliography collection");
    } finally {
      setSaving(false);
    }
  }

  async function handleTogglePaperInCollection(item: BibliographyReference) {
    if (!selectedBibliographyCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const inSelected = selectedBibliographyCollectionPaperIds.has(item.id);
      if (inSelected) {
        await api.removePaperFromBibliographyCollection(selectedBibliographyCollectionId, item.id);
      } else {
        await api.addPaperToBibliographyCollection(selectedBibliographyCollectionId, item.id);
      }
      await Promise.all([loadBibliographyCollections(), loadSelectedBibliographyCollectionPaperIds()]);
      setStatus(inSelected ? "Paper removed from collection." : "Paper added to collection.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update collection membership");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddSelectedPapersToCollection() {
    if (!selectedBibliographyCollectionId || selectedBibIds.size === 0) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      for (const paperId of selectedBibIds) {
        if (selectedBibliographyCollectionPaperIds.has(paperId)) continue;
        await api.addPaperToBibliographyCollection(selectedBibliographyCollectionId, paperId);
      }
      await Promise.all([loadBibliographyCollections(), loadSelectedBibliographyCollectionPaperIds()]);
      setSelectedBibIds(new Set());
      setStatus("Papers added to collection.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add papers to collection");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveSelectedPapersFromCollection() {
    if (!selectedBibliographyCollectionId || selectedBibIds.size === 0) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      for (const paperId of selectedBibIds) {
        if (!selectedBibliographyCollectionPaperIds.has(paperId)) continue;
        await api.removePaperFromBibliographyCollection(selectedBibliographyCollectionId, paperId);
      }
      await Promise.all([loadBibliographyCollections(), loadSelectedBibliographyCollectionPaperIds()]);
      setSelectedBibIds(new Set());
      setStatus("Papers removed from collection.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove papers from collection");
    } finally {
      setSaving(false);
    }
  }

  async function handleBulkImportBibliographyCollection() {
    if (!selectedProjectId || !selectedBibliographyCollectionId || !currentProject) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      if (currentProject.project_kind === "research") {
        if (!bulkResearchTargetCollectionId) throw new Error("Select a research collection first.");
        const result = await api.bulkLinkBibliographyCollectionToResearch(selectedBibliographyCollectionId, {
          project_id: selectedProjectId,
          collection_id: bulkResearchTargetCollectionId,
          reading_status: "unread",
        });
        await refreshResearchDataAfterReferenceChange(bulkResearchTargetCollectionId);
        setStatus(`${result.linked} papers imported.`);
      } else if (currentProject.project_kind === "teaching") {
        const result = await api.bulkLinkBibliographyCollectionToTeaching(selectedBibliographyCollectionId, {
          project_id: selectedProjectId,
        });
        setStatus(`${result.linked} papers imported.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk import failed");
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
      setError("Select a study first.");
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
    if (!selectedProjectId) return;
    try {
      await api.deleteGlobalBibliography(id);
      await loadBibliography();
      setStatus("Paper deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete paper");
    }
  }

  function toggleBibSelection(id: string) {
    setSelectedBibIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllBibSelection() {
    if (selectedBibIds.size === filteredBibliography.length) {
      setSelectedBibIds(new Set());
    } else {
      setSelectedBibIds(new Set(filteredBibliography.map((item) => item.id)));
    }
  }

  function generateBibtexEntry(item: BibliographyReference): string {
    if (item.bibtex_raw) return item.bibtex_raw.trim();
    const key = (item.authors[0]?.split(" ").pop()?.toLowerCase() ?? "unknown") + (item.year ?? "nd");
    const fields: string[] = [];
    fields.push(`  title = {${item.title}}`);
    if (item.authors.length) fields.push(`  author = {${item.authors.join(" and ")}}`);
    if (item.year) fields.push(`  year = {${item.year}}`);
    if (item.venue) fields.push(`  journal = {${item.venue}}`);
    if (item.doi) fields.push(`  doi = {${item.doi}}`);
    if (item.url) fields.push(`  url = {${item.url}}`);
    if (item.abstract) fields.push(`  abstract = {${item.abstract}}`);
    return `@article{${key},\n${fields.join(",\n")}\n}`;
  }

  function exportSelectedBib() {
    const selected = bibliography.filter((item) => selectedBibIds.has(item.id));
    if (!selected.length) return;
    const content = selected.map(generateBibtexEntry).join("\n\n");
    const blob = new Blob([content], { type: "application/x-bibtex" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "bibliography.bib";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleBibliographyEmbedBackfill() {
    try {
      setSaving(true);
      const result = await api.backfillBibliographyEmbeddings();
      setStatus(`Indexed ${result.embedded} paper${result.embedded !== 1 ? "s" : ""}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to index papers.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleExpandBibRow(id: string) {
    if (expandedBibId === id) {
      setExpandedBibId(null);
      setExpandedBibNotes([]);
      return;
    }
    setExpandedBibId(id);
    setExpandedBibNotesLoading(true);
    try {
      const res = await api.listBibliographyNotes(id);
      setExpandedBibNotes(res.items);
    } catch {
      setExpandedBibNotes([]);
    } finally {
      setExpandedBibNotesLoading(false);
    }
  }

  async function handleAddBibNote() {
    if (!expandedBibId || !newNoteContent.trim()) return;
    try {
      setSaving(true);
      await api.createBibliographyNote(expandedBibId, {
        content: newNoteContent.trim(),
        note_type: newNoteType,
        visibility: newNoteVisibility,
      });
      setNewNoteContent("");
      const res = await api.listBibliographyNotes(expandedBibId);
      setExpandedBibNotes(res.items);
      await loadBibliography();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add note.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteBibNote(noteId: string) {
    if (!expandedBibId) return;
    try {
      await api.deleteBibliographyNote(noteId);
      const res = await api.listBibliographyNotes(expandedBibId);
      setExpandedBibNotes(res.items);
      await loadBibliography();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete note.");
    }
  }

  async function handleSetReadingStatus(refId: string, status: string) {
    try {
      await api.setBibliographyReadingStatus(refId, status);
      setBibliography((prev) =>
        prev.map((item) => (item.id === refId ? { ...item, reading_status: status } : item))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status.");
    }
  }

  async function handleOpenBibliographyAttachment(item: BibliographyReference) {
    try {
      setOpeningBibliographyAttachmentId(item.id);
      const blob = await api.getGlobalBibliographyAttachment(item.id);
      const url = URL.createObjectURL(blob);
      setBibliographyPreview((current) => {
        if (current?.url) URL.revokeObjectURL(current.url);
        return {
          title: item.title,
          filename: item.attachment_filename || "paper.pdf",
          url,
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open paper PDF");
    } finally {
      setOpeningBibliographyAttachmentId(null);
    }
  }

  function buildBibliographyFallbackReference(reference: ResearchReference): BibliographyReference {
    return (
      bibliography.find((item) => item.id === reference.bibliography_reference_id) || {
        id: reference.bibliography_reference_id || reference.id,
        source_project_id: null,
        document_key: reference.document_key,
        title: reference.title,
        authors: reference.authors,
        year: reference.year,
        venue: reference.venue,
        doi: reference.doi,
        url: reference.url,
        abstract: reference.abstract,
        bibtex_raw: null,
        tags: reference.tags,
        concepts: [],
        visibility: reference.bibliography_visibility || "shared",
        created_by_user_id: null,
        attachment_filename: reference.bibliography_attachment_filename,
        attachment_url: reference.bibliography_attachment_url,
        document_status: reference.document_key ? "indexed" : "no_pdf",
        warning: null,
        linked_project_count: 0,
        note_count: 0,
        reading_status: reference.reading_status,
        ai_summary: reference.ai_summary,
        ai_summary_at: reference.ai_summary_at,
        semantic_evidence: [],
        created_at: reference.created_at,
        updated_at: reference.updated_at,
      }
    );
  }

  function openBibliographyGraph(referencesToGraph: BibliographyReference[]) {
    setBibliographyGraphReferences(referencesToGraph);
    setBibliographyGraphOpen(true);
  }

  async function handleOpenBibliographyCollectionGraph(collectionId: string) {
    try {
      setError("");
      const response = await api.listGlobalBibliography({ bibliography_collection_id: collectionId, page_size: 100 });
      openBibliographyGraph(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load collection graph.");
    }
  }

  async function handleIngestBibliographyAttachment(item: BibliographyReference) {
    const documentStatus = item.document_status || "";
    if (!["uploaded", "failed", "pending"].includes(documentStatus)) return;
    if (!item.attachment_url) {
      setError("No PDF attached to this paper.");
      return;
    }
    if (!item.source_project_id && !selectedProjectId) {
      setError("Select a project before ingesting this paper PDF.");
      return;
    }
    try {
      setIngestingBibliographyId(item.id);
      setError("");
      setStatus("");
      const updated = await api.ingestGlobalBibliographyAttachment(
        item.id,
        item.source_project_id || selectedProjectId || null,
      );
      setBibliography((prev) => prev.map((entry) => (entry.id === item.id ? updated : entry)));
      setStatus(updated.document_status === "indexed" ? "Paper indexed." : "Paper ingestion started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to ingest paper PDF");
    } finally {
      setIngestingBibliographyId(null);
    }
  }

  function closeBibliographyPreview() {
    setBibliographyPreview((current) => {
      if (current?.url) URL.revokeObjectURL(current.url);
      return null;
    });
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
          lane: noteLane || null,
          note_type: noteType || "observation",
          linked_reference_ids: noteReferenceIds,
        });
        setStatus("Log added.");
      } else if (editingNoteId) {
        await api.updateResearchNote(selectedProjectId, editingNoteId, {
          title: noteTitle.trim(),
          content: noteContent.trim(),
          collection_id: noteCollectionId,
          lane: noteLane || null,
          note_type: noteType || "observation",
        });
        await api.setNoteReferences(selectedProjectId, editingNoteId, noteReferenceIds);
        setStatus("Log updated.");
      }
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId), loadSupportData()]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setNoteModalOpen(false);
      resetNoteForm(selectedCollectionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save log");
    } finally {
      setSaving(false);
    }
  }

  async function handleQuickLogSubmit() {
    if (!selectedProjectId || !selectedCollectionId || !quickLogContent.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      await api.createResearchNote(selectedProjectId, {
        title: quickLogTitle.trim() || deriveLogTitle(quickLogContent),
        content: quickLogContent.trim(),
        lane: quickLogLane || null,
        collection_id: selectedCollectionId,
        note_type: "observation",
        linked_reference_ids: quickLogRefIds,
      });
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId), loadSupportData()]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setQuickLogContent("");
      setQuickLogTitle("");
      setQuickLogLane("");
      setQuickLogRefIds([]);
      setStatus("Log added.");
      setTimeout(() => {
        quickLogInputRef.current?.focus();
      }, 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save log");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!selectedProjectId) return;
    try {
      await api.deleteResearchNote(selectedProjectId, noteId);
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId)]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setStatus("Log deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete log");
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
  if (loading) return <SkeletonTable rows={6} cols={4} />;

  return (
    <>
      {quickSearch.open ? (
        <div className="quick-search-bar">
          <FontAwesomeIcon icon={faSearch} className="quick-search-icon" />
          <input
            ref={quickSearch.inputRef}
            type="text"
            className="quick-search-input"
            placeholder="Filter current list..."
            value={quickSearch.query}
            onChange={(e) => quickSearch.setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") quickSearch.close(); }}
          />
          <kbd className="cmd-palette-kbd">esc</kbd>
        </div>
      ) : null}

      {!bibliographyOnly ? (
        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <span>{collections.length} studies</span>
            <span className="setup-summary-sep" />
            <span>{bibliography.length} papers</span>
            <span className="setup-summary-sep" />
            <span>{references.length} references</span>
            <span className="setup-summary-sep" />
            <span>{readCount} read</span>
            <span className="setup-summary-sep" />
            <span>{notes.length} inbox</span>
          </div>
          <button type="button" className="meetings-new-btn" onClick={openCreateCollectionModal}>
            <FontAwesomeIcon icon={faPlus} /> New Study
          </button>
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="muted-small">{status}</p> : null}

      {!bibliographyOnly && (selectedCollectionId || tab !== "overview") ? (
        <nav className="breadcrumb-bar">
          <button type="button" className="breadcrumb-link" onClick={() => { setSelectedCollectionId(null); setTab("overview"); }}>
            {currentProject?.title || "Research"}
          </button>
          {selectedCollection ? (
            <>
              <FontAwesomeIcon icon={faChevronRight} className="breadcrumb-sep" />
              <button type="button" className="breadcrumb-link" onClick={() => setTab("overview")}>
                {selectedCollection.title}
              </button>
            </>
          ) : null}
          {tab !== "overview" ? (
            <>
              <FontAwesomeIcon icon={faChevronRight} className="breadcrumb-sep" />
              <span className="breadcrumb-current">
                {{ references: "References", notes: "Inbox", paper: "Paper", iterations: "Iterations", overview: "Overview" }[tab]}
              </span>
            </>
          ) : null}
        </nav>
      ) : null}

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
          {activeCollections.length === 0 ? (
            <span className="muted-small" style={{ padding: "0 4px" }}>Create a study to start organizing your research.</span>
          ) : null}
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
            <span className="muted-small">{collectionDetail.reference_count} references</span>
            <span className="setup-summary-sep" />
            <span className="muted-small">{collectionDetail.note_count} logs</span>
            <span className="setup-summary-sep" />
            <span className="muted-small">{collectionDetail.member_count} members</span>
          </div>
          {collectionDetail.description || collectionDetail.hypothesis ? (
            <p className="muted-small research-hypothesis">{collectionDetail.description || collectionDetail.hypothesis}</p>
          ) : null}
          <div className="research-header-actions">
            <button type="button" className="meetings-new-btn" onClick={openCreateNoteModal}>
              <FontAwesomeIcon icon={faPlus} /> New Log
            </button>
            <button type="button" className="ghost docs-action-btn" title="Edit Study" onClick={openEditCollectionModal}>
              <FontAwesomeIcon icon={faPen} />
            </button>
            <button type="button" className="ghost docs-action-btn" title="Link Context" onClick={openWbsModal}>
              <FontAwesomeIcon icon={faLink} />
            </button>
            <button type="button" className="ghost docs-action-btn" title="Archive" onClick={() => handleArchiveCollection(selectedCollection.id)}>
              <FontAwesomeIcon icon={faArchive} />
            </button>
            <button
              type="button"
              className={`ghost docs-action-btn danger${confirmingDeleteId === selectedCollection.id ? " confirm-pulse" : ""}`}
              title={confirmingDeleteId === selectedCollection.id ? "Click again to confirm" : "Delete"}
              onClick={() => requestConfirmDelete(selectedCollection.id, () => handleDeleteCollection(selectedCollection.id))}
            >
              {confirmingDeleteId === selectedCollection.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
            </button>
          </div>
        </div>
      ) : null}

      {!bibliographyOnly ? <div className="delivery-tabs">
        <button className={`delivery-tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          Overview
        </button>
        <button className={`delivery-tab inbox-tab ${tab === "notes" ? "active" : ""}`} onClick={() => setTab("notes")}>
          <FontAwesomeIcon icon={faInbox} /> Inbox <span className="delivery-tab-count">{notes.length}</span>
        </button>
        <button className={`delivery-tab ${tab === "references" ? "active" : ""}`} onClick={() => setTab("references")}>
          References <span className="delivery-tab-count">{references.length}</span>
        </button>
        <button className={`delivery-tab ${tab === "paper" ? "active" : ""}`} onClick={() => setTab("paper")}>
          Paper
        </button>
        <button className={`delivery-tab ${tab === "iterations" ? "active" : ""}`} onClick={() => setTab("iterations")}>
          Iterations <span className="delivery-tab-count">{studyIterations.length}</span>
        </button>
        {tab === "references" ? (
          <div className="bibliography-tab-tools">
            <button
              type="button"
              className="ghost icon-text-button small"
              disabled={references.length === 0}
              onClick={() => {
                const linked = references.filter((item) => item.bibliography_reference_id).map((item) => buildBibliographyFallbackReference(item));
                openBibliographyGraph(linked);
              }}
            >
              <FontAwesomeIcon icon={faShareNodes} /> Graph
            </button>
            <button
              type="button"
              className="meetings-new-btn delivery-tab-action"
              onClick={openBibliographyPicker}
              disabled={!selectedCollectionId}
            >
              <FontAwesomeIcon icon={faFileImport} /> Import
            </button>
          </div>
        ) : null}
        {tab === "notes" ? (
          <div className="bibliography-tab-tools">
            <button
              type="button"
              className="meetings-new-btn delivery-tab-action"
              disabled={selectedInboxLogIds.size === 0}
              onClick={() => void handleCreateIterationFromLogs(Array.from(selectedInboxLogIds))}
            >
              <FontAwesomeIcon icon={faPlus} /> Iteration
            </button>
            <button
              type="button"
              className="meetings-new-btn delivery-tab-action"
              onClick={openCreateNoteModal}
              disabled={!selectedCollectionId}
            >
              <FontAwesomeIcon icon={faPlus} /> New Log
            </button>
          </div>
        ) : null}
        {tab === "iterations" ? (
          <div className="bibliography-tab-tools">
            <button
              type="button"
              className="ghost icon-text-button small"
              disabled={saving || !selectedCollectionId}
              onClick={() => void persistPaperWorkspace(undefined, { successMessage: "Iterations updated." })}
            >
              Save
            </button>
          </div>
        ) : null}
        {tab === "paper" ? (
          <div className="bibliography-tab-tools">
            <button type="button" className={`meetings-new-btn${paperDirty ? " unsaved" : ""}`} disabled={saving} onClick={() => void handleSavePaperWorkspace()}>
              {saving ? "Saving..." : paperDirty ? "Save *" : "Save"}
            </button>
          </div>
        ) : null}
      </div>
      : null}

      {tab === "references" && !bibliographyOnly ? renderReferencesTab() : null}
      {bibliographyOnly ? renderBibliographyTab() : null}
      {tab === "notes" && !bibliographyOnly ? renderNotesTab() : null}
      {tab === "paper" && !bibliographyOnly ? renderPaperTab() : null}
      {tab === "iterations" && !bibliographyOnly ? renderIterationsTab() : null}
      {tab === "overview" && !bibliographyOnly ? renderOverviewTab() : null}

      {!bibliographyOnly && collectionModalOpen ? renderCollectionModal() : null}
      {!bibliographyOnly && referenceModalOpen ? renderReferenceModal() : null}
      {bibliographyModalOpen ? renderBibliographyModal() : null}
      {bibliographyDuplicateModalOpen ? renderBibliographyDuplicateModal() : null}
      {bibliographyPreview ? renderBibliographyPreviewModal() : null}
      {bibliographyGraphOpen ? (
        <BibliographyGraphModal
          references={bibliographyGraphReferences}
          onClose={() => {
            setBibliographyGraphOpen(false);
            setBibliographyGraphReferences([]);
          }}
          onOpenPaper={(reference) => {
            setBibliographyGraphOpen(false);
            openEditBibliographyModal(reference);
          }}
          onOpenAttachment={(reference) => {
            void handleOpenBibliographyAttachment(reference);
          }}
          openingAttachmentId={openingBibliographyAttachmentId}
        />
      ) : null}
      {bibliographyCollectionModalOpen ? renderBibliographyCollectionModal() : null}
      {addToCollectionModalOpen ? renderAddToCollectionModal() : null}
      {!bibliographyOnly && bibliographyPickerOpen ? renderBibliographyPickerModal() : null}
      {!bibliographyOnly && noteModalOpen ? renderNoteModal() : null}
      {!bibliographyOnly && memberModalOpen ? renderMemberModal() : null}
      {!bibliographyOnly && wbsModalOpen ? renderWbsModal() : null}
    </>
  );

  function renderReferencesTab() {
    if (!selectedCollectionId) {
      return <p className="empty-message">Select a study to import and manage references.</p>;
    }

    const referenceUsage = (referenceId: string) => {
      const claimCount = paperClaims.filter((item) => item.reference_ids.includes(referenceId)).length;
      const sectionCount = paperSections.filter((item) => item.reference_ids.includes(referenceId)).length;
      const noteCount = notes.filter((item) => item.linked_reference_ids.includes(referenceId)).length;
      return { claimCount, sectionCount, noteCount };
    };

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
          <p className="empty-message">No references in this study.</p>
        ) : (
          <div className="simple-table-wrap bib-table-fill">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Paper</th>
                  <th>Year</th>
                  <th>Status</th>
                  <th>Actions</th>
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
                      {(() => {
                        const usage = referenceUsage(reference.id);
                        return usage.claimCount + usage.sectionCount + usage.noteCount > 0 ? (
                          <span className="research-chip-group">
                            {usage.claimCount ? <span className="chip small">{usage.claimCount} claims</span> : null}
                            {usage.sectionCount ? <span className="chip small">{usage.sectionCount} sections</span> : null}
                            {usage.noteCount ? <span className="chip small">{usage.noteCount} notes</span> : null}
                          </span>
                        ) : null;
                      })()}
                      {reference.ai_summary ? (() => {
                        const summary = parseSummaryPayload(reference.ai_summary);
                        return (
                          <details className="research-inline-summary">
                            <summary>AI Summary</summary>
                            {renderPaperSummary(summary, reference.ai_summary, { compact: true })}
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
                      <div className="note-row-actions">
                        <button
                          type="button"
                          className="ghost icon-text-button small"
                          onClick={() => void handlePromoteReferenceToClaim(reference)}
                        >
                          Claim
                        </button>
                        <button
                          type="button"
                          className="ghost icon-text-button small"
                          onClick={() => void handlePromoteReferenceToQuestion(reference)}
                        >
                          Question
                        </button>
                        <button
                          type="button"
                          className="ghost docs-action-btn"
                          title={reference.bibliography_reference_id ? "Open paper" : "Edit reference"}
                          onClick={() =>
                            reference.bibliography_reference_id
                              ? openEditBibliographyModal(buildBibliographyFallbackReference(reference))
                              : openEditReferenceModal(reference)
                          }
                        >
                          <FontAwesomeIcon icon={reference.bibliography_reference_id ? faBookOpen : faPen} />
                        </button>
                      </div>
                    </td>
                    <td className="col-icon">
                      <button
                        type="button"
                        className={`ghost docs-action-btn${confirmingDeleteId === reference.id ? " danger confirm-pulse" : ""}`}
                        title={confirmingDeleteId === reference.id ? "Click again to confirm" : "Delete"}
                        onClick={() => requestConfirmDelete(reference.id, () => handleDeleteReference(reference.id))}
                      >
                        {confirmingDeleteId === reference.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
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
        <div className="delivery-tabs">
          <button className={`delivery-tab ${bibTab === "papers" ? "active" : ""}`} onClick={() => setBibTab("papers")}>
            Papers <span className="delivery-tab-count">{bibliography.length}</span>
          </button>
          <button className={`delivery-tab ${bibTab === "collections" ? "active" : ""}`} onClick={() => setBibTab("collections")}>
            Collections <span className="delivery-tab-count">{bibliographyCollections.length}</span>
          </button>
          {bibTab === "papers" ? (
            <div className="bibliography-tab-tools">
              <div className="meetings-filter-group bib-search-group bibliography-tab-search">
                <input
                  className={`meetings-search bib-search-wide${searchingBibliography ? " bib-search-loading" : ""}`}
                  type="text"
                  placeholder={semanticSearch ? "Semantic search (Enter)..." : "Search papers..."}
                  value={bibliographySearch}
                  onChange={(event) => setBibliographySearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (semanticSearch && event.key === "Enter") {
                      event.preventDefault();
                      void runSemanticSearch();
                    }
                  }}
                  disabled={searchingBibliography}
                />
                {searchingBibliography ? <span className="bib-search-spinner" /> : null}
                <button
                  type="button"
                  className={`bib-toggle-btn${semanticSearch ? " bib-toggle-btn-active" : ""}`}
                  onClick={() => setSemanticSearch((v) => !v)}
                >
                  Semantic
                </button>
              </div>
              <button
                type="button"
                className={`ghost docs-action-btn${bibliographyFiltersOpen ? " active" : ""}`}
                onClick={() => setBibliographyFiltersOpen((value) => !value)}
                title="Filters"
              >
                <FontAwesomeIcon icon={faFilter} />
              </button>
              <button
                type="button"
                className="ghost icon-text-button small"
                onClick={() => openBibliographyGraph(filteredBibliography)}
                disabled={filteredBibliography.length === 0}
              >
                <FontAwesomeIcon icon={faShareNodes} /> Show Graph
              </button>
              <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openCreateBibliographyModal}>
                <FontAwesomeIcon icon={faPlus} /> Add Paper
              </button>
            </div>
          ) : (
            <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openCreateBibliographyCollectionModal}>
              <FontAwesomeIcon icon={faPlus} /> New Collection
            </button>
          )}
        </div>

        {bibTab === "papers" ? renderBibliographyPapersView() : renderBibliographyCollectionsView()}
      </>
    );
  }

  function renderBibliographyPapersView() {
    const totalColSpan = bibliographyOnly ? 6 : 7;
    return (
      <>
        {selectedBibIds.size > 0 ? (
          <div className="meetings-toolbar bib-toolbar">
            <div className="meetings-filter-group">
              <button type="button" className="meetings-new-btn" onClick={() => { setAddToCollectionId(""); setAddToCollectionModalOpen(true); }}>
                <FontAwesomeIcon icon={faPlus} /> Add to Collection ({selectedBibIds.size})
              </button>
              <button type="button" className="ghost icon-text-button small" onClick={exportSelectedBib}>
                <FontAwesomeIcon icon={faFileExport} /> Export .bib
              </button>
            </div>
          </div>
        ) : null}

        {bibliographyFiltersOpen ? (
          <div className="bib-filter-panel">
            <div className="meetings-filter-group">
              {bibliographyCollections.length > 0 ? (
                <select value={selectedBibliographyCollectionId ?? ""} onChange={(event) => setSelectedBibliographyCollectionId(event.target.value || null)}>
                  <option value="">All collections</option>
                  {bibliographyCollections.map((c) => (
                    <option key={c.id} value={c.id}>{c.title}</option>
                  ))}
                </select>
              ) : null}
              {bibliographyTagsInUse.length > 0 ? (
                <select value={bibliographyTagFilter} onChange={(event) => setBibliographyTagFilter(event.target.value)}>
                  <option value="">All tags</option>
                  {bibliographyTagsInUse.map((tag) => (
                    <option key={tag} value={tag}>{tag}</option>
                  ))}
                </select>
              ) : null}
              <select value={bibliographyStatusFilter} onChange={(event) => setBibliographyStatusFilter(event.target.value)}>
                <option value="">All status</option>
                <option value="unread">Unread</option>
                <option value="reading">Reading</option>
                <option value="read">Read</option>
                <option value="reviewed">Reviewed</option>
              </select>
              <select value={bibliographyVisibilityFilter} onChange={(event) => setBibliographyVisibilityFilter(event.target.value)}>
                <option value="">All visibility</option>
                <option value="shared">Shared</option>
                <option value="private">Private</option>
              </select>
              <button
                type="button"
                className="ghost icon-text-button small"
                onClick={() => {
                  setSelectedBibliographyCollectionId(null);
                  setBibliographyTagFilter("");
                  setBibliographyStatusFilter("");
                  setBibliographyVisibilityFilter("");
                }}
              >
                Reset
              </button>
            </div>
          </div>
        ) : null}

        {filteredBibliography.length === 0 ? (
          <p className="empty-message">{bibliography.length === 0 ? "No papers yet." : "No papers match filters."}</p>
        ) : (
          <div className={`simple-table-wrap bib-table-fill${bibliographyFiltersOpen ? " bib-filters-active" : ""}`}>
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th className="col-icon">
                    <input
                      type="checkbox"
                      checked={filteredBibliography.length > 0 && selectedBibIds.size === filteredBibliography.length}
                      onChange={toggleAllBibSelection}
                    />
                  </th>
                  <th className="sortable-th" onClick={() => toggleBibSort("title")}>
                    Title
                    {bibSortKey === "title" && <FontAwesomeIcon icon={bibSortDir === "asc" ? faChevronUp : faChevronDown} className="sort-indicator" />}
                  </th>
                  <th className="sortable-th" onClick={() => toggleBibSort("year")}>
                    Year
                    {bibSortKey === "year" && <FontAwesomeIcon icon={bibSortDir === "asc" ? faChevronUp : faChevronDown} className="sort-indicator" />}
                  </th>
                  <th className="sortable-th" onClick={() => toggleBibSort("status")}>
                    Status
                    {bibSortKey === "status" && <FontAwesomeIcon icon={bibSortDir === "asc" ? faChevronUp : faChevronDown} className="sort-indicator" />}
                  </th>
                  <th className="col-icon" />
                  {!bibliographyOnly ? <th className="col-icon" /> : null}
                  <th className="col-icon" />
                </tr>
              </thead>
              <tbody>
                {filteredBibliography.map((item) => (
                  <React.Fragment key={item.id}>
                    <tr
                      className={`bib-row-clickable${selectedBibIds.has(item.id) ? " row-selected" : ""}${expandedBibId === item.id ? " bib-row-expanded" : ""}`}
                      onClick={() => void toggleExpandBibRow(item.id)}
                    >
                      <td className="col-icon" onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedBibIds.has(item.id)}
                          onChange={() => toggleBibSelection(item.id)}
                        />
                      </td>
                      <td>
                        <div className="bib-cell-title">
                          <strong>{item.title}</strong>
                          <button
                            type="button"
                            className={`bib-doc-status bib-doc-status-${item.document_status || "pending"}${
                              ["uploaded", "failed", "pending"].includes(item.document_status || "") ? " clickable" : ""
                            }`}
                            disabled={
                              ingestingBibliographyId === item.id ||
                              !["uploaded", "failed", "pending"].includes(item.document_status || "")
                            }
                            title={
                              item.document_status === "failed"
                                ? "Retry ingestion"
                                : item.document_status === "uploaded" || item.document_status === "pending"
                                  ? "Ingest PDF"
                                  : bibliographyDocumentStatusLabel(item.document_status)
                            }
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleIngestBibliographyAttachment(item);
                            }}
                          >
                            {ingestingBibliographyId === item.id ? "..." : bibliographyDocumentStatusLabel(item.document_status)}
                          </button>
                          {item.attachment_url ? (
                            <button
                              type="button"
                              className="ghost bib-file-btn"
                              title={item.attachment_filename || "Open file"}
                              disabled={openingBibliographyAttachmentId === item.id}
                              onClick={(event) => { event.stopPropagation(); void handleOpenBibliographyAttachment(item); }}
                            >
                              <FontAwesomeIcon icon={faFileArrowUp} spin={openingBibliographyAttachmentId === item.id} />
                            </button>
                          ) : null}
                          {item.note_count > 0 ? (
                            <span className="bib-note-badge">
                              <FontAwesomeIcon icon={faComment} /> {item.note_count}
                            </span>
                          ) : null}
                        </div>
                        <span className="muted-small research-inline-meta">
                          {item.authors.join(", ") || "No authors"}
                          {item.venue ? ` \u00b7 ${item.venue}` : ""}
                        </span>
                        {semanticSearch && item.semantic_evidence.length > 0 ? (
                          <div className="bib-semantic-evidence">
                            {item.semantic_evidence.map((chunk, index) => (
                              <div key={`${item.id}-evidence-${index}`} className="bib-semantic-evidence-item">
                                {chunk.similarity !== null ? (
                                  <span className="bib-semantic-score">{Math.round(chunk.similarity * 100)}%</span>
                                ) : null}
                                <span>{chunk.text}</span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {item.tags.length > 0 ? (
                          <span className="research-chip-group">
                            {item.tags.map((tag) => (
                              <span key={`${item.id}-${tag}`} className="chip small">{tag}</span>
                            ))}
                          </span>
                        ) : null}
                      </td>
                      <td className="bib-cell-year">{item.year || "-"}</td>
                      <td onClick={(event) => event.stopPropagation()}>
                        <select
                          className="bib-status-select"
                          value={item.reading_status}
                          onChange={(event) => void handleSetReadingStatus(item.id, event.target.value)}
                        >
                          <option value="unread">Unread</option>
                          <option value="reading">Reading</option>
                          <option value="read">Read</option>
                          <option value="reviewed">Reviewed</option>
                        </select>
                      </td>
                      <td className="col-icon" onClick={(event) => event.stopPropagation()}>
                        <div className="research-icon-actions">
                          <button
                            type="button"
                            className="ghost docs-action-btn"
                            title="Summarize"
                            disabled={summarizingId === item.id}
                            onClick={() => void handleSummarizeBibliography(item.id)}
                          >
                            <FontAwesomeIcon icon={faMagicWandSparkles} spin={summarizingId === item.id} />
                          </button>
                          <button
                            type="button"
                            className="ghost docs-action-btn"
                            title="Copy link"
                            onClick={() => void handleCopyBibliographyPermalink(item)}
                          >
                            <FontAwesomeIcon icon={faLink} />
                          </button>
                        </div>
                      </td>
                      {!bibliographyOnly ? (
                        <td className="col-icon" onClick={(event) => event.stopPropagation()}>
                          <button
                            type="button"
                            className="ghost docs-action-btn"
                            title="Link to research collection"
                            onClick={() => void handleLinkBibliography(item)}
                            disabled={!selectedCollectionId}
                          >
                            <FontAwesomeIcon icon={faLink} />
                          </button>
                        </td>
                      ) : null}
                      <td className="col-icon">
                        <FontAwesomeIcon icon={faChevronRight} className={`bib-expand-icon${expandedBibId === item.id ? " bib-expand-icon-open" : ""}`} />
                      </td>
                    </tr>
                    {expandedBibId === item.id ? (
                      <tr className="bib-expanded-row">
                        <td colSpan={totalColSpan}>
                          <div className="bib-expanded-content">
                            {item.abstract ? (
                              <div className="bib-abstract-section">
                                <span className="bib-section-label">Abstract</span>
                                <p className="bib-abstract-text">{item.abstract}</p>
                              </div>
                            ) : null}
                            {item.ai_summary ? (() => {
                              const summary = parseSummaryPayload(item.ai_summary);
                              return (
                                <details className="research-inline-summary">
                                  <summary>AI Summary</summary>
                                  {renderPaperSummary(summary, item.ai_summary)}
                                </details>
                              );
                            })() : null}
                            {item.concepts.length > 0 ? (
                              <details className="research-inline-summary" open>
                                <summary>Concepts</summary>
                                <div className="research-chip-group">
                                  {item.concepts.map((concept) => (
                                    <span key={`${item.id}-concept-${concept}`} className="chip small">{concept}</span>
                                  ))}
                                </div>
                              </details>
                            ) : null}
                            {item.doi ? (
                              <span className="muted-small">DOI: {item.doi}</span>
                            ) : null}
                            <div className="bib-notes-panel">
                              <div className="bib-notes-header">
                                <strong>Notes</strong>
                                <span className="muted-small">{expandedBibNotes.length} note{expandedBibNotes.length !== 1 ? "s" : ""}</span>
                                <span style={{ flex: 1 }} />
                                <button type="button" className="ghost docs-action-btn" title="Edit paper" onClick={(event) => { event.stopPropagation(); openEditBibliographyModal(item); }}>
                                  <FontAwesomeIcon icon={faPen} />
                                </button>
                                <button type="button" className="ghost docs-action-btn" title="Copy link" onClick={(event) => { event.stopPropagation(); void handleCopyBibliographyPermalink(item); }}>
                                  <FontAwesomeIcon icon={faLink} />
                                </button>
                                <button
                                  type="button"
                                  className={`ghost docs-action-btn${confirmingDeleteId === item.id ? " danger confirm-pulse" : ""}`}
                                  title={confirmingDeleteId === item.id ? "Click again to confirm" : "Delete paper"}
                                  onClick={() => requestConfirmDelete(item.id, () => void handleDeleteBibliography(item.id))}
                                >
                                  {confirmingDeleteId === item.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
                                </button>
                              </div>
                              {expandedBibNotesLoading ? (
                                <p className="muted-small">Loading...</p>
                              ) : (
                                <>
                                  {expandedBibNotes.map((note) => (
                                    <div key={note.id} className="bib-note-item">
                                      <div className="bib-note-meta">
                                        <strong>{note.user_display_name}</strong>
                                        <span className="chip small">{note.note_type}</span>
                                        {note.visibility === "private" ? <span className="chip small">private</span> : null}
                                        <span className="muted-small">{formatRelativeTime(note.created_at)}</span>
                                        <button
                                          type="button"
                                          className="ghost docs-action-btn danger"
                                          title="Delete"
                                          onClick={() => requestConfirmDelete(note.id, () => void handleDeleteBibNote(note.id))}
                                        >
                                          {confirmingDeleteId === note.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
                                        </button>
                                      </div>
                                      <p className="bib-note-content">{note.content}</p>
                                    </div>
                                  ))}
                                  <div className="bib-note-form">
                                    <textarea
                                      className="bib-note-textarea"
                                      rows={2}
                                      placeholder="Add a note..."
                                      value={newNoteContent}
                                      onChange={(event) => setNewNoteContent(event.target.value)}
                                    />
                                    <div className="bib-note-form-actions">
                                      <select value={newNoteType} onChange={(event) => setNewNoteType(event.target.value)}>
                                        <option value="comment">Comment</option>
                                        <option value="finding">Finding</option>
                                        <option value="critique">Critique</option>
                                        <option value="question">Question</option>
                                        <option value="key_quote">Key quote</option>
                                      </select>
                                      <select value={newNoteVisibility} onChange={(event) => setNewNoteVisibility(event.target.value)}>
                                        <option value="shared">Shared</option>
                                        <option value="private">Private</option>
                                      </select>
                                      <button
                                        type="button"
                                        className="meetings-new-btn"
                                        disabled={!newNoteContent.trim() || saving}
                                        onClick={() => void handleAddBibNote()}
                                      >
                                        Add Note
                                      </button>
                                    </div>
                                  </div>
                                </>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  function renderBibliographyCollectionsView() {
    return (
      <>
        {bibliographyCollections.length === 0 ? (
          <p className="empty-message">No collections yet. Create one to organize your papers.</p>
        ) : (
          <div className="simple-table-wrap bib-table-fill">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Collection</th>
                  <th>Papers</th>
                  <th>Visibility</th>
                  {currentProject ? <th>Import</th> : null}
                  <th className="col-icon" />
                  <th className="col-icon" />
                  <th className="col-icon" />
                </tr>
              </thead>
              <tbody>
                {bibliographyCollections.map((item) => (
                  <tr key={item.id} className={selectedBibliographyCollectionId === item.id ? "row-selected" : ""}>
                    <td>
                      <button
                        type="button"
                        className="ghost bib-collection-name-btn"
                        onClick={() => {
                          setSelectedBibliographyCollectionId(item.id);
                          setBibTab("papers");
                        }}
                      >
                        <strong>{item.title}</strong>
                      </button>
                      {item.description ? <span className="muted-small research-inline-meta">{item.description}</span> : null}
                    </td>
                    <td>{item.reference_count}</td>
                    <td><span className="chip small">{item.visibility}</span></td>
                    {currentProject ? (
                      <td onClick={(event) => event.stopPropagation()}>
                        <div className="bib-collection-import-row">
                          {currentProject.project_kind === "research" ? (
                            <>
                              <select
                                className="bib-import-select"
                                value={selectedBibliographyCollectionId === item.id ? bulkResearchTargetCollectionId : ""}
                                onChange={(event) => {
                                  setSelectedBibliographyCollectionId(item.id);
                                  setBulkResearchTargetCollectionId(event.target.value);
                                }}
                              >
                                <option value="">Target...</option>
                                {collections.map((c) => (
                                  <option key={c.id} value={c.id}>{c.title}</option>
                                ))}
                              </select>
                              <button
                                type="button"
                                className="ghost docs-action-btn"
                                title="Import all papers to project"
                                disabled={saving || !(selectedBibliographyCollectionId === item.id && bulkResearchTargetCollectionId)}
                                onClick={async () => {
                                  if (!selectedProjectId || !currentProject || !bulkResearchTargetCollectionId) return;
                                  setSelectedBibliographyCollectionId(item.id);
                                  setSaving(true);
                                  setError("");
                                  setStatus("");
                                  try {
                                    const result = await api.bulkLinkBibliographyCollectionToResearch(item.id, {
                                      project_id: selectedProjectId,
                                      collection_id: bulkResearchTargetCollectionId,
                                      reading_status: "unread",
                                    });
                                    await refreshResearchDataAfterReferenceChange(bulkResearchTargetCollectionId);
                                    setStatus(`${result.linked} papers imported.`);
                                  } catch (err) {
                                    setError(err instanceof Error ? err.message : "Bulk import failed");
                                  } finally {
                                    setSaving(false);
                                  }
                                }}
                              >
                                <FontAwesomeIcon icon={faFileImport} />
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              className="ghost docs-action-btn"
                              title="Import all papers to project"
                              disabled={saving}
                              onClick={async () => {
                                setSelectedBibliographyCollectionId(item.id);
                                if (!selectedProjectId || !currentProject) return;
                                setSaving(true);
                                setError("");
                                setStatus("");
                                try {
                                  const result = await api.bulkLinkBibliographyCollectionToTeaching(item.id, { project_id: selectedProjectId });
                                  setStatus(`${result.linked} papers imported.`);
                                } catch (err) {
                                  setError(err instanceof Error ? err.message : "Bulk import failed");
                                } finally {
                                  setSaving(false);
                                }
                              }}
                            >
                              <FontAwesomeIcon icon={faFileImport} />
                            </button>
                          )}
                        </div>
                      </td>
                    ) : null}
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Show Graph" onClick={() => void handleOpenBibliographyCollectionGraph(item.id)}>
                        <FontAwesomeIcon icon={faShareNodes} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openEditBibliographyCollectionModal(item)}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                    </td>
                    <td className="col-icon">
                      <button
                        type="button"
                        className={`ghost docs-action-btn${confirmingDeleteId === item.id ? " danger confirm-pulse" : ""}`}
                        title={confirmingDeleteId === item.id ? "Click again to confirm" : "Delete"}
                        onClick={() => requestConfirmDelete(item.id, () => void handleDeleteBibliographyCollection(item.id))}
                      >
                        {confirmingDeleteId === item.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
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

  function renderAddToCollectionModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setAddToCollectionModalOpen(false)}>
        <div className="modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>Add {selectedBibIds.size} paper{selectedBibIds.size !== 1 ? "s" : ""} to collection</h3>
            <div className="modal-head-actions">
              <button
                type="button"
                className="meetings-new-btn"
                disabled={saving || !addToCollectionId}
                onClick={async () => {
                  if (!addToCollectionId) return;
                  setSaving(true);
                  setError("");
                  setStatus("");
                  try {
                    for (const paperId of selectedBibIds) {
                      await api.addPaperToBibliographyCollection(addToCollectionId, paperId);
                    }
                    await loadBibliographyCollections();
                    await loadSelectedBibliographyCollectionPaperIds();
                    const col = bibliographyCollections.find((c) => c.id === addToCollectionId);
                    setStatus(`${selectedBibIds.size} paper${selectedBibIds.size !== 1 ? "s" : ""} added to ${col?.title ?? "collection"}.`);
                    setSelectedBibIds(new Set());
                    setAddToCollectionModalOpen(false);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Failed to add papers");
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                Add
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={() => setAddToCollectionModalOpen(false)} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>
          <div className="form-grid">
            <label className="full-span">
              Collection
              <select value={addToCollectionId} onChange={(event) => setAddToCollectionId(event.target.value)}>
                <option value="">Select a collection...</option>
                {bibliographyCollections.map((c) => (
                  <option key={c.id} value={c.id}>{c.title} ({c.reference_count} papers)</option>
                ))}
              </select>
            </label>
          </div>
        </div>
      </div>
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
                            disabled={openingBibliographyAttachmentId === item.id}
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

  function renderLanePills(
    value: string,
    onChange: (next: string) => void,
    options?: { noneLabel?: string; className?: string },
  ) {
    const noneLabel = options?.noneLabel || "No lane";
    const className = options?.className ? ` ${options.className}` : "";
    return (
      <div className={`research-lane-pills${className}`}>
        <button
          type="button"
          className={`research-lane-pill${value === "" ? " active" : ""}`}
          onClick={() => onChange("")}
        >
          {noneLabel}
        </button>
        {NOTE_LANE_OPTIONS.map(([laneValue, laneLabel]) => (
          <button
            key={laneValue}
            type="button"
            className={`research-lane-pill${value === laneValue ? " active" : ""}`}
            onClick={() => onChange(laneValue)}
          >
            {laneLabel}
          </button>
        ))}
      </div>
    );
  }

  function renderNotesTab() {
    if (!selectedCollectionId) {
      return <p className="empty-message">Select a study to log work.</p>;
    }

    const questionNoteIds = new Set(paperQuestions.flatMap((item) => item.note_ids));
    const claimNoteIds = new Set(paperClaims.flatMap((item) => item.note_ids));
    const sectionNoteIds = new Set(paperSections.flatMap((item) => item.note_ids));
    const noteWorkflow = (note: ResearchNote) => {
      const promotedToQuestion = questionNoteIds.has(note.id);
      const promotedToClaim = claimNoteIds.has(note.id);
      const promotedToSection = sectionNoteIds.has(note.id);
      const promotionCount = [promotedToQuestion, promotedToClaim, promotedToSection].filter(Boolean).length;
      const state = promotionCount === 0 ? "Unprocessed" : "Promoted";
      return {
        state,
        promotedToQuestion,
        promotedToClaim,
        promotedToSection,
      };
    };
    const searchLower = noteSearchQuery.toLowerCase();
    const visibleNotes = searchLower
      ? notes.filter((note) => note.title.toLowerCase().includes(searchLower) || note.content.toLowerCase().includes(searchLower))
      : notes;
    const orderedNotes = [...visibleNotes].sort((a, b) => b.created_at.localeCompare(a.created_at));
    const unassignedLogs = notes.filter((note) => note.collection_id === selectedCollectionId && !noteIterationState(note.id).assigned);
    const allVisibleSelected = orderedNotes.length > 0 && orderedNotes.every((note) => selectedInboxLogIds.has(note.id));

    return (
      <>
        <div className={`research-log-composer${composerExpanded ? " expanded" : ""}`}>
          {composerExpanded ? (
            <input
              className="research-inline-title"
              value={quickLogTitle}
              onChange={(event) => setQuickLogTitle(event.target.value)}
              placeholder="Title (optional)"
            />
          ) : null}
          <textarea
            ref={quickLogInputRef}
            className="research-log-composer-input"
            rows={composerExpanded ? 4 : 1}
            value={quickLogContent}
            onChange={(event) => {
              const textarea = event.target;
              handleContentChange(textarea.value, textarea.selectionStart, textarea, "composer");
            }}
            onFocus={() => setComposerExpanded(true)}
            onBlur={() => { if (!quickLogContent.trim() && !quickLogTitle.trim()) setComposerExpanded(false); }}
            onKeyDown={(event) => {
              handleMentionKeyDown(event);
              if (mentionOpen) return;
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void handleQuickLogSubmit();
              }
            }}
            placeholder={composerExpanded ? "Content (markdown, @ to cite a reference)" : "Log a finding, observation, or note..."}
          />
          {composerExpanded ? (
            <div className="research-log-composer-actions">
              {renderLanePills(quickLogLane, setQuickLogLane, { className: "research-log-lane-pills" })}
              <button
                type="button"
                className="meetings-new-btn"
                disabled={!quickLogContent.trim() || saving}
                onClick={() => void handleQuickLogSubmit()}
              >
                <FontAwesomeIcon icon={faPlus} /> Log
              </button>
            </div>
          ) : null}
        </div>

        <div className="meetings-toolbar">
          <div className="meetings-filter-group">
            <label className="research-log-select-all">
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={() =>
                  setSelectedInboxLogIds((current) => {
                    if (allVisibleSelected) {
                      const next = new Set(current);
                      orderedNotes.forEach((note) => next.delete(note.id));
                      return next;
                    }
                    const next = new Set(current);
                    orderedNotes.forEach((note) => next.add(note.id));
                    return next;
                  })
                }
              />
              <span>{selectedInboxLogIds.size > 0 ? `${selectedInboxLogIds.size} selected` : "All"}</span>
            </label>
            {renderLanePills(noteLaneFilter, setNoteLaneFilter, { noneLabel: "All lanes", className: "research-lane-filter-pills" })}
            <input
              className="meetings-search"
              placeholder="Search logs..."
              value={noteSearchQuery}
              onChange={(event) => setNoteSearchQuery(event.target.value)}
            />
            {unassignedLogs.length > 0 ? (
              <button
                type="button"
                className="ghost icon-text-button small"
                onClick={() => setSelectedInboxLogIds(new Set(unassignedLogs.map((item) => item.id)))}
              >
                Select New ({unassignedLogs.length})
              </button>
            ) : null}
          </div>
        </div>

        {orderedNotes.length === 0 ? (
          <p className="empty-message">No logs in this study.</p>
        ) : (
          <div className="research-log-stream">
            <div className="research-log-list">
              {orderedNotes.map((note) => {
                const workflow = noteWorkflow(note);
                const iterationState = noteIterationState(note.id);
                const isSelected = selectedInboxLogIds.has(note.id);
                const isEditing = inlineEditNoteId === note.id;
                const linkedReferencesLabel = note.linked_reference_ids.length === 1 ? "1 ref" : `${note.linked_reference_ids.length} refs`;
                return (
                  <article
                    key={note.id}
                    className={`research-log-card${isSelected ? " selected" : ""}${isEditing ? " editing" : ""}${workflow.state === "Unprocessed" ? " research-log-card-unprocessed" : ""}`}
                  >
                    <div className="research-log-head">
                      <label className="research-log-select">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() =>
                            setSelectedInboxLogIds((current) => {
                              const next = new Set(current);
                              if (next.has(note.id)) next.delete(note.id);
                              else next.add(note.id);
                              return next;
                            })
                          }
                        />
                      </label>
                      {isEditing ? (
                        <>
                          {renderLanePills(inlineEditLane, setInlineEditLane, { className: "research-inline-lane-pills" })}
                        </>
                      ) : (
                        <div className="research-chip-group">
                          {note.lane ? <span className="chip small">{NOTE_LANE_LABELS[note.lane] || note.lane}</span> : null}
                          <span className="chip small">{workflow.state}</span>
                          {workflow.promotedToQuestion ? <span className="chip small">Question</span> : null}
                          {workflow.promotedToClaim ? <span className="chip small">Claim</span> : null}
                          {workflow.promotedToSection ? <span className="chip small">Section</span> : null}
                          {iterationState.assigned ? <span className="chip small">Iteration</span> : null}
                        </div>
                      )}
                      <span className="research-log-timestamp">{formatLogTimestamp(note.created_at)} · {formatRelativeTime(note.created_at)}</span>
                      <div className="research-log-controls">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              className="meetings-new-btn"
                              disabled={!inlineEditTitle.trim() || !inlineEditContent.trim() || saving}
                              onClick={() => void handleInlineEditSave(note.id)}
                            >
                              {saving ? "Saving..." : "Save"}
                            </button>
                            <button type="button" className="ghost icon-text-button small" onClick={cancelInlineEdit}>
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => startInlineEdit(note)}>
                              <FontAwesomeIcon icon={faPen} />
                            </button>
                            <button
                              type="button"
                              className={`ghost docs-action-btn${confirmingDeleteId === note.id ? " danger confirm-pulse" : ""}`}
                              title={confirmingDeleteId === note.id ? "Click again to confirm" : "Delete"}
                              onClick={() => requestConfirmDelete(note.id, () => handleDeleteNote(note.id))}
                            >
                              {confirmingDeleteId === note.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    {isEditing ? (
                      <div className="research-log-body">
                        <input
                          className="research-inline-title"
                          value={inlineEditTitle}
                          onChange={(event) => setInlineEditTitle(event.target.value)}
                          placeholder="Title"
                          autoFocus
                        />
                        <textarea
                          ref={inlineEditContentRef}
                          className="research-inline-content"
                          value={inlineEditContent}
                          onChange={(event) => {
                            const textarea = event.target;
                            handleContentChange(textarea.value, textarea.selectionStart, textarea, "inline");
                          }}
                          onKeyDown={(event) => {
                            handleMentionKeyDown(event);
                            if (mentionOpen) return;
                            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                              event.preventDefault();
                              void handleInlineEditSave(note.id);
                            }
                            if (event.key === "Escape") {
                              cancelInlineEdit();
                            }
                          }}
                          rows={4}
                          placeholder="Content (markdown, @ to cite)"
                        />
                      </div>
                    ) : (
                      <div className="research-log-body">
                        <strong>{note.title}</strong>
                        <div className="research-log-text chat-markdown">{renderMarkdown(note.content)}</div>
                      </div>
                    )}
                    <div className="research-log-footer">
                      <div className="research-log-meta">
                        <span>{note.author_name || "Unknown author"}</span>
                        <span>{linkedReferencesLabel}</span>
                        {iterationState.assigned && iterationState.iterationTitle ? <span>{iterationState.iterationTitle}</span> : null}
                      </div>
                      <div className="note-promote-actions">
                        <button type="button" className="ghost icon-text-button small" onClick={() => void handlePromoteNoteToClaim(note)}>
                          Claim
                        </button>
                        <button type="button" className="ghost icon-text-button small" onClick={() => void handlePromoteNoteToQuestion(note)}>
                          Question
                        </button>
                        <button type="button" className="ghost icon-text-button small" onClick={() => void handlePromoteNoteToSection(note)}>
                          Section
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        )}

        {mentionOpen && mentionAnchor ? (
          <div
            className="mention-dropdown"
            style={{ position: "fixed", top: mentionAnchor.top, left: mentionAnchor.left }}
          >
            {mentionResults.length === 0 ? (
              <div className="mention-empty">No references found</div>
            ) : (
              mentionResults.map((ref, index) => (
                <button
                  key={ref.id}
                  type="button"
                  className={`mention-item${index === mentionActiveIndex ? " active" : ""}`}
                  onMouseDown={(event) => { event.preventDefault(); selectMention(ref); }}
                  onMouseEnter={() => setMentionActiveIndex(index)}
                >
                  <span className="mention-item-title">{ref.title}</span>
                  <span className="mention-item-meta">
                    {ref.authors.length > 0 ? ref.authors[0] : ""}{ref.year ? ` · ${ref.year}` : ""}
                  </span>
                </button>
              ))
            )}
          </div>
        ) : null}
      </>
    );
  }

  function renderPaperTab() {
    if (!collectionDetail || !selectedCollectionId) {
      return <p className="empty-message">Select a study to manage its paper.</p>;
    }

    const collectionNotes = notes.filter((item) => item.collection_id === selectedCollectionId);
    const gapNotes = collectionNotes.filter((item) => item.lane === "gap");
    const collectionReferences = references.filter((item) => item.collection_id === selectedCollectionId);
    const collectionResults = studyResults;
    const availableAuthorMembers = collectionDetail.members.filter(
      (member) => !paperAuthors.some((author) => author.member_id === member.member_id)
    );
    const unprocessedInboxCount = collectionNotes.filter(
      (note) =>
        !paperQuestions.some((item) => item.note_ids.includes(note.id)) &&
        !paperClaims.some((item) => item.note_ids.includes(note.id)) &&
        !paperSections.some((item) => item.note_ids.includes(note.id))
    ).length;
    const unsupportedClaims = paperClaims.filter((item) => item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0).length;
    const weakSections = paperSections.filter((item) => item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0).length;
    const paperHasStructure =
      Boolean(paperMotivation.trim()) ||
      Boolean(paperTitle.trim()) ||
      paperAuthors.length > 0 ||
      paperQuestions.length > 0 ||
      paperClaims.length > 0 ||
      paperSections.length > 0 ||
      Boolean(paperSubmissionDeadline);
    const nextActions = [
      !paperSubmissionDeadline ? "Set submission deadline" : null,
      !paperMotivation.trim() && gapNotes.length > 0 ? "Draft motivation from gap logs" : null,
      paperAuthors.length === 0 ? "Add authors" : null,
      paperQuestions.length === 0 ? "Add a research question" : null,
      unprocessedInboxCount > 0 ? `Process ${unprocessedInboxCount} inbox item${unprocessedInboxCount !== 1 ? "s" : ""}` : null,
      unsupportedClaims > 0 ? `Support ${unsupportedClaims} claim${unsupportedClaims !== 1 ? "s" : ""}` : null,
      weakSections > 0 ? `Strengthen ${weakSections} section${weakSections !== 1 ? "s" : ""}` : null,
    ].filter(Boolean) as string[];

    return (
      <div className="paper-workspace">
        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Paper</strong>
            </div>
            <div className="research-header-actions">
              <button
                type="button"
                className="ghost icon-text-button small"
                disabled={draftingGapPaper || gapNotes.length === 0}
                onClick={() => void handleDraftPaperFromGap()}
              >
                <FontAwesomeIcon icon={faMagicWandSparkles} spin={draftingGapPaper} /> {draftingGapPaper ? "Drafting..." : "Draft From Gap"}
              </button>
              <button
                type="button"
                className="ghost icon-text-button small"
                disabled={buildingPaperOutline || (paperQuestions.length === 0 && paperClaims.length === 0 && collectionNotes.length === 0 && collectionReferences.length === 0)}
                onClick={() => void handleBuildPaperOutline()}
              >
                <FontAwesomeIcon icon={faMagicWandSparkles} spin={buildingPaperOutline} /> {buildingPaperOutline ? "Building..." : "Build Outline"}
              </button>
              <button type="button" className="ghost icon-text-button small" disabled={auditingPaperClaims || paperClaims.length === 0} onClick={() => void handleAuditPaperClaims()}>
                <FontAwesomeIcon icon={faMagicWandSparkles} spin={auditingPaperClaims} /> {auditingPaperClaims ? "Auditing..." : "Audit Claims"}
              </button>
              <button type="button" className="meetings-new-btn" disabled={saving} onClick={() => void handleSavePaperWorkspace()}>
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
          <div className="paper-health-row">
            <span className={`chip small${!paperSubmissionDeadline ? " paper-health-alert" : ""}`}>
              {paperSubmissionDeadline ? `Submission ${new Date(paperSubmissionDeadline).toLocaleDateString()}` : "No deadline"}
            </span>
            <span className="chip small">{paperAuthors.length} authors</span>
            <span className="chip small">{paperQuestions.length} questions</span>
            <span className="chip small">{gapNotes.length} gap logs</span>
            <span className={`chip small${unsupportedClaims > 0 ? " paper-health-alert" : ""}`}>
              {unsupportedClaims} unsupported claims
            </span>
            <span className={`chip small${weakSections > 0 ? " paper-health-alert" : ""}`}>
              {weakSections} weak sections
            </span>
            <span className={`chip small${unprocessedInboxCount > 0 ? " paper-health-alert" : ""}`}>
              {unprocessedInboxCount} inbox pending
            </span>
          </div>
          {nextActions.length > 0 ? (
            <div className="paper-next-actions">
              {nextActions.slice(0, 4).map((item) => (
                <span key={item} className="chip small">{item}</span>
              ))}
            </div>
          ) : null}
          <div className="paper-meta-grid">
            <label className="full-span">
              Motivation
              <textarea rows={4} value={paperMotivation} onChange={(event) => setPaperMotivation(event.target.value)} />
            </label>
            <label className="full-span">
              Paper Title
              <input value={paperTitle} onChange={(event) => setPaperTitle(event.target.value)} />
            </label>
            <label>
              Venue
              <input value={paperVenue} onChange={(event) => setPaperVenue(event.target.value)} />
            </label>
            <label>
              Status
              <select value={paperStatus} onChange={(event) => setPaperStatus(event.target.value)}>
                <option value="not_started">Not started</option>
                <option value="drafting">Drafting</option>
                <option value="internal_review">Internal review</option>
                <option value="submitted">Submitted</option>
                <option value="published">Published</option>
              </select>
            </label>
            <label>
              Registration Deadline
              <input type="date" value={paperRegistrationDeadline} onChange={(event) => setPaperRegistrationDeadline(event.target.value)} />
            </label>
            <label>
              Submission Deadline
              <input type="date" value={paperSubmissionDeadline} onChange={(event) => setPaperSubmissionDeadline(event.target.value)} />
            </label>
            <label>
              Decision Date
              <input type="date" value={paperDecisionDate} onChange={(event) => setPaperDecisionDate(event.target.value)} />
            </label>
            <label className="full-span">
              Overleaf
              <input value={paperOverleafUrl} onChange={(event) => setPaperOverleafUrl(event.target.value)} />
            </label>
          </div>
        </div>

        {!paperExpanded && !paperHasStructure ? (
          <div className="meetings-detail-section">
            <div className="paper-stack">
              <div className="paper-compact-grid">
                <label>
                  Main Question
                  <textarea
                    rows={3}
                    value={paperQuestions[0]?.text || ""}
                    onChange={(event) =>
                      setPaperQuestions((items) =>
                        items.length > 0
                          ? items.map((item, index) => (index === 0 ? { ...item, text: event.target.value } : item))
                          : [{ id: crypto.randomUUID(), text: event.target.value, note_ids: [] }]
                      )
                    }
                  />
                </label>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost icon-text-button small" onClick={() => void handleGeneratePaperFromStudy()}>
                  <FontAwesomeIcon icon={faMagicWandSparkles} /> Generate From Study
                </button>
                <button type="button" className="meetings-new-btn" onClick={() => setPaperExpanded(true)}>
                  Open Full Workspace
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {paperExpanded || paperHasStructure ? (
          <>

        <details className="research-inline-summary" open>
          <summary>Authors <span className="delivery-tab-count">{paperAuthors.length}</span></summary>
          <div className="paper-stack">
            <div className="paper-author-add-row">
              <select
                value=""
                onChange={(event) => {
                  const member = collectionDetail.members.find((entry) => entry.member_id === event.target.value);
                  if (!member) return;
                  setPaperAuthors((items) => [...items, newPaperAuthor(member)]);
                }}
              >
                <option value="">Add author</option>
                {availableAuthorMembers.map((member) => (
                  <option key={member.member_id} value={member.member_id}>
                    {member.member_name || "Member"}
                  </option>
                ))}
              </select>
            </div>
            {paperAuthors.length === 0 ? <p className="muted-small">No authors.</p> : null}
            {paperAuthors.map((author, index) => (
                <div key={author.id} className="paper-item-card paper-author-card">
                  <div className="paper-item-head">
                    <strong>
                      {index + 1}. {author.display_name}
                    </strong>
                  <div className="paper-author-actions">
                    <button
                      type="button"
                      className={`ghost paper-author-flag${author.is_corresponding ? " active" : ""}`}
                      onClick={() =>
                        setPaperAuthors((items) =>
                          items.map((entry) =>
                            entry.id === author.id ? { ...entry, is_corresponding: !entry.is_corresponding } : entry
                          )
                        )
                      }
                    >
                      Corresponding
                    </button>
                    <button
                      type="button"
                      className="ghost docs-action-btn"
                      title="Move up"
                      disabled={index === 0}
                      onClick={() =>
                        setPaperAuthors((items) => {
                          const next = [...items];
                          [next[index - 1], next[index]] = [next[index], next[index - 1]];
                          return next;
                        })
                      }
                    >
                      <FontAwesomeIcon icon={faChevronUp} />
                    </button>
                    <button
                      type="button"
                      className="ghost docs-action-btn"
                      title="Move down"
                      disabled={index === paperAuthors.length - 1}
                      onClick={() =>
                        setPaperAuthors((items) => {
                          const next = [...items];
                          [next[index], next[index + 1]] = [next[index + 1], next[index]];
                          return next;
                        })
                      }
                    >
                      <FontAwesomeIcon icon={faChevronDown} />
                    </button>
                    <button
                      type="button"
                      className="ghost docs-action-btn"
                      title="Remove"
                      onClick={() => setPaperAuthors((items) => items.filter((entry) => entry.id !== author.id))}
                    >
                      <FontAwesomeIcon icon={faXmark} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </details>

        <details className="research-inline-summary" open>
          <summary>Research Questions & Claims <span className="delivery-tab-count">{paperQuestions.length + paperClaims.length}</span></summary>
        <div className="paper-columns">
          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Research Questions</strong>
              </div>
              <button type="button" className="meetings-new-btn" onClick={() => setPaperQuestions((items) => [...items, newPaperQuestion()])}>
                <FontAwesomeIcon icon={faPlus} /> Add
              </button>
            </div>
            <div className="paper-stack">
              {paperQuestions.length === 0 ? <p className="muted-small">No questions.</p> : null}
              {paperQuestions.map((item, index) => (
                <div key={item.id} className="paper-item-card">
                  <div className="paper-item-head">
                    <strong>Question {index + 1}</strong>
                    <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => setPaperQuestions((items) => items.filter((entry) => entry.id !== item.id))}>
                      <FontAwesomeIcon icon={faXmark} />
                    </button>
                  </div>
                  <div className="paper-evidence-strip">
                    <span className="chip small">{item.note_ids.length} notes</span>
                  </div>
                  <textarea
                    rows={3}
                    value={item.text}
                    onChange={(event) =>
                      setPaperQuestions((items) => items.map((entry) => (entry.id === item.id ? { ...entry, text: event.target.value } : entry)))
                    }
                  />
                  <div className="paper-link-block">
                    <strong>Notes</strong>
                    <div className="paper-link-group">
                      {collectionNotes.map((note) => (
                        <label key={`${item.id}-question-note-${note.id}`} className="paper-link-chip">
                          <input
                            type="checkbox"
                            checked={item.note_ids.includes(note.id)}
                            onChange={() =>
                              setPaperQuestions((items) =>
                                items.map((entry) =>
                                  entry.id === item.id ? { ...entry, note_ids: toggleId(entry.note_ids, note.id) } : entry
                                )
                              )
                            }
                          />
                          <span>{note.title || "Note"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Claims</strong>
              </div>
              <button type="button" className="meetings-new-btn" onClick={() => setPaperClaims((items) => [...items, newPaperClaim()])}>
                <FontAwesomeIcon icon={faPlus} /> Add
              </button>
            </div>
            <div className="paper-stack">
              {paperClaims.length === 0 ? <p className="muted-small">No claims.</p> : null}
              {paperClaims.map((item, index) => (
                <div key={item.id} className={`paper-item-card${item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? " paper-item-card-alert" : ""}`}>
                  <div className="paper-item-head">
                    <strong>Claim {index + 1}</strong>
                    <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => setPaperClaims((items) => items.filter((entry) => entry.id !== item.id))}>
                      <FontAwesomeIcon icon={faXmark} />
                    </button>
                  </div>
                  <div className="paper-evidence-strip">
                    <span className="chip small">{item.question_ids.length} questions</span>
                    <span className="chip small">{item.reference_ids.length} references</span>
                    <span className="chip small">{item.note_ids.length} notes</span>
                    <span className="chip small">{item.result_ids.length} results</span>
                    {item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? (
                      <span className="chip small paper-health-alert">Missing evidence</span>
                    ) : null}
                    {item.audit_status ? (
                      <span className={`chip small paper-audit-status paper-audit-status-${item.audit_status}`}>{item.audit_status.replace(/_/g, " ")}</span>
                    ) : null}
                  </div>
                  {item.audit_summary ? (
                    <div className="paper-audit-box">
                      <p>{item.audit_summary}</p>
                      <div className="paper-audit-meta">
                        {item.supporting_reference_ids.length ? <span className="muted-small">{item.supporting_reference_ids.length} supporting references</span> : null}
                        {item.supporting_note_ids.length ? <span className="muted-small">{item.supporting_note_ids.length} supporting notes</span> : null}
                        {item.audit_confidence !== null ? <span className="muted-small">{Math.round(item.audit_confidence * 100)}% confidence</span> : null}
                        {item.audited_at ? <span className="muted-small">{formatRelativeTime(item.audited_at)}</span> : null}
                      </div>
                      {item.missing_evidence.length > 0 ? (
                        <div className="research-chip-group">
                          {item.missing_evidence.map((entry) => (
                            <span key={`${item.id}-${entry}`} className="chip small paper-health-alert">{entry}</span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <textarea
                    rows={3}
                    value={item.text}
                    onChange={(event) =>
                      setPaperClaims((items) => items.map((entry) => (entry.id === item.id ? { ...entry, text: event.target.value } : entry)))
                    }
                  />
                  <label>
                    Status
                    <select
                      value={item.status}
                      onChange={(event) =>
                        setPaperClaims((items) => items.map((entry) => (entry.id === item.id ? { ...entry, status: event.target.value } : entry)))
                      }
                    >
                      <option value="draft">Draft</option>
                      <option value="supported">Supported</option>
                      <option value="missing_evidence">Missing evidence</option>
                    </select>
                  </label>
                  <div className="paper-link-group">
                    {paperQuestions.map((question) => (
                      <label key={`${item.id}-${question.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.question_ids.includes(question.id)}
                          onChange={() =>
                            setPaperClaims((items) =>
                              items.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, question_ids: toggleId(entry.question_ids, question.id) }
                                  : entry
                              )
                            )
                          }
                        />
                        <span>{question.text || "Question"}</span>
                      </label>
                    ))}
                  </div>
                  <div className="paper-link-block">
                    <strong>References</strong>
                    <div className="paper-link-group">
                      {collectionReferences.map((reference) => (
                        <label key={`${item.id}-ref-${reference.id}`} className="paper-link-chip">
                          <input
                            type="checkbox"
                            checked={item.reference_ids.includes(reference.id)}
                            onChange={() =>
                              setPaperClaims((items) =>
                                items.map((entry) =>
                                  entry.id === item.id
                                    ? { ...entry, reference_ids: toggleId(entry.reference_ids, reference.id) }
                                    : entry
                                )
                              )
                            }
                          />
                          <span>{reference.title || "Reference"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Notes</strong>
                    <div className="paper-link-group">
                      {collectionNotes.map((note) => (
                        <label key={`${item.id}-note-${note.id}`} className="paper-link-chip">
                          <input
                            type="checkbox"
                            checked={item.note_ids.includes(note.id)}
                            onChange={() =>
                              setPaperClaims((items) =>
                                items.map((entry) =>
                                  entry.id === item.id
                                    ? { ...entry, note_ids: toggleId(entry.note_ids, note.id) }
                                    : entry
                                )
                              )
                            }
                        />
                          <span>{note.title || "Note"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Results</strong>
                    <div className="paper-link-group">
                      {collectionResults.map((result) => (
                        <label key={`${item.id}-result-${result.id}`} className="paper-link-chip">
                          <input
                            type="checkbox"
                            checked={item.result_ids.includes(result.id)}
                            onChange={() =>
                              setPaperClaims((items) =>
                                items.map((entry) =>
                                  entry.id === item.id
                                    ? { ...entry, result_ids: toggleId(entry.result_ids, result.id) }
                                    : entry
                                )
                              )
                            }
                          />
                          <span>{result.title || "Result"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        </details>

        <details className="research-inline-summary" open>
          <summary>Sections <span className="delivery-tab-count">{paperSections.length}</span></summary>
          <div className="paper-section-action-row">
            <button type="button" className="meetings-new-btn" onClick={() => setPaperSections((items) => [...items, newPaperSection()])}>
              <FontAwesomeIcon icon={faPlus} /> Add Section
            </button>
          </div>
          <div className="paper-stack">
            {paperSections.length === 0 ? <p className="muted-small">No sections.</p> : null}
              {paperSections.map((item, index) => (
              <div
                key={item.id}
                className={`paper-item-card${item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? " paper-item-card-alert" : ""}`}
              >
                <div className="paper-item-head">
                  <strong>Section {index + 1}</strong>
                  <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => setPaperSections((items) => items.filter((entry) => entry.id !== item.id))}>
                    <FontAwesomeIcon icon={faXmark} />
                  </button>
                </div>
                <div className="paper-evidence-strip">
                  <span className="chip small">{item.question_ids.length} questions</span>
                  <span className="chip small">{item.claim_ids.length} claims</span>
                  <span className="chip small">{item.reference_ids.length} references</span>
                  <span className="chip small">{item.note_ids.length} notes</span>
                  <span className="chip small">{item.result_ids.length} results</span>
                  {item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? (
                    <span className="chip small paper-health-alert">Weak section</span>
                  ) : null}
                </div>
                <div className="paper-section-grid">
                  <label>
                    Title
                    <input
                      value={item.title}
                      onChange={(event) =>
                        setPaperSections((items) => items.map((entry) => (entry.id === item.id ? { ...entry, title: event.target.value } : entry)))
                      }
                    />
                  </label>
                  <label>
                    Status
                    <select
                      value={item.status}
                      onChange={(event) =>
                        setPaperSections((items) => items.map((entry) => (entry.id === item.id ? { ...entry, status: event.target.value } : entry)))
                      }
                    >
                      <option value="not_started">Not started</option>
                      <option value="drafting">Drafting</option>
                      <option value="ready">Ready</option>
                    </select>
                  </label>
                </div>
                <div className="paper-link-block">
                  <strong>Questions</strong>
                  <div className="paper-link-group">
                    {paperQuestions.map((question) => (
                      <label key={`${item.id}-q-${question.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.question_ids.includes(question.id)}
                          onChange={() =>
                            setPaperSections((items) =>
                              items.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, question_ids: toggleId(entry.question_ids, question.id) }
                                  : entry
                              )
                            )
                          }
                        />
                        <span>{question.text || "Question"}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="paper-link-block">
                  <strong>Claims</strong>
                  <div className="paper-link-group">
                    {paperClaims.map((claim) => (
                      <label key={`${item.id}-c-${claim.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.claim_ids.includes(claim.id)}
                          onChange={() =>
                            setPaperSections((items) =>
                              items.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, claim_ids: toggleId(entry.claim_ids, claim.id) }
                                  : entry
                              )
                            )
                          }
                        />
                        <span>{claim.text || "Claim"}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="paper-link-block">
                  <strong>References</strong>
                  <div className="paper-link-group">
                    {collectionReferences.map((reference) => (
                      <label key={`${item.id}-section-ref-${reference.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.reference_ids.includes(reference.id)}
                          onChange={() =>
                            setPaperSections((items) =>
                              items.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, reference_ids: toggleId(entry.reference_ids, reference.id) }
                                  : entry
                              )
                            )
                          }
                        />
                        <span>{reference.title || "Reference"}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="paper-link-block">
                  <strong>Notes</strong>
                  <div className="paper-link-group">
                    {collectionNotes.map((note) => (
                      <label key={`${item.id}-section-note-${note.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.note_ids.includes(note.id)}
                          onChange={() =>
                            setPaperSections((items) =>
                              items.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, note_ids: toggleId(entry.note_ids, note.id) }
                                  : entry
                              )
                            )
                          }
                        />
                        <span>{note.title || "Note"}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="paper-link-block">
                  <strong>Results</strong>
                  <div className="paper-link-group">
                    {collectionResults.map((result) => (
                      <label key={`${item.id}-section-result-${result.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.result_ids.includes(result.id)}
                          onChange={() =>
                            setPaperSections((items) =>
                              items.map((entry) =>
                                entry.id === item.id
                                  ? { ...entry, result_ids: toggleId(entry.result_ids, result.id) }
                                  : entry
                              )
                            )
                          }
                        />
                        <span>{result.title || "Result"}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </details>
          </>
        ) : null}
      </div>
    );
  }

  function renderIterationsTab() {
    if (!collectionDetail || !selectedCollectionId) {
      return <p className="empty-message">Select a study to manage its iterations.</p>;
    }

    const collectionNotes = notes.filter((item) => item.collection_id === selectedCollectionId);
    const orderedResults = sortedStudyResults();

    return (
      <div className="paper-workspace">
        {orderedResults.length > 0 ? (
          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Results</strong>
              </div>
              <div className="research-header-actions">
                <button
                  type="button"
                  className="ghost icon-text-button small"
                  disabled={comparingResults || orderedResults.length < 2}
                  onClick={() => void handleCompareResults()}
                >
                  <FontAwesomeIcon icon={faMagicWandSparkles} spin={comparingResults} /> {comparingResults ? "Comparing..." : "Compare Results"}
                </button>
              </div>
            </div>
            <div className="paper-stack">
              {resultComparison ? (
                <div className="paper-item-card">
                  <div className="paper-item-head">
                    <strong>Comparison</strong>
                    <span className="chip small">{resultComparison.compared_result_ids.length} results</span>
                  </div>
                  <p>{resultComparison.summary || "No comparison summary."}</p>
                  <div className="paper-columns">
                    <div className="paper-link-block">
                      <strong>Likely Improvements</strong>
                      <div className="research-bullet-stack">
                        {resultComparison.likely_improvements.length === 0 ? <span className="muted-small">None</span> : null}
                        {resultComparison.likely_improvements.map((entry) => (
                          <span key={`comparison-improvement-${entry}`} className="chip small">{entry}</span>
                        ))}
                      </div>
                    </div>
                    <div className="paper-link-block">
                      <strong>Likely Regressions</strong>
                      <div className="research-bullet-stack">
                        {resultComparison.likely_regressions.length === 0 ? <span className="muted-small">None</span> : null}
                        {resultComparison.likely_regressions.map((entry) => (
                          <span key={`comparison-regression-${entry}`} className="chip small">{entry}</span>
                        ))}
                      </div>
                    </div>
                    <div className="paper-link-block">
                      <strong>Likely Causes</strong>
                      <div className="research-bullet-stack">
                        {resultComparison.likely_causes.length === 0 ? <span className="muted-small">None</span> : null}
                        {resultComparison.likely_causes.map((entry) => (
                          <span key={`comparison-cause-${entry}`} className="chip small">{entry}</span>
                        ))}
                      </div>
                    </div>
                    <div className="paper-link-block">
                      <strong>Next Experiment Changes</strong>
                      <div className="research-bullet-stack">
                        {resultComparison.next_experiment_changes.length === 0 ? <span className="muted-small">None</span> : null}
                        {resultComparison.next_experiment_changes.map((entry) => (
                          <span key={`comparison-next-${entry}`} className="chip small">{entry}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
              {orderedResults.map((result) => {
                const previous = previousStudyResult(result.id);
                const delta = resultDeltaLabel(result, previous);
                return (
                  <div key={result.id} className="paper-item-card">
                    <div className="paper-item-head">
                      <strong>{result.title}</strong>
                      <span className="chip small">{result.updated_at ? formatRelativeTime(result.updated_at) : "Result"}</span>
                    </div>
                    <div className="paper-evidence-strip">
                      <span className="chip small">{result.note_ids.length} logs</span>
                      <span className="chip small">{result.reference_ids.length} references</span>
                      {result.improvements.length ? <span className="chip small">{result.improvements.length} improvements</span> : null}
                      {result.regressions.length ? <span className="chip small">{result.regressions.length} regressions</span> : null}
                    </div>
                    <p>{result.summary || "No summary."}</p>
                    {delta ? <span className="muted-small">{delta}</span> : null}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
        {studyIterations.length === 0 ? (
          <div className="meetings-detail-section">
            <div className="paper-stack">
              <p className="empty-message">No iterations yet.</p>
            </div>
          </div>
        ) : null}
        {studyIterations.map((iteration, index) => (
          <div key={iteration.id} className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>{iteration.title || `Iteration ${index + 1}`}</strong>
              </div>
              <div className="research-header-actions">
                <span className="chip small">
                  {iteration.start_date || "?"} {iteration.end_date ? `- ${iteration.end_date}` : ""}
                </span>
                <span className="chip small">{iteration.note_ids.length} logs</span>
                <span className="chip small">{iterationResults(iteration.id).length} results</span>
                <button
                  type="button"
                  className="ghost icon-text-button small"
                  disabled={reviewingIterationId === iteration.id}
                  onClick={() => void handleReviewIteration(iteration.id)}
                >
                  <FontAwesomeIcon icon={faMagicWandSparkles} spin={reviewingIterationId === iteration.id} /> {reviewingIterationId === iteration.id ? "Reviewing..." : "Review"}
                </button>
                <button
                  type="button"
                  className="ghost icon-text-button small"
                  disabled={!iteration.summary}
                  onClick={() => void handleCreateResultFromIteration(iteration.id)}
                >
                  <FontAwesomeIcon icon={faPlus} /> {iterationResults(iteration.id).length > 0 ? "Update Result" : "Create Result"}
                </button>
                <button
                  type="button"
                  className="ghost icon-text-button small"
                  onClick={() => setExpandedIterationId((current) => (current === iteration.id ? null : iteration.id))}
                >
                  {expandedIterationId === iteration.id ? "Close" : "Open"}
                </button>
                <button
                  type="button"
                  className="ghost docs-action-btn"
                  title="Remove"
                  onClick={() => setStudyIterations((items) => items.filter((entry) => entry.id !== iteration.id))}
                >
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>
            <div className="paper-stack">
              <div className="paper-evidence-strip">
                {iteration.reviewed_at ? <span className="chip small">Reviewed</span> : <span className="chip small paper-health-alert">Review pending</span>}
                {iteration.improvements.length ? <span className="chip small">{iteration.improvements.length} improvements</span> : null}
                {iteration.regressions.length ? <span className="chip small">{iteration.regressions.length} regressions</span> : null}
                {iteration.next_actions.length ? <span className="chip small">{iteration.next_actions.length} next actions</span> : null}
              </div>
              <p>{iteration.summary || "No review yet."}</p>
            </div>
            {expandedIterationId === iteration.id ? (
              <div className="paper-stack">
                <div className="paper-section-grid">
                  <label>
                    Title
                    <input
                      value={iteration.title}
                      onChange={(event) =>
                        setStudyIterations((items) =>
                          items.map((entry) => (entry.id === iteration.id ? { ...entry, title: event.target.value } : entry))
                        )
                      }
                    />
                  </label>
                  <label>
                    Start
                    <input
                      type="date"
                      value={iteration.start_date || ""}
                      onChange={(event) =>
                        setStudyIterations((items) =>
                          items.map((entry) => (entry.id === iteration.id ? { ...entry, start_date: event.target.value || null } : entry))
                        )
                      }
                    />
                  </label>
                  <label>
                    End
                    <input
                      type="date"
                      value={iteration.end_date || ""}
                      onChange={(event) =>
                        setStudyIterations((items) =>
                          items.map((entry) => (entry.id === iteration.id ? { ...entry, end_date: event.target.value || null } : entry))
                        )
                      }
                    />
                  </label>
                </div>
                <div className="paper-link-block">
                  <strong>Logs</strong>
                  <div className="research-bullet-stack">
                    {collectionNotes
                      .filter((note) => iteration.note_ids.includes(note.id))
                      .map((note) => (
                        <span key={`${iteration.id}-log-${note.id}`} className="chip small">
                          {note.title || "Log"}
                        </span>
                      ))}
                  </div>
                </div>
                {iteration.what_changed.length > 0 ? (
                  <div className="paper-link-block">
                    <strong>What Changed</strong>
                    <div className="research-bullet-stack">
                      {iteration.what_changed.map((entry) => (
                        <span key={`${iteration.id}-changed-${entry}`} className="chip small">{entry}</span>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="paper-columns">
                  <div className="paper-link-block">
                    <strong>Improvements</strong>
                    <div className="research-bullet-stack">
                      {iteration.improvements.length === 0 ? <span className="muted-small">None</span> : null}
                      {iteration.improvements.map((entry) => (
                        <span key={`${iteration.id}-improvement-${entry}`} className="chip small">{entry}</span>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Regressions</strong>
                    <div className="research-bullet-stack">
                      {iteration.regressions.length === 0 ? <span className="muted-small">None</span> : null}
                      {iteration.regressions.map((entry) => (
                        <span key={`${iteration.id}-regression-${entry}`} className="chip small">{entry}</span>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Unclear</strong>
                    <div className="research-bullet-stack">
                      {iteration.unclear_points.length === 0 ? <span className="muted-small">None</span> : null}
                      {iteration.unclear_points.map((entry) => (
                        <span key={`${iteration.id}-unclear-${entry}`} className="chip small">{entry}</span>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Next Actions</strong>
                    <div className="research-bullet-stack">
                      {iteration.next_actions.length === 0 ? <span className="muted-small">None</span> : null}
                      {iteration.next_actions.map((entry) => (
                        <span key={`${iteration.id}-next-${entry}`} className="chip small">{entry}</span>
                      ))}
                    </div>
                  </div>
                </div>
                <label>
                  Comments
                  <textarea
                    rows={4}
                    value={iteration.user_comments || ""}
                    onChange={(event) =>
                      setStudyIterations((items) =>
                        items.map((entry) => (entry.id === iteration.id ? { ...entry, user_comments: event.target.value || null } : entry))
                      )
                    }
                  />
                </label>
                {iterationResults(iteration.id).length > 0 ? (
                  <div className="paper-link-block">
                    <strong>Results</strong>
                    <div className="paper-stack">
                      {iterationResults(iteration.id).map((result) => (
                        <div key={result.id} className="paper-item-card">
                          <div className="paper-item-head">
                            <strong>{result.title}</strong>
                            <span className="chip small">{result.updated_at ? formatRelativeTime(result.updated_at) : "Result"}</span>
                          </div>
                          <div className="paper-evidence-strip">
                            <span className="chip small">{result.note_ids.length} logs</span>
                            <span className="chip small">{result.reference_ids.length} references</span>
                            {result.improvements.length ? <span className="chip small">{result.improvements.length} improvements</span> : null}
                            {result.regressions.length ? <span className="chip small">{result.regressions.length} regressions</span> : null}
                          </div>
                          <p>{result.summary || "No summary."}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="row-actions">
                  <button
                    type="button"
                    className="meetings-new-btn"
                    onClick={() => void persistPaperWorkspace({ study_iterations: studyIterations, study_results: studyResults }, { successMessage: "Iteration updated." })}
                  >
                    Save
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  function renderOverviewTab() {
    if (!collectionDetail || !selectedCollectionId) {
      return <p className="empty-message">Select a study to manage it.</p>;
    }

    const synthesis = parseSynthesisPayload(collectionDetail.ai_synthesis);
    const collectionNotes = notes.filter((item) => item.collection_id === selectedCollectionId);
    const recentNotes = [...collectionNotes].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 4);
    const recentReferences = [...references].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 4);
    const recentResults = sortedStudyResults().slice(0, 4);
    const unprocessedInboxCount = collectionNotes.filter(
      (note) =>
        !paperQuestions.some((item) => item.note_ids.includes(note.id)) &&
        !paperClaims.some((item) => item.note_ids.includes(note.id)) &&
        !paperSections.some((item) => item.note_ids.includes(note.id))
    ).length;
    const unsupportedClaims = paperClaims.filter((item) => item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0).length;
    const weakSections = paperSections.filter((item) => item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0).length;
    const nextActions = [
      !paperSubmissionDeadline ? "Set the paper submission deadline." : null,
      unprocessedInboxCount > 0 ? `Process ${unprocessedInboxCount} inbox item${unprocessedInboxCount !== 1 ? "s" : ""}.` : null,
      studyResults.length === 0 ? "Create the first result from an iteration review." : null,
      unsupportedClaims > 0 ? `Add evidence for ${unsupportedClaims} unsupported claim${unsupportedClaims !== 1 ? "s" : ""}.` : null,
      weakSections > 0 ? `Strengthen ${weakSections} weak section${weakSections !== 1 ? "s" : ""}.` : null,
      references.length === 0 ? "Import the first references from Bibliography." : null,
    ].filter(Boolean) as string[];

    return (
      <div className="research-overview">
        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Dashboard</strong>
            </div>
          </div>
          <div className="research-overview-body">
            <div className="research-meta-grid">
              <span className="muted-small">{paperSubmissionDeadline ? `Deadline: ${new Date(paperSubmissionDeadline).toLocaleDateString()}` : "No deadline set"}</span>
              <span className="muted-small">{references.length} references</span>
              <span className="muted-small">{collectionNotes.length} inbox</span>
              <span className="muted-small">{studyResults.length} results</span>
              <span className="muted-small">{paperClaims.length} claims</span>
              <span className="muted-small">{paperSections.length} sections</span>
            </div>
            {nextActions.length > 0 ? (
              <div className="research-bullet-stack">
                {nextActions.map((item) => (
                  <span key={item} className={`chip small${item.includes("unsupported") || item.includes("weak") || item.includes("deadline") ? " paper-health-alert" : ""}`}>{item}</span>
                ))}
              </div>
            ) : (
              <p className="muted-small">Study is in a good state.</p>
            )}
          </div>
        </div>

        <div className="meetings-detail-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Study</strong>
            </div>
            <button type="button" className="meetings-new-btn" onClick={openEditCollectionModal}>
              <FontAwesomeIcon icon={faPen} /> Edit
            </button>
          </div>
          <div className="research-overview-body">
            {collectionDetail.description ? <p>{collectionDetail.description}</p> : null}
            {collectionDetail.hypothesis ? (
              <p className="muted-small"><strong>Hypothesis:</strong> {collectionDetail.hypothesis}</p>
            ) : null}
            {!collectionDetail.description && !collectionDetail.hypothesis ? <p className="muted-small">No description or hypothesis set.</p> : null}
            <div className="research-meta-grid">
              <span className="muted-small">Status: <span className="chip small">{collectionDetail.status}</span></span>
            </div>
          </div>
        </div>

        <div className="paper-columns">
          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Recent Results</strong>
              </div>
            </div>
            <div className="paper-stack">
              {recentResults.length === 0 ? <p className="muted-small">No results.</p> : null}
              {recentResults.map((result) => (
                <div key={result.id} className="paper-item-card">
                  <strong>{result.title}</strong>
                  <span className="muted-small">{result.summary || "No summary."}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Recent References</strong>
              </div>
            </div>
            <div className="paper-stack">
              {recentReferences.length === 0 ? <p className="muted-small">No references.</p> : null}
              {recentReferences.map((reference) => (
                <div key={reference.id} className="paper-item-card">
                  <strong>{reference.title}</strong>
                  <span className="muted-small">{reference.authors.join(", ") || "-"}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Recent Inbox</strong>
              </div>
            </div>
            <div className="paper-stack">
              {recentNotes.length === 0 ? <p className="muted-small">No inbox items.</p> : null}
              {recentNotes.map((note) => (
                <div key={note.id} className="paper-item-card">
                  <strong>{note.title}</strong>
                  <span className="muted-small">{formatRelativeTime(note.created_at)}</span>
                </div>
              ))}
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
                    <span className="chip-type-label">WP</span> {item.code}
                  </span>
                ) : null;
              })}
              {collectionDetail.task_ids.map((id) => {
                const item = tasks.find((entry) => entry.id === id);
                return item ? (
                  <span key={id} className="chip small">
                    <span className="chip-type-label">Task</span> {item.code}
                  </span>
                ) : null;
              })}
              {collectionDetail.deliverable_ids.map((id) => {
                const item = deliverables.find((entry) => entry.id === id);
                return item ? (
                  <span key={id} className="chip small">
                    <span className="chip-type-label">Del</span> {item.code}
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
                  <span className="muted-small">Generated {formatRelativeTime(collectionDetail.ai_synthesis_at)}</span>
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

  function renderBibliographyPreviewModal() {
    if (!bibliographyPreview) return null;
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={closeBibliographyPreview}>
        <div className="modal-card bib-preview-modal" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{bibliographyPreview.title}</h3>
            <div className="modal-head-actions">
              <a className="ghost icon-text-button small" href={bibliographyPreview.url} target="_blank" rel="noreferrer">
                Open
              </a>
              <button type="button" className="ghost docs-action-btn" onClick={closeBibliographyPreview} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>
          <div className="bib-preview-shell">
            <div className="bib-preview-meta">
              <span className="chip small">PDF</span>
              <span className="muted-small">{bibliographyPreview.filename}</span>
            </div>
            <iframe className="bib-preview-frame" src={bibliographyPreview.url} title={bibliographyPreview.title} />
          </div>
        </div>
      </div>
    );
  }

  function renderBibliographyDuplicateModal() {
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setBibliographyDuplicateModalOpen(false)}>
        <div className="modal-card settings-modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>Duplicates</h3>
            <div className="modal-head-actions">
              <button type="button" className="meetings-new-btn" disabled={saving} onClick={() => void persistBibliography({ allowDuplicate: true })}>
                {saving ? "Saving..." : "Create Anyway"}
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={() => setBibliographyDuplicateModalOpen(false)} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>
          <div className="bib-duplicate-list">
            {bibliographyDuplicateMatches.map((match) => (
              <div key={`${match.reference.id}-${match.match_reason}`} className="bib-duplicate-card">
                <div className="bib-duplicate-main">
                  <div className="research-chip-group">
                    <span className="chip small">{match.match_reason === "doi" ? "DOI" : "Title"}</span>
                    <span className="chip small">{match.reference.visibility}</span>
                  </div>
                  <strong>{match.reference.title}</strong>
                  <span className="muted-small">{match.reference.authors.join(", ") || "-"}</span>
                  {(match.reference.venue || match.reference.year) ? (
                    <span className="muted-small">{[match.reference.venue, match.reference.year].filter(Boolean).join(" · ")}</span>
                  ) : null}
                  <div className="research-chip-group">
                    <span className="chip small">{match.reference.linked_project_count} linked</span>
                    {match.reference.attachment_url ? <span className="chip small">PDF</span> : null}
                    {match.reference.tags.map((tag) => (
                      <span key={`${match.reference.id}-${tag}`} className="chip small">{tag}</span>
                    ))}
                  </div>
                </div>
                <div className="bib-duplicate-actions">
                  {match.reference.attachment_url ? (
                    <button type="button" className="ghost icon-text-button small" onClick={() => void handleOpenBibliographyAttachment(match.reference)}>
                      PDF
                    </button>
                  ) : null}
                  <button type="button" className="meetings-new-btn" disabled={saving} onClick={() => void persistBibliography({ reuseExistingId: match.reference.id })}>
                    Use Existing
                  </button>
                </div>
              </div>
            ))}
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
            <h3>{collectionModalMode === "create" ? "New Study" : "Edit Study"}</h3>
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
              Focus
              <textarea value={collectionDescription} onChange={(event) => setCollectionDescription(event.target.value)} rows={4} />
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
              {saving ? "Saving..." : collectionModalMode === "create" ? "Create Study" : "Save"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderBibliographyCollectionModal() {
    const isCreate = bibliographyCollectionModalMode === "create";
    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setBibliographyCollectionModalOpen(false)}>
        <div className="modal-card" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{isCreate ? "Collection" : "Edit Collection"}</h3>
            <div className="modal-head-actions">
              <button type="button" disabled={!bibliographyCollectionTitle.trim() || saving} onClick={() => void handleSaveBibliographyCollection()}>
                {saving ? "Saving..." : isCreate ? "Add" : "Save"}
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={() => setBibliographyCollectionModalOpen(false)} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>
          <div className="form-grid">
            <label className="full-span">
              Title
              <input value={bibliographyCollectionTitle} onChange={(event) => setBibliographyCollectionTitle(event.target.value)} />
            </label>
            <label>
              Visibility
              <select value={bibliographyCollectionVisibility} onChange={(event) => setBibliographyCollectionVisibility(event.target.value)}>
                <option value="private">Private</option>
                <option value="shared">Shared</option>
              </select>
            </label>
            <label className="full-span">
              Description
              <textarea rows={4} value={bibliographyCollectionDescription} onChange={(event) => setBibliographyCollectionDescription(event.target.value)} />
            </label>
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
    const isCreate = bibliographyModalMode === "create";
    const isBatchMode = isCreate && bibliographyCreateTab === "batch";
    const isBibtexMode = isCreate && bibliographyCreateTab === "manual" && bibliographyBibtexInput.trim();
    const canSave = isBatchMode ? bibliographyIdentifierInput.trim() : (isBibtexMode || bibliographyTitle.trim());
    const editingBibliography = editingBibliographyId ? bibliography.find((item) => item.id === editingBibliographyId) ?? null : null;
    const canExtractAbstract = !isCreate && !bibliographyAbstract.trim() && !!editingBibliography && editingBibliography.document_status !== "no_pdf";
    const canExtractConcepts = !isCreate && !!editingBibliography && !!bibliographyAbstract.trim();

    return (
      <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setBibliographyModalOpen(false)}>
        <div className="modal-card settings-modal-card bib-modal" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{isCreate ? "Add Paper" : "Edit Paper"}</h3>
            <div className="modal-head-actions">
              <div className="bib-toggle-group">
                <button type="button" className={`bib-toggle-group-btn${bibliographyVisibility === "shared" ? " active" : ""}`} onClick={() => setBibliographyVisibility("shared")}>Shared</button>
                <button type="button" className={`bib-toggle-group-btn${bibliographyVisibility === "private" ? " active" : ""}`} onClick={() => setBibliographyVisibility("private")}>Private</button>
              </div>
              {!isCreate && editingBibliography ? (
                <button type="button" className="ghost docs-action-btn" title="Copy link" onClick={() => void handleCopyBibliographyPermalink(editingBibliography)}>
                  <FontAwesomeIcon icon={faLink} />
                </button>
              ) : null}
              <button
                type="button"
                className="meetings-new-btn"
                disabled={!canSave || saving}
                onClick={() => void (isBatchMode ? handleImportBibliographyIdentifiers() : (isBibtexMode ? handleImportBibliographyBibtex() : handleSaveBibliography()))}
              >
                {saving ? (isBatchMode || isBibtexMode ? "Importing..." : "Saving...") : isCreate ? (isBatchMode || isBibtexMode ? "Import" : "Add") : "Save"}
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={() => setBibliographyModalOpen(false)} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>

          <div className="bib-modal-body">
            {isCreate ? (
              <div className="delivery-tabs bib-modal-tabs">
                <button className={`delivery-tab ${bibliographyCreateTab === "manual" ? "active" : ""}`} onClick={() => setBibliographyCreateTab("manual")}>
                  Manual
                </button>
                <button className={`delivery-tab ${bibliographyCreateTab === "batch" ? "active" : ""}`} onClick={() => setBibliographyCreateTab("batch")}>
                  Batch
                </button>
              </div>
            ) : null}

            {isBatchMode ? (
              <div className="bib-section">
                <textarea
                  className="bib-bibtex-area bib-batch-area"
                  value={bibliographyIdentifierInput}
                  onChange={(event) => setBibliographyIdentifierInput(event.target.value)}
                  rows={12}
                  placeholder={"10.48550/arXiv.2401.00001\nhttps://doi.org/10.1038/...\n2401.00001\nhttps://arxiv.org/abs/2401.00001"}
                  autoFocus
                />
                {bibliographyIdentifierResult ? (
                  <div className="research-bibtex-result">
                    {bibliographyIdentifierResult.created > 0 ? <span className="chip small">{bibliographyIdentifierResult.created} created</span> : null}
                    {bibliographyIdentifierResult.reused > 0 ? <span className="chip small">{bibliographyIdentifierResult.reused} reused</span> : null}
                    {bibliographyIdentifierResult.errors.map((item, index) => (
                      <span key={`${item}-${index}`} className="chip small research-bibtex-error">{item}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
            <>
            {isCreate ? (
              <div className="bib-section">
                <div className="bib-section-head">
                  <FontAwesomeIcon icon={faFileImport} />
                  <span>Quick Import</span>
                </div>
                <textarea
                  className="bib-bibtex-area"
                  value={bibliographyBibtexInput}
                  onChange={(event) => setBibliographyBibtexInput(event.target.value)}
                  rows={3}
                  placeholder={"@article{key,\n  title = {…},\n  author = {…},\n  year = {…}\n}"}
                  autoFocus
                />
                {bibliographyBibtexResult ? (
                  <div className="research-bibtex-result">
                    {bibliographyBibtexResult.created > 0 ? <span className="chip small">{bibliographyBibtexResult.created} imported</span> : null}
                    {bibliographyBibtexResult.errors.map((item, index) => (
                      <span key={`${item}-${index}`} className="chip small research-bibtex-error">{item}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="bib-modal-columns">
              {/* Left: metadata, tags, PDF */}
              <div className="bib-modal-col">
                <div className="form-grid">
                  <label className="full-span">
                    Title
                    <input value={bibliographyTitle} onChange={(event) => setBibliographyTitle(event.target.value)} autoFocus={!isCreate} placeholder="Full paper title" />
                  </label>
                  <label className="full-span">
                    Authors
                    <input value={bibliographyAuthors} onChange={(event) => setBibliographyAuthors(event.target.value)} placeholder="Last, First; Last, First" />
                  </label>
                  <label>
                    Year
                    <input type="number" value={bibliographyYear} onChange={(event) => setBibliographyYear(event.target.value)} placeholder="2024" />
                  </label>
                  <label>
                    Venue
                    <input value={bibliographyVenue} onChange={(event) => setBibliographyVenue(event.target.value)} placeholder="Journal or conference" />
                  </label>
                  <label>
                    DOI
                    <input value={bibliographyDoi} onChange={(event) => setBibliographyDoi(event.target.value)} placeholder="10.xxxx/…" />
                  </label>
                  <label>
                    URL
                    <input value={bibliographyUrl} onChange={(event) => setBibliographyUrl(event.target.value)} placeholder="https://…" />
                  </label>
                </div>
                <div className="bibliography-tag-picker">
                  <span className="bib-field-label">Tags</span>
                  {bibliographyTags.length > 0 ? (
                    <div className="research-chip-group bibliography-tag-selected">
                      {bibliographyTags.map((tag) => (
                        <span key={tag} className="chip small">
                          {tag}
                          <button type="button" className="research-chip-remove" onClick={() => removeBibliographyTag(tag)} aria-label={`Remove ${tag}`}>
                            <FontAwesomeIcon icon={faXmark} />
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="bibliography-tag-input-row">
                    <input
                      value={bibliographyTagInput}
                      onChange={(event) => {
                        setBibliographyTagInput(event.target.value);
                        setBibliographyTagMenuOpen(true);
                        setBibliographyTagActiveIndex(0);
                      }}
                      onFocus={() => {
                        setBibliographyTagMenuOpen(true);
                        setBibliographyTagActiveIndex(0);
                      }}
                      onBlur={() => {
                        window.setTimeout(() => setBibliographyTagMenuOpen(false), 120);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "ArrowDown") {
                          event.preventDefault();
                          if (!bibliographyTagSuggestions.length) return;
                          setBibliographyTagMenuOpen(true);
                          setBibliographyTagActiveIndex((current) => (current + 1) % bibliographyTagSuggestions.length);
                          return;
                        }
                        if (event.key === "ArrowUp") {
                          event.preventDefault();
                          if (!bibliographyTagSuggestions.length) return;
                          setBibliographyTagMenuOpen(true);
                          setBibliographyTagActiveIndex((current) =>
                            current === 0 ? bibliographyTagSuggestions.length - 1 : current - 1
                          );
                          return;
                        }
                        if (event.key === "Escape") {
                          setBibliographyTagMenuOpen(false);
                          return;
                        }
                        if (event.key === "Enter") {
                          event.preventDefault();
                          if (bibliographyTagMenuOpen && bibliographyTagSuggestions[bibliographyTagActiveIndex]) {
                            addBibliographyTag(bibliographyTagSuggestions[bibliographyTagActiveIndex].label);
                            return;
                          }
                          addBibliographyTag(bibliographyTagInput);
                          return;
                        }
                        if (event.key === ",") {
                          event.preventDefault();
                          addBibliographyTag(bibliographyTagInput);
                        }
                      }}
                      placeholder="Type and press Enter or comma"
                    />
                    <button
                      type="button"
                      className="ghost docs-action-btn"
                      disabled={!normalizeTagLabel(bibliographyTagInput)}
                      onClick={() => addBibliographyTag(bibliographyTagInput)}
                    >
                      Add
                    </button>
                  </div>
                  {bibliographyTagMenuOpen && bibliographyTagSuggestions.length > 0 ? (
                    <div className="bibliography-tag-suggestions" role="listbox">
                      {bibliographyTagSuggestions.map((tag, index) => (
                        <button
                          key={tag.id}
                          type="button"
                          className={`bibliography-tag-suggestion ${index === bibliographyTagActiveIndex ? "active" : ""}`}
                          onMouseDown={(event) => {
                            event.preventDefault();
                            addBibliographyTag(tag.label);
                          }}
                        >
                          {tag.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <label className="bib-pdf-label">
                  <span className="bib-pdf-zone">
                    <FontAwesomeIcon icon={faFileArrowUp} />
                    <span>{bibliographyAttachmentFile ? bibliographyAttachmentFile.name : "Attach PDF"}</span>
                  </span>
                  <input type="file" accept="application/pdf" className="bib-pdf-input" onChange={(event) => setBibliographyAttachmentFile(event.target.files?.[0] || null)} />
                </label>
              </div>

              {/* Right: abstract fills full height */}
              <div className="bib-modal-col">
                <label className="bib-abstract-label">
                  <span className="bib-abstract-head">
                    <span>Abstract</span>
                    <span className="bib-abstract-actions">
                      {canExtractAbstract ? (
                        <button
                          type="button"
                          className="ghost docs-action-btn"
                          disabled={extractingBibliographyAbstractId === editingBibliographyId}
                          onClick={() => void handleExtractBibliographyAbstract(editingBibliographyId!)}
                        >
                          <FontAwesomeIcon icon={faMagicWandSparkles} spin={extractingBibliographyAbstractId === editingBibliographyId} />
                          {extractingBibliographyAbstractId === editingBibliographyId ? "Extracting..." : "Extract"}
                        </button>
                      ) : null}
                      {canExtractConcepts ? (
                        <button
                          type="button"
                          className="ghost docs-action-btn"
                          disabled={extractingBibliographyConceptsId === editingBibliographyId}
                          onClick={() => void handleExtractBibliographyConcepts(editingBibliographyId!)}
                        >
                          <FontAwesomeIcon icon={faMagicWandSparkles} spin={extractingBibliographyConceptsId === editingBibliographyId} />
                          {extractingBibliographyConceptsId === editingBibliographyId
                            ? "Extracting..."
                            : editingBibliography?.concepts.length
                              ? "Re-extract Concepts"
                              : "Extract Concepts"}
                        </button>
                      ) : null}
                    </span>
                  </span>
                  <textarea className="bib-abstract-fill" value={bibliographyAbstract} onChange={(event) => setBibliographyAbstract(event.target.value)} placeholder="Paper abstract…" />
                  {editingBibliography?.concepts.length ? (
                    <span className="research-chip-group bib-concept-list">
                      {editingBibliography.concepts.map((concept) => (
                        <span key={`${editingBibliography.id}-modal-concept-${concept}`} className="chip small">{concept}</span>
                      ))}
                    </span>
                  ) : null}
                </label>
              </div>
            </div>
            </>
            )}
          </div>
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
            <h3>{noteModalMode === "create" ? "New Log" : "Edit Log"}</h3>
            <button type="button" className="ghost docs-action-btn" onClick={() => setNoteModalOpen(false)} title="Close">
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>
          <div className="form-grid">
            <label className="full-span">
              Study *
              <select value={noteCollectionId} onChange={(event) => setNoteCollectionId(event.target.value)}>
                <option value="">Select study</option>
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
              Lane
              {renderLanePills(noteLane, setNoteLane)}
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
              {saving ? "Saving..." : noteModalMode === "create" ? "Add Log" : "Save Log"}
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
