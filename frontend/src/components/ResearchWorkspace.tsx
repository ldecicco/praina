import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArchive,
  faBookOpen,
  faCalendarDay,
  faChevronLeft,
  faChevronRight,
  faChevronUp,
  faChevronDown,
  faFile,
  faFileArrowUp,
  faComment,
  faFileExport,
  faFileImport,
  faFilter,
  faFlask,
  faGrip,
  faInbox,
  faLink,
  faList,
  faMagicWandSparkles,
  faPen,
  faPlus,
  faSearch,
  faShareNodes,
  faStar,
  faThumbtack,
  faTrash,
  faUsers,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import { useStatusToast } from "../lib/useStatusToast";
import { BibliographyGraphModal } from "./BibliographyGraphModal";
import { StudyGraphModal } from "./StudyGraphModal";
import { CollectionsGraphModal } from "./CollectionsGraphModal";
import { StudyCollabChat } from "./StudyCollabChat";
import { StudyLogRichEditor } from "./StudyLogRichEditor";
import { CommandPalette } from "./CommandPalette";
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
  AuthUser,
  DocumentListItem,
  Member,
  MeetingRecord,
  Project,
  CollectionGraph,
  ResearchCollection,
  ResearchCollectionDetail,
  ResearchCollectionMember,
  ResearchNote,
  ResearchNoteReply,
  ResearchNoteTemplate,
  ResearchPaperAuthor,
  ResearchPaperClaim,
  ResearchPaperQuestion,
  ResearchPaperSection,
  ResearchSpace,
  ResearchStudyFile,
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

type Tab = "references" | "notes" | "paper" | "iterations" | "overview" | "chat" | "files" | "todos";
type StudyDigestFilter = "all" | "needs-review" | "recent" | "deadlines" | "stale";
type StudyHomeView = "dashboard" | "studies";
type CollectionModalMode = "create" | "edit";
type ReferenceModalMode = "create" | "edit";
type NoteModalMode = "create" | "edit";
type ReferenceModalTab = "manual" | "bibtex" | "pdf" | "document";
type BibliographyModalMode = "create" | "edit";
type BibliographyCreateTab = "manual" | "batch";
type BibTab = "papers" | "collections";
type NoteModalSnapshot = {
  title: string;
  content: string;
  noteType: string;
  collectionId: string;
  lane: string;
  pinned: boolean;
  starred: boolean;
  referenceIds: string[];
  fileIds: string[];
  linkedNoteIds: string[];
};

function csvToList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function toggleListValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function sortedUniqueIds(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function startOfMonth(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addMonths(value: Date, delta: number): Date {
  return new Date(value.getFullYear(), value.getMonth() + delta, 1);
}

function formatDeadlinePressure(deadline: Date, now: Date) {
  const startOfToday = new Date(now);
  startOfToday.setHours(0, 0, 0, 0);
  const startOfDeadline = new Date(deadline);
  startOfDeadline.setHours(0, 0, 0, 0);
  const diffDays = Math.round((startOfDeadline.getTime() - startOfToday.getTime()) / (24 * 60 * 60 * 1000));

  if (diffDays < 0) {
    const overdueDays = Math.abs(diffDays);
    return {
      label: overdueDays === 1 ? "1 day overdue" : `${overdueDays} days overdue`,
      tone: "danger" as const,
    };
  }
  if (diffDays === 0) {
    return { label: "Today", tone: "danger" as const };
  }
  if (diffDays < 7) {
    return {
      label: diffDays === 1 ? "1 day left" : `${diffDays} days left`,
      tone: "danger" as const,
    };
  }
  if (diffDays < 28) {
    const weeks = Math.ceil(diffDays / 7);
    return {
      label: weeks === 1 ? "1 week left" : `${weeks} weeks left`,
      tone: "warning" as const,
    };
  }
  return {
    label: `${Math.ceil(diffDays / 7)} weeks left`,
    tone: "muted" as const,
  };
}

function buildNoteModalSnapshot(value: NoteModalSnapshot): NoteModalSnapshot {
  return {
    title: value.title,
    content: value.content,
    noteType: value.noteType,
    collectionId: value.collectionId,
    lane: value.lane,
    pinned: value.pinned,
    starred: value.starred,
    referenceIds: sortedUniqueIds(value.referenceIds),
    fileIds: sortedUniqueIds(value.fileIds),
    linkedNoteIds: sortedUniqueIds(value.linkedNoteIds),
  };
}

function noteModalSnapshotsEqual(a: NoteModalSnapshot, b: NoteModalSnapshot): boolean {
  return JSON.stringify(buildNoteModalSnapshot(a)) === JSON.stringify(buildNoteModalSnapshot(b));
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

function isIndexNote(note: ResearchNote): boolean {
  return note.note_type === "index";
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

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value >= 10 || unitIndex === 0 ? Math.round(value) : value.toFixed(1)} ${units[unitIndex]}`;
}

function uniqueLogFileIds(noteIds: string[], allNotes: ResearchNote[]): string[] {
  return Array.from(
    new Set(
      allNotes
        .filter((note) => noteIds.includes(note.id))
        .flatMap((note) => note.linked_file_ids || [])
        .filter(Boolean)
    )
  );
}

function extractMarkdownFileLabels(content: string): string[] {
  const labels = new Map<string, string>();
  for (const match of content.matchAll(/!\[([^\]]+)\]/g)) {
    const label = (match[1] || "").trim();
    if (!label) continue;
    const key = label.toLowerCase();
    if (!labels.has(key)) labels.set(key, label);
  }
  return Array.from(labels.values());
}

function extractMarkdownReferenceLabels(content: string): string[] {
  const labels = new Map<string, string>();
  const scrubbed = content
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`\n]*`/g, " ");
  for (const match of scrubbed.matchAll(/(?:@|%)\[(.*?)\]/g)) {
    const label = (match[1] || "").trim();
    if (!label) continue;
    const key = label.toLowerCase();
    if (!labels.has(key)) labels.set(key, label);
  }
  return Array.from(labels.values());
}

function memberMentionHandle(name: string): string {
  const normalized = (name || "")
    .trim()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return normalized || "user";
}

function extractMarkdownNoteLabels(content: string): string[] {
  const labels = new Map<string, string>();
  const scrubbed = content
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`\n]*`/g, " ");
  for (const match of scrubbed.matchAll(/\[\[([^[\]]+)\]\]/g)) {
    const label = (match[1] || "").trim();
    if (!label) continue;
    const key = label.toLowerCase();
    if (!labels.has(key)) labels.set(key, label);
  }
  return Array.from(labels.values());
}

function logDateBucketLabel(value: string): string {
  const date = new Date(value);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfTarget = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((startOfToday.getTime() - startOfTarget.getTime()) / 86_400_000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "This Week";
  return formatLogDate(value);
}

function isImageMime(mimeType: string | null | undefined): boolean {
  return (mimeType || "").toLowerCase().startsWith("image/");
}

function isCsvMime(mimeType: string | null | undefined, filename: string): boolean {
  const mime = (mimeType || "").toLowerCase();
  return mime.includes("csv") || filename.toLowerCase().endsWith(".csv");
}

function userInitials(name: string): string {
  const parts = (name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "");
  return parts.join("") || "U";
}

function resolveAvatarUrl(rawValue: string | null | undefined): string | null {
  const raw = (rawValue || "").trim();
  if (!raw) return null;
  if (/^(https?:)?\/\//i.test(raw) || raw.startsWith("data:") || raw.startsWith("blob:")) {
    return raw;
  }
  const base = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  return `${base}${path}`;
}

function studyMemberAvatarUrl(member: ResearchCollectionMember): string | null {
  return resolveAvatarUrl(member.avatar_url);
}

function LogAvatar({
  name,
  avatarUrl,
  className = "",
}: {
  name: string;
  avatarUrl?: string | null;
  className?: string;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const initial = userInitials(name);
  const hue = [...(name || "?")].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
  const resolvedAvatarUrl = imageFailed ? null : resolveAvatarUrl(avatarUrl);

  useEffect(() => {
    setImageFailed(false);
  }, [avatarUrl]);

  return (
    <span
      className={`study-avatar research-log-avatar${className ? ` ${className}` : ""}`}
      title={name}
      style={{ backgroundColor: `hsl(${hue}, 55%, 45%)` }}
    >
      {resolvedAvatarUrl ? (
        <img src={resolvedAvatarUrl} alt={name} onError={() => setImageFailed(true)} />
      ) : (
        initial
      )}
    </span>
  );
}

function ResearchFilePreviewCard({
  file,
  projectId,
  collectionId,
  spaceId,
}: {
  file: ResearchStudyFile;
  projectId: string | null;
  collectionId: string | null;
  spaceId?: string;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [csvRows, setCsvRows] = useState<string[][]>([]);

  useEffect(() => {
    let revokedUrl: string | null = null;
    let cancelled = false;

    async function loadPreview() {
      if (!projectId || !collectionId) return;
      if (!isImageMime(file.mime_type) && !isCsvMime(file.mime_type, file.original_filename)) return;
      try {
        const blob = await api.getStudyFile(projectId, collectionId, file.id, spaceId || undefined);
        if (cancelled) return;
        if (isImageMime(file.mime_type)) {
          const nextUrl = URL.createObjectURL(blob);
          revokedUrl = nextUrl;
          setObjectUrl(nextUrl);
          return;
        }
        const text = await blob.text();
        if (cancelled) return;
        const rows = text
          .trim()
          .split(/\r?\n/)
          .slice(0, 8)
          .map((line) => line.split(",").slice(0, 6).map((cell) => cell.trim()));
        setCsvRows(rows);
      } catch {
        if (!cancelled) {
          setObjectUrl(null);
          setCsvRows([]);
        }
      }
    }

    void loadPreview();
    return () => {
      cancelled = true;
      if (revokedUrl) URL.revokeObjectURL(revokedUrl);
    };
  }, [collectionId, file, projectId, spaceId]);

  if (isImageMime(file.mime_type) && objectUrl) {
    return (
      <div className="research-file-preview">
        <img src={objectUrl} alt={file.original_filename} className="research-file-preview-image" />
      </div>
    );
  }

  if (isCsvMime(file.mime_type, file.original_filename) && csvRows.length > 0) {
    return (
      <div className="research-file-preview research-file-preview-table">
        <div className="research-file-preview-scroll">
          <table className="markdown-table">
            <tbody>
              {csvRows.map((row, rowIndex) => (
                <tr key={`${file.id}-csv-row-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${file.id}-csv-cell-${rowIndex}-${cellIndex}`}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return null;
}

function StudyHeaderAvatar({ member, isOnline }: { member: ResearchCollectionMember; isOnline?: boolean }) {
  const [imageFailed, setImageFailed] = useState(false);
  const initial = userInitials(member.member_name || "");
  const hue = [...(member.member_name || "?")].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
  const avatarUrl = imageFailed ? null : studyMemberAvatarUrl(member);

  useEffect(() => {
    setImageFailed(false);
  }, [member.avatar_url]);

  return (
    <span
      className="study-avatar"
      title={member.member_name}
      style={{ backgroundColor: `hsl(${hue}, 55%, 45%)` }}
    >
      {avatarUrl ? (
        <img src={avatarUrl} alt={member.member_name} onError={() => setImageFailed(true)} />
      ) : (
        initial
      )}
      <span className={`study-avatar-presence-dot ${isOnline ? "online" : "offline"}`} />
    </span>
  );
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

function formatIsoDateLocal(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function resolveTemplateTokens(
  value: string,
  context: {
    userName: string;
    studyTitle: string;
    spaceTitle: string;
  },
): string {
  const now = new Date();
  return [
    ["[TODAY]", formatIsoDateLocal(now)],
    ["[NOW]", now.toLocaleString()],
    ["[YEAR]", String(now.getFullYear())],
    ["[USER]", context.userName],
    ["[STUDY]", context.studyTitle],
    ["[SPACE]", context.spaceTitle],
  ].reduce((acc, [token, replacement]) => acc.split(token).join(replacement), value || "");
}

type DraftActionItemPreview = {
  text: string;
  assigneeHandle: string | null;
  dueDate: string | null;
  isDone: boolean;
};

function extractDraftActionItems(content: string): DraftActionItemPreview[] {
  const items: DraftActionItemPreview[] = [];
  let insideFence = false;
  for (const rawLine of (content || "").split("\n")) {
    const stripped = rawLine.trim();
    if (stripped.startsWith("```")) {
      insideFence = !insideFence;
      continue;
    }
    if (insideFence) continue;
    const match = rawLine.match(/^\s*(?:[-*+]\s+)?\[( |x|X)\]\s+(.*)$/);
    if (!match) continue;
    let body = (match[2] || "").trim();
    if (!body) continue;
    let dueDate: string | null = null;
    const dueMatches = Array.from(body.matchAll(/(?:(?:->)\s*)?(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{4})/g));
    const dueMatch = dueMatches.length ? dueMatches[dueMatches.length - 1] : null;
    if (dueMatch) {
      dueDate = dueMatch[1];
      body = (body.slice(0, dueMatch.index) + body.slice((dueMatch.index || 0) + dueMatch[0].length)).trim();
      body = body.replace(/(?:->|by|before|entro|per)\s*$/i, "").trim();
    }
    const assigneeMatch = body.match(/@([A-Za-z0-9._:-]+)/);
    const assigneeHandle = assigneeMatch ? assigneeMatch[1] : null;
    const text = body.replace(/@([A-Za-z0-9._:-]+)/g, "").replace(/\s{2,}/g, " ").trim();
    if (!text) continue;
    items.push({
      text,
      assigneeHandle,
      dueDate,
      isDone: match[1].toLowerCase() === "x",
    });
  }
  return items;
}

async function computeStudyFileFingerprint(file: File): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;
  try {
    const buffer = await file.arrayBuffer();
    const digest = await globalThis.crypto.subtle.digest("SHA-256", buffer);
    const hex = Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
    return `${file.type || "application/octet-stream"}:${file.size}:${hex}`;
  } catch {
    return null;
  }
}

export function ResearchWorkspace({
  researchSpaceId,
  availableResearchSpaces,
  selectedProjectId,
  currentUser,
  accessToken,
  bibliographyOnly = false,
  isAdmin = false,
  isStudent = false,
  currentProject = null,
  onClearResearchSpaceFilter,
  navigationState,
  onNavigationStateChange,
  openBibliographyReferenceId = null,
  onOpenBibliographyReferenceConsumed,
  homeViewRequest,
  homeViewRequestNonce,
  researchTourActive = false,
  researchTourStepId = null,
}: {
  researchSpaceId: string;
  availableResearchSpaces: ResearchSpace[];
  selectedProjectId: string;
  currentUser: AuthUser;
  accessToken: string;
  bibliographyOnly?: boolean;
  isAdmin?: boolean;
  isStudent?: boolean;
  currentProject?: Project | null;
  onClearResearchSpaceFilter?: () => void;
  navigationState?: {
    selectedCollectionId: string | null;
    tab: Tab;
    selectedBibliographyCollectionId: string | null;
  };
  onNavigationStateChange?: (state: {
    selectedCollectionId: string | null;
    tab: Tab;
    selectedBibliographyCollectionId: string | null;
  }) => void;
  openBibliographyReferenceId?: string | null;
  onOpenBibliographyReferenceConsumed?: () => void;
  homeViewRequest?: StudyHomeView;
  homeViewRequestNonce?: number;
  researchTourActive?: boolean;
  researchTourStepId?: string | null;
}) {
  const activeResearchSpaceId = researchSpaceId || "";
  const activeResearchSpace = availableResearchSpaces.find((item) => item.id === activeResearchSpaceId) ?? null;
  const hasProjectContext = Boolean(
    currentProject?.id &&
    currentProject.id === selectedProjectId &&
    selectedProjectId !== "00000000-0000-0000-0000-000000000000"
  );
  const [collections, setCollections] = useState<ResearchCollection[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(navigationState?.selectedCollectionId ?? null);
  const [bulkResearchTargetCollectionId, setBulkResearchTargetCollectionId] = useState("");
  const [collectionDetail, setCollectionDetail] = useState<ResearchCollectionDetail | null>(null);

  const [references, setReferences] = useState<ResearchReference[]>([]);
  const [bibliography, setBibliography] = useState<BibliographyReference[]>([]);
  const [bibliographyCollections, setBibliographyCollections] = useState<BibliographyCollection[]>([]);
  const [selectedBibliographyCollectionId, setSelectedBibliographyCollectionId] = useState<string | null>(navigationState?.selectedBibliographyCollectionId ?? null);
  const [selectedBibliographyCollectionPaperIds, setSelectedBibliographyCollectionPaperIds] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState<ResearchNote[]>([]);
  const [studyFiles, setStudyFiles] = useState<ResearchStudyFile[]>([]);
  const [allReferences, setAllReferences] = useState<ResearchReference[]>([]);
  const [projectDocuments, setProjectDocuments] = useState<DocumentListItem[]>([]);
  const [projectMeetings, setProjectMeetings] = useState<MeetingRecord[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [discoverableUsers, setDiscoverableUsers] = useState<AuthUser[]>([]);
  const [wps, setWps] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);

  const [tab, setTab] = useState<Tab>(navigationState?.tab ?? "overview");
  const [studyOnlineUserIds, setStudyOnlineUserIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const { error, setError, setStatus } = useStatusToast();
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
  const uploadedStudyFileFingerprintMapRef = useRef<Map<string, ResearchStudyFile>>(new Map());

  const [collectionTitle, setCollectionTitle] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [collectionStatus, setCollectionStatus] = useState("active");
  const [collectionSpaceIds, setCollectionSpaceIds] = useState<string[]>([]);
  const [inlineStudyTitle, setInlineStudyTitle] = useState("");
  const [inlineStudyFocus, setInlineStudyFocus] = useState("");
  const [editingStudyTitle, setEditingStudyTitle] = useState(false);
  const [editingStudyFocus, setEditingStudyFocus] = useState(false);
  const [synthesisExpanded, setSynthesisExpanded] = useState(false);
  const [overviewLinksExpanded, setOverviewLinksExpanded] = useState(false);
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
  const [editingPaperTitle, setEditingPaperTitle] = useState(false);
  const [inlinePaperTitle, setInlinePaperTitle] = useState("");
  const [editingPaperVenue, setEditingPaperVenue] = useState(false);
  const [inlinePaperVenue, setInlinePaperVenue] = useState("");
  const [editingPaperOverleaf, setEditingPaperOverleaf] = useState(false);
  const [inlinePaperOverleaf, setInlinePaperOverleaf] = useState("");
  const [editingPaperStatus, setEditingPaperStatus] = useState(false);
  const [inlinePaperStatus, setInlinePaperStatus] = useState("not_started");
  const [editingPaperRegistration, setEditingPaperRegistration] = useState(false);
  const [inlinePaperRegistration, setInlinePaperRegistration] = useState("");
  const [editingPaperSubmission, setEditingPaperSubmission] = useState(false);
  const [inlinePaperSubmission, setInlinePaperSubmission] = useState("");
  const [editingPaperDecision, setEditingPaperDecision] = useState(false);
  const [inlinePaperDecision, setInlinePaperDecision] = useState("");
  const [editingPaperMotivation, setEditingPaperMotivation] = useState(false);
  const [inlinePaperMotivation, setInlinePaperMotivation] = useState("");

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

  const [autoLinkAfterCreate, setAutoLinkAfterCreate] = useState(false);
  const [studyPaletteOpen, setStudyPaletteOpen] = useState(false);
  const [studyPaletteQuery, setStudyPaletteQuery] = useState("");
  const [studyPaletteIndex, setStudyPaletteIndex] = useState(0);
  const studyPaletteInputRef = useRef<HTMLInputElement | null>(null);

  const [noteTitle, setNoteTitle] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [noteType, setNoteType] = useState("observation");
  const [noteCollectionId, setNoteCollectionId] = useState("");
  const [noteLane, setNoteLane] = useState("");
  const [notePinned, setNotePinned] = useState(false);
  const [noteStarred, setNoteStarred] = useState(false);
  const [noteReferenceIds, setNoteReferenceIds] = useState<string[]>([]);
  const [noteFileIds, setNoteFileIds] = useState<string[]>([]);
  const [noteLinkedNoteIds, setNoteLinkedNoteIds] = useState<string[]>([]);
  const [noteTemplates, setNoteTemplates] = useState<ResearchNoteTemplate[]>([]);
  const [noteTemplateLibraryOpen, setNoteTemplateLibraryOpen] = useState(false);
  const [noteTemplateSaveOpen, setNoteTemplateSaveOpen] = useState(false);
  const [noteTemplateSearch, setNoteTemplateSearch] = useState("");
  const [noteTemplateName, setNoteTemplateName] = useState("");
  const [noteTemplateSystem, setNoteTemplateSystem] = useState(false);
  const [savingNoteTemplate, setSavingNoteTemplate] = useState(false);
  const [deletingNoteTemplateId, setDeletingNoteTemplateId] = useState<string | null>(null);
  const [quickLogContent, setQuickLogContent] = useState("");
  const [quickLogTitle, setQuickLogTitle] = useState("");
  const [quickLogLane, setQuickLogLane] = useState("");
  const [quickLogRefIds, setQuickLogRefIds] = useState<string[]>([]);
  const [quickLogFileIds, setQuickLogFileIds] = useState<string[]>([]);

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
  const [uploadingStudyFile, setUploadingStudyFile] = useState(false);
  const [filesView, setFilesView] = useState<"grid" | "list">("grid");
  const [fileSearchOpen, setFileSearchOpen] = useState(false);

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
  const [refSortKey, setRefSortKey] = useState<"created_at" | "title" | "connections">("created_at");
  const [noteLaneFilter, setNoteLaneFilter] = useState("");
  const [noteSearchQuery, setNoteSearchQuery] = useState("");
  const [todoQuickFilter, setTodoQuickFilter] = useState<"all" | "mine" | "overdue">("all");
  const [todoView, setTodoView] = useState<"list" | "board">("list");
  const [updatingActionItemId, setUpdatingActionItemId] = useState<string | null>(null);
  const [draggingTodoActionId, setDraggingTodoActionId] = useState<string | null>(null);
  const [todoDropStatus, setTodoDropStatus] = useState<"open" | "doing" | "done" | null>(null);
  const [composerExpanded, setComposerExpanded] = useState(false);
  const [inlineEditNoteId, setInlineEditNoteId] = useState<string | null>(null);
  const [inlineEditTitle, setInlineEditTitle] = useState("");
  const [inlineEditContent, setInlineEditContent] = useState("");
  const [inlineEditLane, setInlineEditLane] = useState("");
  const [inlineEditPinned, setInlineEditPinned] = useState(false);
  const [inlineEditStarred, setInlineEditStarred] = useState(false);
  const [inlineEditRefIds, setInlineEditRefIds] = useState<string[]>([]);
  const [inlineEditFileIds, setInlineEditFileIds] = useState<string[]>([]);
  const [inlineEditLinkedNoteIds, setInlineEditLinkedNoteIds] = useState<string[]>([]);
  const [editingIterationTitleId, setEditingIterationTitleId] = useState<string | null>(null);
  const [inlineIterationTitle, setInlineIterationTitle] = useState("");
  const [editingIterationStartId, setEditingIterationStartId] = useState<string | null>(null);
  const [inlineIterationStart, setInlineIterationStart] = useState("");
  const [editingIterationEndId, setEditingIterationEndId] = useState<string | null>(null);
  const [inlineIterationEnd, setInlineIterationEnd] = useState("");
  const [replyingNoteId, setReplyingNoteId] = useState<string | null>(null);
  const [submittingReplyNoteId, setSubmittingReplyNoteId] = useState<string | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [replyRefIds, setReplyRefIds] = useState<Record<string, string[]>>({});
  const [collapsedIterationIds, setCollapsedIterationIds] = useState<Set<string>>(new Set());
  const [foldedNoteIds, setFoldedNoteIds] = useState<Set<string>>(new Set());
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionTrigger, setMentionTrigger] = useState<"@" | "%">("%");
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionActiveIndex, setMentionActiveIndex] = useState(0);
  const [mentionTarget, setMentionTarget] = useState<"composer" | "inline" | "reply" | "modal">("composer");
  const [mentionAnchor, setMentionAnchor] = useState<{ top: number; left: number } | null>(null);
  const [mentionCursorStart, setMentionCursorStart] = useState(0);
  const [mentionReplyNoteId, setMentionReplyNoteId] = useState<string | null>(null);
  const inlineEditContentRef = useRef<HTMLTextAreaElement | null>(null);
  const replyInputRef = useRef<HTMLTextAreaElement | null>(null);
  const [selectedInboxLogIds, setSelectedInboxLogIds] = useState<Set<string>>(new Set());
  const [activeInboxNoteId, setActiveInboxNoteId] = useState<string | null>(null);
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
  const [noteTagOptions, setNoteTagOptions] = useState<string[]>([]);
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
  const [studyGraphOpen, setStudyGraphOpen] = useState(false);
  const [collectionsGraphOpen, setCollectionsGraphOpen] = useState(false);
  const [collectionsGraphData, setCollectionsGraphData] = useState<CollectionGraph | null>(null);
  const [loadingCollectionsGraph, setLoadingCollectionsGraph] = useState(false);
  const quickLogInputRef = useRef<HTMLTextAreaElement | null>(null);
  const quickLogFileInputRef = useRef<HTMLInputElement | null>(null);
  const inlineEditFileInputRef = useRef<HTMLInputElement | null>(null);
  const noteSearchInputRef = useRef<HTMLInputElement | null>(null);
  const noteEditorRef = useRef<Editor | null>(null);
  const noteModalFileInputRef = useRef<HTMLInputElement | null>(null);
  const noteModalInitialSnapshotRef = useRef<NoteModalSnapshot | null>(null);
  const [studySearchQuery, setStudySearchQuery] = useState("");
  const [studyDigestFilter, setStudyDigestFilter] = useState<StudyDigestFilter>("all");
  const [studyHomeView, setStudyHomeView] = useState<StudyHomeView>(isStudent ? "studies" : "dashboard");
  const [studyHeatmapMonth, setStudyHeatmapMonth] = useState(() => startOfMonth(new Date()));
  const pendingNavigationSyncRef = useRef<string | null>(null);
  const lastAppliedNavigationStateRef = useRef<string | null>(null);

  function navigationSignatureForState(state: {
    selectedCollectionId: string | null;
    tab: Tab;
    selectedBibliographyCollectionId: string | null;
  }) {
    return JSON.stringify({
      selectedCollectionId: state.selectedCollectionId ?? null,
      tab: state.selectedCollectionId ? state.tab : "overview",
      selectedBibliographyCollectionId: state.selectedBibliographyCollectionId ?? null,
    });
  }

  const activeCollections = collections.filter((item) => item.status === "active");
  const archivedCollections = collections.filter((item) => item.status !== "active");
  const normalizedStudySearchQuery = studySearchQuery.trim().toLowerCase();
  const filteredActiveCollections = useMemo(
    () =>
      activeCollections.filter((item) =>
        !normalizedStudySearchQuery ||
        [item.title, item.description || item.hypothesis || "", item.status]
          .some((value) => value.toLowerCase().includes(normalizedStudySearchQuery))
      ),
    [activeCollections, normalizedStudySearchQuery]
  );
  const filteredArchivedCollections = useMemo(
    () =>
      archivedCollections.filter((item) =>
        !normalizedStudySearchQuery ||
        [item.title, item.description || item.hypothesis || "", item.status]
          .some((value) => value.toLowerCase().includes(normalizedStudySearchQuery))
      ),
    [archivedCollections, normalizedStudySearchQuery]
  );
  const studyDigestData = useMemo(() => {
    const now = new Date();
    const nowTime = now.getTime();
    const deadlineThreshold = nowTime + 30 * 24 * 60 * 60 * 1000;
    const weekStart = new Date(now);
    const weekday = weekStart.getDay();
    const mondayOffset = (weekday + 6) % 7;
    weekStart.setHours(0, 0, 0, 0);
    weekStart.setDate(weekStart.getDate() - mondayOffset);

    function parseDate(value: string | null | undefined) {
      if (!value) return null;
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime()) ? null : parsed;
    }

    const items = activeCollections.map((study) => {
      const updatedAt = parseDate(study.updated_at) ?? new Date(0);
      const lastIterationAt = parseDate(study.last_reviewed_iteration_at);
      const deadlineCandidates = [
        study.registration_deadline ? { label: "Registration", date: parseDate(study.registration_deadline) } : null,
        study.submission_deadline ? { label: "Submission", date: parseDate(study.submission_deadline) } : null,
        study.decision_date ? { label: "Decision", date: parseDate(study.decision_date) } : null,
      ]
        .filter((value): value is { label: string; date: Date | null } => Boolean(value && value.date))
        .map((value) => ({ label: value.label, date: value.date as Date }))
        .sort((a, b) => a.date.getTime() - b.date.getTime());

      const upcomingDeadline = deadlineCandidates.find((item) => item.date.getTime() >= nowTime && item.date.getTime() <= deadlineThreshold) ?? null;
      const overdueDeadline = deadlineCandidates.find((item) => item.date.getTime() < nowTime) ?? null;
      const recentlyActive = study.recent_log_count > 0;
      const needsReview = study.needs_review;
      const staleThreshold = 7 * 24 * 60 * 60 * 1000;
      const stale = !recentlyActive && (nowTime - updatedAt.getTime()) > staleThreshold && (study.open_action_count + study.doing_action_count) > 0;

      return {
        study,
        updatedAt,
        lastIterationAt,
        recentlyActive,
        needsReview,
        upcomingDeadline,
        overdueDeadline,
        stale,
      };
    });

    return {
      weekLabel: weekStart.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }),
      total: items.length,
      needsReviewCount: items.filter((item) => item.needsReview).length,
      recentCount: items.filter((item) => item.recentlyActive).length,
      deadlineCount: items.filter((item) => item.upcomingDeadline || item.overdueDeadline).length,
      overdueCount: items.filter((item) => item.study.overdue_action_count > 0).length,
      staleCount: items.filter((item) => item.stale).length,
      assignedCount: items.reduce((sum, item) => sum + item.study.assigned_to_me_action_count, 0),
      items,
      needsReview: items
        .filter((item) => item.needsReview)
        .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
        .slice(0, 4),
      recent: items
        .filter((item) => item.recentlyActive)
        .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
        .slice(0, 4),
      deadlines: items
        .filter((item) => item.upcomingDeadline || item.overdueDeadline)
        .sort((a, b) => {
          const left = (a.overdueDeadline || a.upcomingDeadline)?.date.getTime() ?? Number.MAX_SAFE_INTEGER;
          const right = (b.overdueDeadline || b.upcomingDeadline)?.date.getTime() ?? Number.MAX_SAFE_INTEGER;
          return left - right;
        })
        .slice(0, 4),
      stale: items
        .filter((item) => item.stale)
        .sort((a, b) => a.updatedAt.getTime() - b.updatedAt.getTime())
        .slice(0, 4),
    };
  }, [activeCollections]);
  const visibleActiveCollections = useMemo(() => {
    return filteredActiveCollections.filter((item) => {
      const digestItem = studyDigestData.items.find((entry) => entry.study.id === item.id);
      if (!digestItem) return studyDigestFilter === "all";
      if (studyDigestFilter === "needs-review") return digestItem.needsReview;
      if (studyDigestFilter === "recent") return digestItem.recentlyActive;
      if (studyDigestFilter === "deadlines") return Boolean(digestItem.upcomingDeadline || digestItem.overdueDeadline);
      if (studyDigestFilter === "stale") return digestItem.stale;
      return true;
    });
  }, [filteredActiveCollections, studyDigestData.items, studyDigestFilter]);
  const visibleArchivedCollections = useMemo(() => {
    return filteredArchivedCollections.filter((item) => {
      const digestItem = studyDigestData.items.find((entry) => entry.study.id === item.id);
      if (!digestItem) return studyDigestFilter === "all";
      if (studyDigestFilter === "needs-review") return digestItem.needsReview;
      if (studyDigestFilter === "recent") return digestItem.recentlyActive;
      if (studyDigestFilter === "deadlines") return Boolean(digestItem.upcomingDeadline || digestItem.overdueDeadline);
      if (studyDigestFilter === "stale") return digestItem.stale;
      return true;
    });
  }, [filteredArchivedCollections, studyDigestData.items, studyDigestFilter]);
  const studyHeatmapData = useMemo(() => {
    const monthStart = startOfMonth(studyHeatmapMonth);
    const nextMonth = addMonths(monthStart, 1);
    const dayCount = Math.max(1, Math.round((nextMonth.getTime() - monthStart.getTime()) / (24 * 60 * 60 * 1000)));
    const days = Array.from({ length: dayCount }, (_, index) => {
      const day = new Date(monthStart);
      day.setDate(monthStart.getDate() + index);
      const key = day.toISOString().slice(0, 10);
      return {
        key,
        dayNumber: day.getDate(),
        weekday: day.toLocaleDateString(undefined, { weekday: "short" }),
        label: day.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      };
    });

    const rows = filteredActiveCollections
      .map((study) => {
        const activityMap = new Map((study.activity_days || []).map((entry) => [entry.date, entry.count]));
        const deadlineMap = new Map<string, { label: string; tone: "danger" | "warning" | "muted" }[]>();
        const deadlineCandidates = [
          study.registration_deadline ? { label: "Registration", raw: study.registration_deadline } : null,
          study.submission_deadline ? { label: "Submission", raw: study.submission_deadline } : null,
          study.decision_date ? { label: "Decision", raw: study.decision_date } : null,
        ].filter((item): item is { label: string; raw: string } => Boolean(item));
        deadlineCandidates.forEach((item) => {
          const parsed = new Date(item.raw);
          if (Number.isNaN(parsed.getTime())) return;
          const key = parsed.toISOString().slice(0, 10);
          const pressure = formatDeadlinePressure(parsed, new Date());
          const bucket = deadlineMap.get(key) ?? [];
          bucket.push({ label: item.label, tone: pressure.tone });
          deadlineMap.set(key, bucket);
        });
        const values = days.map((day) => activityMap.get(day.key) || 0);
        return {
          study,
          values,
          deadlines: days.map((day) => deadlineMap.get(day.key) ?? []),
          total: values.reduce((sum, value) => sum + value, 0),
        };
      })
      .sort((left, right) => {
        if (right.total !== left.total) return right.total - left.total;
        return (left.study.title || "").localeCompare(right.study.title || "");
      });

    const maxCount = rows.reduce((max, row) => Math.max(max, ...row.values), 0);
    const earliestActivityDate = activeCollections
      .flatMap((study) => study.activity_days || [])
      .map((entry) => {
        const parsed = new Date(entry.date);
        parsed.setHours(0, 0, 0, 0);
        return parsed;
      })
      .sort((a, b) => a.getTime() - b.getTime())[0] ?? addMonths(startOfMonth(new Date()), -2);
    const minMonth = startOfMonth(earliestActivityDate);
    const maxMonth = startOfMonth(new Date());

    return {
      monthStart,
      monthLabel: monthStart.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
      days,
      rows,
      maxCount,
      canGoPrev: monthStart.getTime() > minMonth.getTime(),
      canGoNext: monthStart.getTime() < maxMonth.getTime(),
    };
  }, [activeCollections, filteredActiveCollections, studyHeatmapMonth]);
  const readCount = references.filter((item) => item.reading_status === "read" || item.reading_status === "reviewed").length;
  const unreadRefCount = references.filter((item) => item.reading_status === "unread").length;
  const tabAlerts = useMemo(() => {
    const collNotes = notes.filter((n) => n.collection_id === selectedCollectionId);
    const unprocessedInbox = collNotes.filter(
      (note) =>
        !paperQuestions.some((q) => q.note_ids.includes(note.id)) &&
        !paperClaims.some((c) => c.note_ids.includes(note.id)) &&
        !paperSections.some((s) => s.note_ids.includes(note.id))
    ).length;
    const unsupportedClaims = paperClaims.filter((c) => c.reference_ids.length + c.note_ids.length + c.result_ids.length === 0).length;
    const weakSections = paperSections.filter((s) => s.claim_ids.length + s.reference_ids.length + s.note_ids.length + s.result_ids.length === 0).length;
    return { inboxAlert: unprocessedInbox > 0, paperAlert: unsupportedClaims > 0 || weakSections > 0, refsAlert: unreadRefCount > 0 };
  }, [notes, selectedCollectionId, paperQuestions, paperClaims, paperSections, unreadRefCount]);
  const visibleStudyLogNotes = useMemo(
    () => notes.filter((item) => item.collection_id === selectedCollectionId && !isIndexNote(item)),
    [notes, selectedCollectionId],
  );
  const allVisibleStudyLogsFolded =
    visibleStudyLogNotes.length > 0 && visibleStudyLogNotes.every((item) => foldedNoteIds.has(item.id));
  const selectedCollection = collections.find((item) => item.id === selectedCollectionId) ?? null;
  const selectedBibliographyCollection = bibliographyCollections.find((item) => item.id === selectedBibliographyCollectionId) ?? null;

  useEffect(() => {
    if (!navigationState) return;
    const signature = navigationSignatureForState({
      selectedCollectionId: navigationState.selectedCollectionId ?? null,
      tab: navigationState.tab,
      selectedBibliographyCollectionId: navigationState.selectedBibliographyCollectionId ?? null,
    });
    if (lastAppliedNavigationStateRef.current === signature) return;
    pendingNavigationSyncRef.current = signature;
    setSelectedCollectionId(navigationState.selectedCollectionId ?? null);
    setTab((navigationState.selectedCollectionId ?? null) ? navigationState.tab : "overview");
    setSelectedBibliographyCollectionId(navigationState.selectedBibliographyCollectionId ?? null);
  }, [navigationState]);

  useEffect(() => {
    if (bibliographyOnly || !homeViewRequest) return;
    setStudyHomeView(homeViewRequest);
  }, [bibliographyOnly, homeViewRequest, homeViewRequestNonce]);

  useEffect(() => {
    const currentSignature = navigationSignatureForState({
      selectedCollectionId,
      tab,
      selectedBibliographyCollectionId,
    });
    if (pendingNavigationSyncRef.current) {
      if (pendingNavigationSyncRef.current !== currentSignature) {
        return;
      }
      lastAppliedNavigationStateRef.current = pendingNavigationSyncRef.current;
      pendingNavigationSyncRef.current = null;
      return;
    }
    const nextState = {
      selectedCollectionId,
      tab: selectedCollectionId ? tab : "overview",
      selectedBibliographyCollectionId,
    };
    if (
      navigationState &&
      (navigationState.selectedCollectionId ?? null) === nextState.selectedCollectionId &&
      navigationState.tab === nextState.tab &&
      (navigationState.selectedBibliographyCollectionId ?? null) === nextState.selectedBibliographyCollectionId
    ) {
      return;
    }
    onNavigationStateChange?.(nextState);
  }, [selectedCollectionId, tab, selectedBibliographyCollectionId, navigationState, onNavigationStateChange]);

  useEffect(() => {
    if (!noteModalOpen) return;

    const nextReferenceIds = collectResolvedReferenceIds(noteContent);
    const nextFileIds = collectResolvedFileIds(noteContent, noteFileIds);
    const nextLinkedNoteIds = collectResolvedLinkedNoteIds(noteContent, editingNoteId);

    setNoteReferenceIds((current) =>
      current.length === nextReferenceIds.length && current.every((id, index) => id === nextReferenceIds[index])
        ? current
        : nextReferenceIds
    );
    setNoteFileIds((current) =>
      current.length === nextFileIds.length && current.every((id, index) => id === nextFileIds[index])
        ? current
        : nextFileIds
    );
    setNoteLinkedNoteIds((current) =>
      current.length === nextLinkedNoteIds.length && current.every((id, index) => id === nextLinkedNoteIds[index])
        ? current
        : nextLinkedNoteIds
    );
  }, [noteModalOpen, noteContent, editingNoteId]);

  useEffect(() => {
    if (tab !== "notes") return;
    if (!selectedCollectionId) return;
    if (noteModalOpen || inlineEditNoteId || replyingNoteId) return;
    const collectionNotes = notes.filter((item) => item.collection_id === selectedCollectionId);
    if (collectionNotes.length === 0) {
      if (activeInboxNoteId) setActiveInboxNoteId(null);
      return;
    }
    if (!activeInboxNoteId || !collectionNotes.some((item) => item.id === activeInboxNoteId)) {
      setActiveInboxNoteId(collectionNotes[0].id);
    }
  }, [tab, selectedCollectionId, notes, noteModalOpen, inlineEditNoteId, replyingNoteId, activeInboxNoteId]);

  useEffect(() => {
    if (tab !== "notes" || !selectedCollectionId || noteModalOpen || inlineEditNoteId || replyingNoteId) return;

    function isEditableTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) return false;
      const tagName = target.tagName.toLowerCase();
      return target.isContentEditable || ["input", "textarea", "select", "button"].includes(tagName);
    }

    function focusNoteCard(noteId: string) {
      setActiveInboxNoteId(noteId);
      const target = document.querySelector<HTMLElement>(`.research-log-card[data-note-id="${noteId}"]:not(.in-stack-preview)`);
      target?.focus();
      target?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isEditableTarget(event.target)) return;

      const visibleCards = Array.from(
        document.querySelectorAll<HTMLElement>(".research-log-card[data-note-id]:not(.in-stack-preview)")
      );
      const visibleIds = visibleCards.map((item) => item.dataset.noteId || "").filter(Boolean);
      if (visibleIds.length === 0) return;
      const currentId = activeInboxNoteId && visibleIds.includes(activeInboxNoteId) ? activeInboxNoteId : visibleIds[0];
      const currentIndex = Math.max(visibleIds.indexOf(currentId), 0);
      const activeNote = notes.find((item) => item.id === currentId) || null;

      if (event.shiftKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setFoldedNoteIds((current) => {
          const allFolded = visibleIds.every((id) => current.has(id));
          const next = new Set(current);
          if (allFolded) {
            visibleIds.forEach((id) => next.delete(id));
          } else {
            visibleIds.forEach((id) => next.add(id));
          }
          return next;
        });
        return;
      }
      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        const delta = event.key === "j" ? 1 : -1;
        const nextIndex = Math.min(Math.max(currentIndex + delta, 0), visibleIds.length - 1);
        focusNoteCard(visibleIds[nextIndex]);
        return;
      }
      if (event.key === "/") {
        event.preventDefault();
        noteSearchInputRef.current?.focus();
        noteSearchInputRef.current?.select();
        return;
      }
      if (event.key === "n") {
        event.preventDefault();
        openCreateNoteModal();
        return;
      }
      if (!activeNote) return;
      if (event.key === "Enter" || event.key === "e") {
        event.preventDefault();
        openEditNoteModal(activeNote);
        return;
      }
      if (event.key === "r") {
        event.preventDefault();
        setReplyingNoteId((current) => current === activeNote.id ? null : activeNote.id);
        setReplyDrafts((current) => ({ ...current, [activeNote.id]: current[activeNote.id] || "" }));
        return;
      }
      if (event.key === "p") {
        event.preventDefault();
        void handleToggleNotePin(activeNote);
        return;
      }
      if (event.key === "c") {
        const iterationState = noteIterationState(activeNote.id);
        if (!iterationState.iterationId) return;
        event.preventDefault();
        setCollapsedIterationIds((current) => {
          const next = new Set(current);
          if (next.has(iterationState.iterationId!)) next.delete(iterationState.iterationId!);
          else next.add(iterationState.iterationId!);
          return next;
        });
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [tab, selectedCollectionId, noteModalOpen, activeInboxNoteId, notes, inlineEditNoteId, replyingNoteId]);

  const referenceUsageMap = useMemo(() => {
    const map = new Map<string, { claimCount: number; sectionCount: number; noteCount: number; total: number }>();
    for (const ref of references) {
      const claimCount = paperClaims.filter((item) => item.reference_ids.includes(ref.id)).length;
      const sectionCount = paperSections.filter((item) => item.reference_ids.includes(ref.id)).length;
      const noteCount = notes.filter((item) => item.linked_reference_ids.includes(ref.id)).length;
      map.set(ref.id, { claimCount, sectionCount, noteCount, total: claimCount + sectionCount + noteCount });
    }
    return map;
  }, [references, paperClaims, paperSections, notes]);

  const sortedReferences = useMemo(() => {
    const sorted = [...references];
    if (refSortKey === "title") sorted.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
    else if (refSortKey === "connections") sorted.sort((a, b) => (referenceUsageMap.get(b.id)?.total ?? 0) - (referenceUsageMap.get(a.id)?.total ?? 0));
    else sorted.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return sorted;
  }, [references, refSortKey, referenceUsageMap]);

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
    if (!semanticSearch && bibliographySearch.trim()) {
      const query = bibliographySearch.trim().toLowerCase();
      items = items.filter((item) =>
        item.title.toLowerCase().includes(query) ||
        item.authors.some((author) => author.toLowerCase().includes(query))
      );
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
  }, [
    bibliography,
    selectedBibliographyCollectionId,
    selectedBibliographyCollectionPaperIds,
    bibliographyTagFilter,
    bibliographyStatusFilter,
    semanticSearch,
    bibliographySearch,
    bibSortKey,
    bibSortDir,
  ]);

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
    setInlinePaperTitle(collectionDetail?.target_output_title || "");
    setInlinePaperMotivation(collectionDetail?.paper_motivation || "");
    setInlinePaperVenue(collectionDetail?.target_venue || "");
    setInlinePaperOverleaf(collectionDetail?.overleaf_url || "");
    setInlinePaperStatus(collectionDetail?.output_status || "not_started");
    setInlinePaperRegistration(collectionDetail?.registration_deadline || "");
    setInlinePaperSubmission(collectionDetail?.submission_deadline || "");
    setInlinePaperDecision(collectionDetail?.decision_date || "");
    setEditingPaperTitle(false);
    setEditingPaperVenue(false);
    setEditingPaperOverleaf(false);
    setEditingPaperStatus(false);
    setEditingPaperRegistration(false);
    setEditingPaperSubmission(false);
    setEditingPaperDecision(false);
    setEditingPaperMotivation(false);
    setStudyIterations(collectionDetail?.study_iterations || []);
    setStudyResults(collectionDetail?.study_results || []);
    setResultComparison(null);
    setPaperAuthors(collectionDetail?.paper_authors || []);
    setPaperQuestions(collectionDetail?.paper_questions || []);
    setPaperClaims(collectionDetail?.paper_claims || []);
    setPaperSections(collectionDetail?.paper_sections || []);
    setPaperDirty(false);
    paperSyncedRef.current = false;
    setInlineStudyTitle(collectionDetail?.title || "");
    setInlineStudyFocus(collectionDetail?.description || collectionDetail?.hypothesis || "");
    setEditingStudyTitle(false);
    setEditingStudyFocus(false);
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

  useEffect(() => {
    if (bibliographyOnly || !researchTourActive || !researchTourStepId) return;
    if (researchTourStepId === "research-study-grid") {
      if (selectedCollectionId) {
        setSelectedCollectionId(null);
        setTab("overview");
      }
      return;
    }
    if (["study-inbox-tab", "study-references-tab", "study-paper-tab", "study-iterations-tab"].includes(researchTourStepId)) {
      if (!selectedCollectionId) {
        const firstStudy = filteredActiveCollections[0] ?? filteredArchivedCollections[0] ?? null;
        if (firstStudy) {
          setSelectedCollectionId(firstStudy.id);
          setTab("overview");
        }
        return;
      }
      if (researchTourStepId === "study-inbox-tab") setTab("notes");
      if (researchTourStepId === "study-references-tab") setTab("references");
      if (researchTourStepId === "study-paper-tab") setTab("paper");
      if (researchTourStepId === "study-iterations-tab") setTab("iterations");
    }
  }, [
    bibliographyOnly,
    researchTourActive,
    researchTourStepId,
    selectedCollectionId,
    filteredActiveCollections,
    filteredArchivedCollections,
  ]);

  // Ctrl+F on the studies grid → open study command palette
  const showSpaceHome = !bibliographyOnly && !selectedCollectionId;
  useEffect(() => {
    function handleStudyPaletteKey(e: KeyboardEvent) {
      if (!showSpaceHome) return;
      // Skip if a graph modal is open (it has its own Ctrl+F handler)
      if (document.querySelector(".bibliography-graph-modal")) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        e.stopImmediatePropagation();
        setStudyPaletteOpen(true);
        setStudyPaletteQuery("");
        setStudyPaletteIndex(0);
      }
    }
    window.addEventListener("keydown", handleStudyPaletteKey, true);
    return () => window.removeEventListener("keydown", handleStudyPaletteKey, true);
  }, [showSpaceHome]);

  // Ctrl+F on files tab → open file search palette
  const filesTabActive = !bibliographyOnly && !!selectedCollectionId && tab === "files";
  useEffect(() => {
    if (!filesTabActive) return;
    function handleFileSearchKey(e: KeyboardEvent) {
      // Skip if a graph modal is open
      if (document.querySelector(".bibliography-graph-modal")) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        e.stopImmediatePropagation();
        setFileSearchOpen(true);
      }
    }
    window.addEventListener("keydown", handleFileSearchKey, true);
    return () => window.removeEventListener("keydown", handleFileSearchKey, true);
  }, [filesTabActive]);

  useEffect(() => {
    if (studyPaletteOpen) studyPaletteInputRef.current?.focus();
  }, [studyPaletteOpen]);

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

  // Keyboard shortcuts for study view
  useEffect(() => {
    if (bibliographyOnly || !selectedCollectionId) return;
    const tabKeys: Record<string, Tab> = { "1": "overview", "2": "notes", "3": "references", "4": "paper", "5": "chat", "6": "iterations", "7": "files" };
    function handleStudyKeys(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const inInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable;
      if (inInput) return;
      if (e.key in tabKeys) {
        e.preventDefault();
        setTab(tabKeys[e.key]);
        return;
      }
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        setTab("notes");
        setTimeout(() => quickLogInputRef.current?.focus(), 50);
        return;
      }
    }
    window.addEventListener("keydown", handleStudyKeys);
    return () => window.removeEventListener("keydown", handleStudyKeys);
  }, [bibliographyOnly, selectedCollectionId]);

  // Auto-save paper after 3s of inactivity when dirty
  useEffect(() => {
    if (!paperDirty || !selectedProjectId || !selectedCollectionId || saving) return;
    const timer = setTimeout(() => {
      void persistPaperWorkspace(undefined, { successMessage: "Auto-saved." });
    }, 3000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperDirty, paperTitle, paperMotivation, paperVenue, paperOverleafUrl, paperStatus, paperRegistrationDeadline, paperSubmissionDeadline, paperDecisionDate, paperAuthors, paperQuestions, paperClaims, paperSections]);

  useEffect(() => {
    if (!noteModalOpen) return;
    function handleNoteModalEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      closeNoteModal();
    }
    window.addEventListener("keydown", handleNoteModalEscape);
    return () => window.removeEventListener("keydown", handleNoteModalEscape);
  }, [
    noteModalOpen,
    noteTitle,
    noteContent,
    noteType,
    noteCollectionId,
    noteLane,
    notePinned,
    noteStarred,
    noteReferenceIds,
    noteFileIds,
    noteLinkedNoteIds,
  ]);

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
    const response = await api.listResearchCollections(projectId, { space_id: activeResearchSpaceId, page_size: 100 });
    setCollections(response.items);
    if (bibliographyOnly && !bulkResearchTargetCollectionId && response.items.length > 0) {
      setBulkResearchTargetCollectionId(response.items[0].id);
    }
  }

  async function loadMembers(projectId = selectedProjectId) {
    if (!projectId || !hasProjectContext) {
      setMembers([]);
      return;
    }
    const response = await api.listMembers(projectId);
    setMembers(response.items.filter((item: Member) => item.is_active));
  }

  async function loadDiscoverableUsers() {
    const response = await api.listUserDiscovery(1, 100);
    setDiscoverableUsers(response.items.filter((item) => item.can_access_research));
  }

  async function loadSupportData(projectId = selectedProjectId) {
    if (!projectId) {
      setAllReferences([]);
      setProjectDocuments([]);
      setProjectMeetings([]);
      setWps([]);
      setTasks([]);
      setDeliverables([]);
      return;
    }
    const refsRes = await api.listResearchReferences(projectId, { space_id: activeResearchSpaceId, page_size: 100 });
    setAllReferences(refsRes.items);
    if (!hasProjectContext) {
      setProjectDocuments([]);
      setProjectMeetings([]);
      setWps([]);
      setTasks([]);
      setDeliverables([]);
      return;
    }
    const [docsRes, meetingsRes, wpsRes, tasksRes, deliverablesRes] = await Promise.all([
      api.listDocuments(projectId),
      api.listMeetings(projectId),
      api.listWorkPackages(projectId),
      api.listTasks(projectId),
      api.listDeliverables(projectId),
    ]);
    setProjectDocuments(docsRes.items);
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
    const response = await api.listBibliographyTags({ page_size: 100 });
    setBibliographyTagOptions(response.items);
  }

  async function loadCollectionDetail(collectionId: string, projectId = selectedProjectId) {
    if (!projectId || !collectionId) return;
    const detail = await api.getResearchCollection(projectId, collectionId, activeResearchSpaceId);
    setCollectionDetail(detail);
  }

  async function loadReferences(collectionId: string | null, projectId = selectedProjectId) {
    if (!projectId) return;
    const opts: Record<string, string> = {};
    if (collectionId) opts.collection_id = collectionId;
    if (refStatusFilter) opts.reading_status = refStatusFilter;
    if (refSearch) opts.q = refSearch;
    const response = await api.listResearchReferences(projectId, { ...opts, space_id: activeResearchSpaceId, page_size: 100 });
    setReferences(response.items);
  }

  async function loadNotes(collectionId: string | null, projectId = selectedProjectId) {
    if (!projectId) return;
    const opts: Record<string, string> = {};
    if (collectionId) opts.collection_id = collectionId;
    if (noteLaneFilter !== "") opts.lane = noteLaneFilter === "__none__" ? "" : noteLaneFilter;
    const response = await api.listResearchNotes(projectId, { ...opts, space_id: activeResearchSpaceId, page_size: 100 });
    setNotes(response.items);
  }

  async function loadNoteTags(projectId = selectedProjectId, collectionId = noteCollectionId || selectedCollectionId) {
    if (!projectId) {
      setNoteTagOptions([]);
      return;
    }
    const response = await api.listResearchNoteTags(projectId, {
      space_id: activeResearchSpaceId || undefined,
      collection_id: collectionId || undefined,
    });
    setNoteTagOptions(response.items);
  }

  async function loadNoteTemplates(projectId = selectedProjectId, query = "") {
    if (!projectId) {
      setNoteTemplates([]);
      return;
    }
    const response = await api.listResearchNoteTemplates(projectId, { q: query || undefined, page_size: 100 });
    setNoteTemplates(response.items);
  }

  async function loadStudyFiles(collectionId: string | null, projectId = selectedProjectId) {
    if (!projectId || !collectionId) {
      setStudyFiles([]);
      return;
    }
    const response = await api.listStudyFiles(projectId, collectionId, { space_id: activeResearchSpaceId, page_size: 100 });
    setStudyFiles(response.items);
  }

  async function refreshWorkspace(projectId = selectedProjectId, collectionId = selectedCollectionId) {
    if (!projectId) return;
    if (!collectionId) {
      setReferences([]);
      setNotes([]);
      setStudyFiles([]);
      setCollectionDetail(null);
      return;
    }
    const tasksToRun: Promise<unknown>[] = [
      loadReferences(collectionId, projectId),
      loadNotes(collectionId, projectId),
      loadStudyFiles(collectionId, projectId),
      loadCollectionDetail(collectionId, projectId),
    ];
    await Promise.all(tasksToRun);
  }

  useEffect(() => {
    if (bibliographyOnly) {
      setLoading(true);
      setError("");
      setStatus("");
      Promise.all([
        loadBibliographyCollections(),
        activeResearchSpaceId ? loadCollections(selectedProjectId) : Promise.resolve(),
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
      setStudyFiles([]);
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
    setCollectionDetail(null);
    Promise.all([
      loadBibliographyCollections(),
      loadCollections(selectedProjectId),
      loadMembers(selectedProjectId),
      loadSupportData(selectedProjectId),
      loadBibliography(selectedProjectId),
      loadBibliographyTags(),
    ])
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load research workspace");
      })
      .finally(() => setLoading(false));
  }, [selectedProjectId, bibliographyOnly, currentProject?.project_kind, activeResearchSpaceId, hasProjectContext]);

  useEffect(() => {
    if (bibliographyOnly) return;
    if (!selectedCollectionId) return;
    if (collections.some((item) => item.id === selectedCollectionId)) return;
    setSelectedCollectionId(null);
  }, [bibliographyOnly, collections, selectedCollectionId]);

  useEffect(() => {
    if (bibliographyOnly) return;
    if (!selectedProjectId) return;
    if (!selectedCollectionId) {
      setReferences([]);
      setNotes([]);
      setStudyFiles([]);
      setCollectionDetail(null);
      return;
    }
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
    if (!noteModalOpen) return;
    Promise.all([loadNoteTags(), loadNoteTemplates()]).catch((err) => {
      console.error(err);
    });
  }, [noteModalOpen, selectedProjectId, activeResearchSpaceId, noteCollectionId, selectedCollectionId]);

  useEffect(() => {
    if (!memberModalOpen || hasProjectContext) return;
    loadDiscoverableUsers().catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    });
  }, [memberModalOpen, hasProjectContext]);

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
    setCollectionSpaceIds(activeResearchSpaceId ? [activeResearchSpaceId] : []);
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
    setNotePinned(false);
    setNoteStarred(false);
    setNoteReferenceIds([]);
    setNoteFileIds([]);
    setNoteLinkedNoteIds([]);
    setNoteTemplateSearch("");
    setNoteTemplateName("");
    setNoteTemplateSystem(false);
    setEditingNoteId(null);
  }

  function setInitialNoteModalSnapshot(snapshot: NoteModalSnapshot) {
    noteModalInitialSnapshotRef.current = buildNoteModalSnapshot(snapshot);
  }

  function currentNoteModalSnapshot(): NoteModalSnapshot {
    return buildNoteModalSnapshot({
      title: noteTitle,
      content: noteContent,
      noteType,
      collectionId: noteCollectionId,
      lane: noteLane,
      pinned: notePinned,
      starred: noteStarred,
      referenceIds: noteReferenceIds,
      fileIds: noteFileIds,
      linkedNoteIds: noteLinkedNoteIds,
    });
  }

  function noteModalHasUnsavedChanges() {
    if (!noteModalOpen) return false;
    const initial = noteModalInitialSnapshotRef.current;
    if (!initial) return false;
    return !noteModalSnapshotsEqual(initial, currentNoteModalSnapshot());
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
    setAutoLinkAfterCreate(Boolean(selectedCollectionId && !bibliographyOnly));
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
    setCollectionSpaceIds(collectionDetail.space_ids || []);
    setCollectionModalOpen(true);
  }

  function openEditCollectionFromCard(item: ResearchCollection) {
    setCollectionModalMode("edit");
    setEditingCollectionId(item.id);
    setCollectionTitle(item.title);
    setCollectionDescription(item.description || item.hypothesis || "");
    setCollectionStatus(item.status);
    setCollectionSpaceIds(item.space_ids || []);
    setCollectionModalOpen(true);
  }

  function openStudyFromCard(collectionId: string) {
    setSelectedCollectionId(collectionId);
    setTab("overview");
  }

  async function handleInlineStudyHeaderSave(field: "title" | "focus") {
    if (!selectedProjectId || !selectedCollectionId || !collectionDetail) return;
    const nextTitle = field === "title" ? inlineStudyTitle.trim() : collectionDetail.title;
    const nextFocus = field === "focus" ? inlineStudyFocus.trim() : (collectionDetail.description || collectionDetail.hypothesis || "");
    if (!nextTitle) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError("");
    setStatus("");
    try {
      await api.updateResearchCollection(selectedProjectId, selectedCollectionId, {
        title: nextTitle,
        description: nextFocus || null,
        status: collectionDetail.status,
        space_ids: collectionDetail.space_ids || [],
      }, activeResearchSpaceId);
      await Promise.all([loadCollections(), loadCollectionDetail(selectedCollectionId)]);
      setStatus("Study updated.");
      if (field === "title") setEditingStudyTitle(false);
      if (field === "focus") setEditingStudyFocus(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update study.");
    } finally {
      setSaving(false);
    }
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

  function openCreateNoteModal(options?: { seedFromQuickLog?: boolean; noteType?: string }) {
    if (!selectedCollectionId) {
      setError("Select a study first.");
      return;
    }
    const nextSnapshot = buildNoteModalSnapshot({
      title: options?.seedFromQuickLog ? (quickLogTitle.trim() || deriveLogTitle(quickLogContent)) : "",
      content: options?.seedFromQuickLog ? quickLogContent : "",
      noteType: options?.noteType || "observation",
      collectionId: selectedCollectionId,
      lane: options?.seedFromQuickLog ? quickLogLane : "",
      pinned: false,
      starred: false,
      referenceIds: options?.seedFromQuickLog ? [...quickLogRefIds] : [],
      fileIds: options?.seedFromQuickLog ? [...quickLogFileIds] : [],
      linkedNoteIds: [],
    });
    setNoteModalMode("create");
    setEditingNoteId(null);
    setNoteCollectionId(nextSnapshot.collectionId);
    setNoteTitle(nextSnapshot.title);
    setNoteContent(nextSnapshot.content);
    setNoteLane(nextSnapshot.lane);
    setNotePinned(nextSnapshot.pinned);
    setNoteStarred(nextSnapshot.starred);
    setNoteType(nextSnapshot.noteType);
    setNoteReferenceIds(nextSnapshot.referenceIds);
    setNoteFileIds(nextSnapshot.fileIds);
    setNoteLinkedNoteIds(nextSnapshot.linkedNoteIds);
    setInitialNoteModalSnapshot(nextSnapshot);
    setNoteModalOpen(true);
    void loadNoteTemplates();
  }

  function openEditNoteModal(note: ResearchNote) {
    const nextSnapshot = buildNoteModalSnapshot({
      title: note.title,
      content: note.content,
      noteType: note.note_type,
      collectionId: note.collection_id || selectedCollectionId || "",
      lane: note.lane || "",
      pinned: note.pinned,
      starred: note.starred,
      referenceIds: note.linked_reference_ids,
      fileIds: note.linked_file_ids || [],
      linkedNoteIds: note.linked_note_ids || [],
    });
    setNoteModalMode("edit");
    setEditingNoteId(note.id);
    setNoteTitle(nextSnapshot.title);
    setNoteContent(nextSnapshot.content);
    setNoteType(nextSnapshot.noteType);
    setNoteCollectionId(nextSnapshot.collectionId);
    setNoteLane(nextSnapshot.lane);
    setNotePinned(nextSnapshot.pinned);
    setNoteStarred(nextSnapshot.starred);
    setNoteReferenceIds(nextSnapshot.referenceIds);
    setNoteFileIds(nextSnapshot.fileIds);
    setNoteLinkedNoteIds(nextSnapshot.linkedNoteIds);
    setInitialNoteModalSnapshot(nextSnapshot);
    setNoteModalOpen(true);
    void loadNoteTemplates();
  }

  function openIndexNote() {
    if (!selectedCollectionId) return;
    const existingIndex = notes.find((item) => item.collection_id === selectedCollectionId && isIndexNote(item));
    if (existingIndex) {
      openEditNoteModal(existingIndex);
      return;
    }
    openCreateNoteModal({ noteType: "index" });
  }

  function applyNoteTemplate(template: ResearchNoteTemplate) {
    const resolvedTitle = resolveTemplateTokens(template.title || "", {
      userName: currentUser.display_name,
      studyTitle: collectionDetail?.title || collections.find((item) => item.id === noteCollectionId)?.title || "Study",
      spaceTitle: activeResearchSpace?.title || "Research",
    });
    const resolvedContent = resolveTemplateTokens(template.content || "", {
      userName: currentUser.display_name,
      studyTitle: collectionDetail?.title || collections.find((item) => item.id === noteCollectionId)?.title || "Study",
      spaceTitle: activeResearchSpace?.title || "Research",
    });
    setNoteTitle(resolvedTitle);
    setNoteContent(resolvedContent);
    setNoteType(template.note_type || "observation");
    setNoteLane(template.lane || "");
    setNotePinned(false);
    setNoteStarred(false);
    setNoteReferenceIds(collectResolvedReferenceIds(resolvedContent));
    setNoteFileIds(collectResolvedFileIds(resolvedContent, []));
    setNoteLinkedNoteIds(collectResolvedLinkedNoteIds(resolvedContent, editingNoteId));
    setNoteTemplateLibraryOpen(false);
    setStatus(`Template applied: ${template.name}`);
  }

  function openSaveTemplateModal() {
    setNoteTemplateName(noteTitle.trim() || deriveLogTitle(noteContent) || "New Template");
    setNoteTemplateSystem(false);
    setNoteTemplateSaveOpen(true);
  }

  function closeNoteModal(force = false) {
    if (!force && noteModalHasUnsavedChanges() && typeof window !== "undefined") {
      const confirmed = window.confirm("Discard unsaved changes?");
      if (!confirmed) return;
    }
    setNoteModalOpen(false);
    setNoteTemplateLibraryOpen(false);
    setNoteTemplateSaveOpen(false);
    noteModalInitialSnapshotRef.current = null;
  }

  function startInlineEdit(note: ResearchNote) {
    setInlineEditNoteId(note.id);
    setInlineEditTitle(note.title);
    setInlineEditContent(note.content);
    setInlineEditLane(note.lane || "");
    setInlineEditPinned(note.pinned);
    setInlineEditStarred(note.starred);
    setInlineEditRefIds([...note.linked_reference_ids]);
    setInlineEditFileIds([...(note.linked_file_ids || [])]);
    setInlineEditLinkedNoteIds([...(note.linked_note_ids || [])]);
  }

  function cancelInlineEdit() {
    setInlineEditNoteId(null);
    setInlineEditTitle("");
    setInlineEditContent("");
    setInlineEditLane("");
    setInlineEditPinned(false);
    setInlineEditStarred(false);
    setInlineEditRefIds([]);
    setInlineEditFileIds([]);
    setInlineEditLinkedNoteIds([]);
    closeMention();
  }

  async function handleInlineEditSave(noteId: string) {
    if (!selectedProjectId || !inlineEditTitle.trim() || !inlineEditContent.trim()) return;
    setSaving(true);
    setError("");
    try {
      const existingNote = notes.find((item) => item.id === noteId);
      const linkedNoteIds = collectResolvedLinkedNoteIds(inlineEditContent, noteId);
      await api.updateResearchNote(selectedProjectId, noteId, {
        title: inlineEditTitle.trim(),
        content: inlineEditContent.trim(),
        lane: inlineEditLane || null,
        pinned: inlineEditPinned,
        starred: inlineEditStarred,
        note_type: existingNote?.note_type || "observation",
        linked_file_ids: inlineEditFileIds,
        linked_note_ids: linkedNoteIds,
      }, activeResearchSpaceId);
      await api.setNoteReferences(selectedProjectId, noteId, inlineEditRefIds, activeResearchSpaceId);
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

  function deriveMarkdownTags(content: string): string[] {
    const scrubbed = content
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/`[^`\n]*`/g, " ");
    const tags = new Map<string, string>();
    for (const match of scrubbed.matchAll(/(^|[\s(>])#([A-Za-z0-9][A-Za-z0-9_/-]*)/g)) {
      const label = (match[2] || "").trim();
      if (!label) continue;
      const key = label.toLowerCase();
      if (!tags.has(key)) tags.set(key, label);
    }
    return Array.from(tags.values());
  }

  function handleOpenLinkedReference(referenceId: string) {
    const ref = references.find((item) => item.id === referenceId);
    if (!ref) return;
    setTab("references");
    setRefSearch(ref.title);
    openEditReferenceModal(ref);
  }

  function handleOpenReferenceByLabel(label: string, referenceIds: string[]) {
    const ref = references.find((item) => referenceIds.includes(item.id) && formatRefLabel(item) === label)
      || references.find((item) => referenceIds.includes(item.id));
    if (!ref) return;
    handleOpenLinkedReference(ref.id);
  }

  function resolveLinkedReferenceByLabel(label: string, referenceIds?: string[]): ResearchReference | null {
    const normalized = label.trim().toLowerCase();
    if (!normalized) return null;
    if (referenceIds && referenceIds.length > 0) {
      return references.find((item) => referenceIds.includes(item.id) && formatRefLabel(item).trim().toLowerCase() === normalized)
        || references.find((item) => referenceIds.includes(item.id))
        || null;
    }
    return references.find((item) => formatRefLabel(item).trim().toLowerCase() === normalized) || null;
  }

  function resolveLinkedNoteById(noteId: string): ResearchNote | null {
    return notes.find((item) => item.id === noteId) || null;
  }

  function resolveLinkedNoteByLabel(label: string, noteIds?: string[]): ResearchNote | null {
    const normalized = label.trim().toLowerCase();
    if (!normalized) return null;
    if (noteIds && noteIds.length > 0) {
      return notes.find((item) => noteIds.includes(item.id) && item.title.trim().toLowerCase() === normalized)
        || notes.find((item) => noteIds.includes(item.id))
        || null;
    }
    return notes.find((item) => item.title.trim().toLowerCase() === normalized) || null;
  }

  function collectResolvedLinkedNoteIds(content: string, currentNoteId?: string | null): string[] {
    const resolved = new Set<string>();
    extractMarkdownNoteLabels(content).forEach((label) => {
      const note = resolveLinkedNoteByLabel(label);
      if (note && note.id !== currentNoteId) resolved.add(note.id);
    });
    return Array.from(resolved);
  }

  function collectResolvedReferenceIds(content: string): string[] {
    const resolved = new Set<string>();
    extractMarkdownReferenceLabels(content).forEach((label) => {
      const ref = resolveLinkedReferenceByLabel(label);
      if (ref) resolved.add(ref.id);
    });
    return Array.from(resolved);
  }

  function collectResolvedFileIds(content: string, existingIds: string[]): string[] {
    const resolved = new Set<string>();
    extractMarkdownFileLabels(content).forEach((label) => {
      const file = resolveLinkedFileByLabel(label, existingIds);
      if (file) resolved.add(file.id);
    });
    return Array.from(resolved);
  }

  function handleOpenLinkedNote(noteId: string) {
    const note = resolveLinkedNoteById(noteId);
    if (!note) return;
    setTab("notes");
    setSelectedCollectionId(note.collection_id || selectedCollectionId);
    setActiveInboxNoteId(note.id);
    window.setTimeout(() => {
      const target = document.querySelector<HTMLElement>(`.research-log-card[data-note-id="${note.id}"]`);
      target?.scrollIntoView({ block: "center", behavior: "smooth" });
      target?.focus();
    }, 80);
  }

  function handleOpenIteration(iterationId: string) {
    setTab("iterations");
    setExpandedIterationId(iterationId);
  }

  function handleOpenLinkedNoteByLabel(label: string, noteIds?: string[]) {
    const note = resolveLinkedNoteByLabel(label, noteIds);
    if (!note) return;
    handleOpenLinkedNote(note.id);
  }

  function resolveLinkedFileByLabel(label: string, fileIds: string[]): ResearchStudyFile | null {
    const normalized = label.trim().toLowerCase();
    return studyFiles.find((item) => fileIds.includes(item.id) && item.original_filename.trim().toLowerCase() === normalized)
      || studyFiles.find((item) => fileIds.includes(item.id))
      || null;
  }

  function handleOpenLinkedFileByLabel(label: string, fileIds: string[]) {
    const file = resolveLinkedFileByLabel(label, fileIds);
    if (!file) return;
    void handleOpenStudyFile(file);
  }

  function handleFilterByTag(tag: string) {
    setTab("notes");
    setNoteSearchQuery(`#${tag}`);
  }

  function insertReferenceIntoNoteEditor(ref: ResearchReference) {
    const token = `%[${formatRefLabel(ref)}] `;
    if (noteEditorRef.current) {
      noteEditorRef.current.chain().focus().insertContent(token).run();
    } else {
      setNoteContent((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}${token}`);
    }
    setNoteReferenceIds((current) => current.includes(ref.id) ? current : [...current, ref.id]);
  }

  const mentionResults = useMemo(() => {
    if (!mentionOpen) return [];
    if (mentionTrigger === "%") {
      if (!mentionQuery) return references.slice(0, 6);
      const q = mentionQuery.toLowerCase();
      return references
        .filter((ref) =>
          ref.title.toLowerCase().includes(q) ||
          ref.authors.some((a) => a.toLowerCase().includes(q)) ||
          (ref.year && String(ref.year).includes(q))
        )
        .slice(0, 6);
    }
    const members = collectionDetail?.members || [];
    if (!mentionQuery) return members.slice(0, 6);
    const q = mentionQuery.toLowerCase();
    return members
      .filter((member) =>
        member.member_name.toLowerCase().includes(q) ||
        memberMentionHandle(member.member_name).includes(q) ||
        (member.role || "").toLowerCase().includes(q)
      )
      .slice(0, 6);
  }, [mentionOpen, mentionQuery, mentionTrigger, references, collectionDetail]);

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

  function openMention(textarea: HTMLTextAreaElement, trigger: "@" | "%", target: "composer" | "inline" | "reply" | "modal", replyNoteId?: string | null) {
    const coords = getTextareaCaretCoords(textarea);
    setMentionTrigger(trigger);
    setMentionTarget(target);
    setMentionReplyNoteId(target === "reply" ? (replyNoteId || null) : null);
    setMentionAnchor(coords);
    setMentionCursorStart(textarea.selectionStart);
    setMentionQuery("");
    setMentionActiveIndex(0);
    setMentionOpen(true);
  }

  function closeMention() {
    setMentionOpen(false);
    setMentionTrigger("%");
    setMentionQuery("");
    setMentionActiveIndex(0);
    setMentionAnchor(null);
    setMentionReplyNoteId(null);
  }

  function selectMention(item: ResearchReference | ResearchCollectionMember) {
    const isReference = mentionTrigger === "%";
    const label = isReference
      ? `%[${formatRefLabel(item as ResearchReference)}]`
      : `@${memberMentionHandle((item as ResearchCollectionMember).member_name)}`;
    if (mentionTarget === "composer") {
      const before = quickLogContent.substring(0, mentionCursorStart - 1);
      const after = quickLogContent.substring(mentionCursorStart + mentionQuery.length);
      setQuickLogContent(before + label + " " + after);
      if (isReference) {
        const ref = item as ResearchReference;
        setQuickLogRefIds((current) => current.includes(ref.id) ? current : [...current, ref.id]);
      }
    } else if (mentionTarget === "inline") {
      const before = inlineEditContent.substring(0, mentionCursorStart - 1);
      const after = inlineEditContent.substring(mentionCursorStart + mentionQuery.length);
      setInlineEditContent(before + label + " " + after);
      if (isReference) {
        const ref = item as ResearchReference;
        setInlineEditRefIds((current) => current.includes(ref.id) ? current : [...current, ref.id]);
      }
    } else if (mentionTarget === "modal") {
      const before = noteContent.substring(0, mentionCursorStart - 1);
      const after = noteContent.substring(mentionCursorStart + mentionQuery.length);
      setNoteContent(before + label + " " + after);
      if (isReference) {
        const ref = item as ResearchReference;
        setNoteReferenceIds((current) => current.includes(ref.id) ? current : [...current, ref.id]);
      }
    } else if (mentionReplyNoteId) {
      const currentText = replyDrafts[mentionReplyNoteId] || "";
      const before = currentText.substring(0, mentionCursorStart - 1);
      const after = currentText.substring(mentionCursorStart + mentionQuery.length);
      setReplyDrafts((current) => ({ ...current, [mentionReplyNoteId]: before + label + " " + after }));
      if (isReference) {
        const ref = item as ResearchReference;
        setReplyRefIds((current) => ({
          ...current,
          [mentionReplyNoteId]: (current[mentionReplyNoteId] || []).includes(ref.id)
            ? (current[mentionReplyNoteId] || [])
            : [...(current[mentionReplyNoteId] || []), ref.id],
        }));
      }
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

  function handleContentChange(
    value: string,
    cursorPos: number,
    textarea: HTMLTextAreaElement,
    target: "composer" | "inline" | "reply" | "modal",
    options?: { replyNoteId?: string | null },
  ) {
    if (target === "composer") {
      setQuickLogContent(value);
    } else if (target === "inline") {
      setInlineEditContent(value);
    } else if (target === "modal") {
      setNoteContent(value);
    } else if (options?.replyNoteId) {
      setReplyDrafts((current) => ({ ...current, [options.replyNoteId!]: value }));
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

    if (cursorPos > 0 && (value[cursorPos - 1] === "@" || value[cursorPos - 1] === "%")) {
      const trigger = value[cursorPos - 1] as "@" | "%";
      const charBefore = cursorPos > 1 ? value[cursorPos - 2] : " ";
      if (charBefore === " " || charBefore === "\n" || cursorPos === 1) {
        openMention(textarea, trigger, target, options?.replyNoteId);
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
    file_ids: [],
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
    file_ids: [],
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
      file_ids: [],
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
    return {
      id: crypto.randomUUID(),
      title: "",
      question_ids: [],
      claim_ids: [],
      reference_ids: [],
      note_ids: [],
      result_ids: [],
      file_ids: [],
      status: "not_started",
    };
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
    file_ids: Array.from(new Set([...(iteration.file_ids || []), ...uniqueLogFileIds(iteration.note_ids, notes)])),
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
        file_ids: item.file_ids,
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
        file_ids: item.file_ids,
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
        file_ids: item.file_ids,
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
        file_ids: item.file_ids,
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
      await api.updateResearchCollection(selectedProjectId, selectedCollectionId, payload, activeResearchSpaceId);
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
          space_ids: collectionSpaceIds,
          description: collectionDescription.trim() || undefined,
        }, activeResearchSpaceId);
        await loadCollections();
        setSelectedCollectionId(created.id);
        setStatus("Study created.");
      } else if (editingCollectionId) {
        await api.updateResearchCollection(selectedProjectId, editingCollectionId, {
          title: collectionTitle.trim(),
          space_ids: collectionSpaceIds,
          description: collectionDescription.trim() || null,
          status: collectionStatus,
        }, activeResearchSpaceId);
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
      await api.deleteResearchCollection(selectedProjectId, collectionId, activeResearchSpaceId);
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
      await api.updateResearchCollection(selectedProjectId, collectionId, { status: "archived" }, activeResearchSpaceId);
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
      const detail = await api.auditResearchPaperClaims(selectedProjectId, selectedCollectionId, activeResearchSpaceId);
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
      const detail = await api.buildResearchPaperOutline(selectedProjectId, selectedCollectionId, activeResearchSpaceId);
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
      const detail = await api.draftResearchPaperFromGap(selectedProjectId, selectedCollectionId, activeResearchSpaceId);
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
      const detail = await api.reviewResearchIteration(selectedProjectId, selectedCollectionId, iterationId, activeResearchSpaceId);
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
      const report = await api.compareResearchResults(selectedProjectId, selectedCollectionId, activeResearchSpaceId);
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
    const fileIds = Array.from(new Set(logs.flatMap((item) => item.linked_file_ids)));
    const iteration: ResearchStudyIteration = {
      ...newStudyIteration(),
      title: `Iteration ${studyIterations.length + 1}`,
      start_date: logs[0].created_at.slice(0, 10),
      end_date: logs[logs.length - 1].created_at.slice(0, 10),
      note_ids: logs.map((item) => item.id),
      reference_ids: referenceIds,
      file_ids: fileIds,
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
        await api.createResearchReference(selectedProjectId, buildReferencePayload(), activeResearchSpaceId);
        setStatus("Reference added.");
      } else if (editingReferenceId) {
        await api.updateResearchReference(selectedProjectId, editingReferenceId, buildReferencePayload(), activeResearchSpaceId);
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
      const result = await api.importBibtexReferences(selectedProjectId, bibtexInput.trim(), referenceCollectionId, activeResearchSpaceId);
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
    if (!selectedProjectId || !hasProjectContext || !existingDocumentKey || !referenceCollectionId) return;
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
        await api.createResearchReference(selectedProjectId, payload, activeResearchSpaceId);
      } else if (editingReferenceId) {
        await api.updateResearchReference(selectedProjectId, editingReferenceId, payload, activeResearchSpaceId);
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
    if (!selectedProjectId || !hasProjectContext || !referencePdfFile || !referenceCollectionId) return;
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
        await api.createResearchReference(selectedProjectId, payload, activeResearchSpaceId);
      } else if (editingReferenceId) {
        await api.updateResearchReference(selectedProjectId, editingReferenceId, payload, activeResearchSpaceId);
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
      await api.deleteResearchReference(selectedProjectId, referenceId, activeResearchSpaceId);
      await refreshResearchDataAfterReferenceChange(selectedCollectionId || undefined);
      setStatus("Reference deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete reference");
    }
  }

  async function handleStatusChange(referenceId: string, nextStatus: string) {
    if (!selectedProjectId) return;
    try {
      const updated = await api.updateReferenceStatus(selectedProjectId, referenceId, nextStatus, activeResearchSpaceId);
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
      const result = await api.summarizeReference(selectedProjectId, referenceId, activeResearchSpaceId);
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
    if (!bibliographyTitle.trim() && !bibliographyBibtexInput.trim()) return;
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
        if (!item.attachment_url || options?.allowDuplicate) {
          finalItem = await api.uploadGlobalBibliographyAttachment(
            item.id,
            hasProjectContext ? selectedProjectId : null,
            bibliographyAttachmentFile,
          );
        }
      }
      await Promise.all([loadBibliography(), loadBibliographyTags()]);
      setBibliographyModalOpen(false);
      setBibliographyDuplicateModalOpen(false);
      setBibliographyDuplicateMatches([]);
      resetBibliographyForm();

      // Auto-link to current study if triggered from the import picker
      if (autoLinkAfterCreate && bibliographyModalMode === "create" && selectedCollectionId) {
        setAutoLinkAfterCreate(false);
        try {
          await api.linkBibliographyReference(selectedProjectId, {
            bibliography_reference_id: finalItem.id,
            collection_id: selectedCollectionId,
            reading_status: isStudent ? "to_review" : "unread",
          }, activeResearchSpaceId || undefined);
          await refreshResearchDataAfterReferenceChange(selectedCollectionId);
          await loadBibliography();
          setStatus("Paper added and linked to study.");
        } catch {
          setStatus("Paper added but failed to link to study.");
        }
      } else {
        setAutoLinkAfterCreate(false);
        setStatus(
          finalItem.warning ||
          (bibliographyModalMode === "create"
            ? options?.reuseExistingId
              ? "Existing paper reused."
              : "Paper added."
            : "Paper updated.")
        );
      }
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
        source_project_id: hasProjectContext ? selectedProjectId : null,
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
    if (!bibliographyBibtexInput.trim()) return;
    setSaving(true);
    setError("");
    setStatus("");
    setBibliographyBibtexResult(null);
    try {
      const result = await api.importGlobalBibliographyBibtex(bibliographyBibtexInput.trim(), bibliographyVisibility);
      if (bibliographyAttachmentFile && result.created.length === 1) {
        await api.uploadGlobalBibliographyAttachment(
          result.created[0].id,
          hasProjectContext ? selectedProjectId : null,
          bibliographyAttachmentFile,
        );
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
      }, activeResearchSpaceId || undefined);
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

  async function handleOpenCollectionsGraph() {
    if (!selectedProjectId) return;
    const collectionIds = filteredActiveCollections.map((item) => item.id);
    if (collectionIds.length === 0) return;
    try {
      setLoadingCollectionsGraph(true);
      setError("");
      const graph = await api.buildResearchCollectionsGraph(selectedProjectId, collectionIds);
      setCollectionsGraphData(graph);
      setCollectionsGraphOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load studies graph.");
    } finally {
      setLoadingCollectionsGraph(false);
    }
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
    if (!item.source_project_id && !hasProjectContext) {
      setError("Link a project before ingesting this paper PDF.");
      return;
    }
    try {
      setIngestingBibliographyId(item.id);
      setError("");
      setStatus("");
      const updated = await api.ingestGlobalBibliographyAttachment(
        item.id,
        item.source_project_id || (hasProjectContext ? selectedProjectId : null),
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
    if (!selectedProjectId || !noteContent.trim() || !noteCollectionId) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const resolvedTitle = noteTitle.trim() || deriveLogTitle(noteContent);
      const linkedNoteIds = collectResolvedLinkedNoteIds(noteContent, editingNoteId);
      if (noteModalMode === "create") {
        await api.createResearchNote(selectedProjectId, {
          title: resolvedTitle,
          content: noteContent.trim(),
          collection_id: noteCollectionId,
          lane: noteLane || null,
          pinned: notePinned,
          starred: noteStarred,
          note_type: noteType || "observation",
          linked_reference_ids: noteReferenceIds,
          linked_file_ids: noteFileIds,
          linked_note_ids: linkedNoteIds,
        }, activeResearchSpaceId);
        setStatus("Log added.");
      } else if (editingNoteId) {
        await api.updateResearchNote(selectedProjectId, editingNoteId, {
          title: resolvedTitle,
          content: noteContent.trim(),
          collection_id: noteCollectionId,
          lane: noteLane || null,
          pinned: notePinned,
          starred: noteStarred,
          note_type: noteType || "observation",
          linked_file_ids: noteFileIds,
          linked_note_ids: linkedNoteIds,
        }, activeResearchSpaceId);
        await api.setNoteReferences(selectedProjectId, editingNoteId, noteReferenceIds, activeResearchSpaceId);
        setStatus("Log updated.");
      }
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId), loadSupportData()]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      closeNoteModal(true);
      resetNoteForm(selectedCollectionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save log");
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateNoteTemplate() {
    if (!selectedProjectId || !noteTemplateName.trim()) return;
    setSavingNoteTemplate(true);
    setError("");
    try {
      const created = await api.createResearchNoteTemplate(selectedProjectId, {
        name: noteTemplateName.trim(),
        title: noteTitle.trim() || null,
        content: noteContent,
        lane: noteLane || null,
        note_type: noteType || "observation",
        tags: deriveMarkdownTags(noteContent),
        is_system: currentUser.platform_role === "super_admin" ? noteTemplateSystem : false,
      });
      setNoteTemplates((current) => {
        const next = [created, ...current.filter((item) => item.id !== created.id)];
        return next.sort((a, b) => {
          if (a.is_system !== b.is_system) return a.is_system ? -1 : 1;
          return a.name.localeCompare(b.name);
        });
      });
      setNoteTemplateSaveOpen(false);
      setStatus("Template saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save template.");
    } finally {
      setSavingNoteTemplate(false);
    }
  }

  async function handleDeleteNoteTemplate(templateId: string) {
    if (!selectedProjectId) return;
    setDeletingNoteTemplateId(templateId);
    setError("");
    try {
      await api.deleteResearchNoteTemplate(selectedProjectId, templateId);
      setNoteTemplates((current) => current.filter((item) => item.id !== templateId));
      setStatus("Template deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete template.");
    } finally {
      setDeletingNoteTemplateId(null);
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
        pinned: false,
        starred: false,
        note_type: "observation",
        linked_reference_ids: quickLogRefIds,
        linked_file_ids: quickLogFileIds,
        linked_note_ids: collectResolvedLinkedNoteIds(quickLogContent),
      }, activeResearchSpaceId);
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId), loadSupportData()]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setQuickLogContent("");
      setQuickLogTitle("");
      setQuickLogLane("");
      setQuickLogRefIds([]);
      setQuickLogFileIds([]);
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

  async function handleCreateNoteReply(noteId: string) {
    if (!selectedProjectId) return;
    const content = (replyDrafts[noteId] || "").trim();
    if (!content) return;
    setSubmittingReplyNoteId(noteId);
    setError("");
    try {
      const reply = await api.createResearchNoteReply(
        selectedProjectId,
        noteId,
        { content, linked_reference_ids: replyRefIds[noteId] || [] },
        activeResearchSpaceId,
      );
      setNotes((current) =>
        current.map((note) =>
          note.id === noteId
            ? { ...note, replies: [...(note.replies || []), reply].sort((a, b) => a.created_at.localeCompare(b.created_at)) }
            : note
        )
      );
      setReplyDrafts((current) => ({ ...current, [noteId]: "" }));
      setReplyRefIds((current) => ({ ...current, [noteId]: [] }));
      setReplyingNoteId(null);
      setStatus("Reply added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add reply");
    } finally {
      setSubmittingReplyNoteId(null);
    }
  }

  async function handleUpdateNoteActionItem(actionItemId: string, status: "open" | "doing" | "done") {
    if (!selectedProjectId) return;
    setUpdatingActionItemId(actionItemId);
    setError("");
    try {
      const updated = await api.updateResearchNoteActionItem(selectedProjectId, actionItemId, { status });
      setNotes((current) =>
        current.map((note) =>
          note.action_items?.some((action) => action.id === actionItemId)
            ? {
                ...note,
                action_items: note.action_items.map((action) => (action.id === actionItemId ? updated : action)),
              }
            : note
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update action");
    } finally {
      setUpdatingActionItemId(null);
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!selectedProjectId) return;
    try {
      await api.deleteResearchNote(selectedProjectId, noteId, activeResearchSpaceId);
      await Promise.all([loadCollections(), loadNotes(selectedCollectionId)]);
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setStatus("Log deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete log");
    }
  }

  async function handleToggleNotePin(note: ResearchNote) {
    if (!selectedProjectId) return;
    try {
      await api.updateResearchNote(selectedProjectId, note.id, {
        pinned: !note.pinned,
      }, activeResearchSpaceId);
      await loadNotes(selectedCollectionId);
      setStatus(note.pinned ? "Pin removed." : "Pinned.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update pin");
    }
  }

  async function handleToggleNoteStar(note: ResearchNote) {
    if (!selectedProjectId) return;
    try {
      await api.updateResearchNote(selectedProjectId, note.id, {
        starred: !note.starred,
      }, activeResearchSpaceId);
      await loadNotes(selectedCollectionId);
      setStatus(note.starred ? "Star removed." : "Starred.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update star");
    }
  }

  async function handleUploadStudyFile(file: File, options?: { linkToQuickLog?: boolean; linkToInlineEdit?: boolean; linkToNoteModal?: boolean }): Promise<ResearchStudyFile | null> {
    if (!selectedProjectId || !selectedCollectionId) return null;

    function linkCreatedFile(created: ResearchStudyFile) {
      setStudyFiles((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      if (options?.linkToQuickLog) {
        setQuickLogFileIds((current) => (current.includes(created.id) ? current : [...current, created.id]));
      }
      if (options?.linkToInlineEdit) {
        setInlineEditFileIds((current) => (current.includes(created.id) ? current : [...current, created.id]));
      }
      if (options?.linkToNoteModal) {
        setNoteFileIds((current) => (current.includes(created.id) ? current : [...current, created.id]));
      }
    }

    setUploadingStudyFile(true);
    setError("");
    try {
      const fingerprint = await computeStudyFileFingerprint(file);
      const fingerprintKey = fingerprint ? `${selectedCollectionId}:${fingerprint}` : null;
      const cached = fingerprintKey ? uploadedStudyFileFingerprintMapRef.current.get(fingerprintKey) ?? null : null;
      if (cached && cached.collection_id === selectedCollectionId) {
        linkCreatedFile(cached);
        setStatus("File reused.");
        return cached;
      }

      const created = await api.uploadStudyFile(selectedProjectId, selectedCollectionId, file, activeResearchSpaceId);
      linkCreatedFile(created);
      if (fingerprintKey) {
        uploadedStudyFileFingerprintMapRef.current.set(fingerprintKey, created);
      }
      if (selectedCollectionId) {
        await loadCollectionDetail(selectedCollectionId);
      }
      setStatus("File uploaded.");
      return created;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload file");
      return null;
    } finally {
      setUploadingStudyFile(false);
      if (quickLogFileInputRef.current) quickLogFileInputRef.current.value = "";
      if (inlineEditFileInputRef.current) inlineEditFileInputRef.current.value = "";
      if (noteModalFileInputRef.current) noteModalFileInputRef.current.value = "";
    }
  }

  async function handleOpenStudyFile(file: ResearchStudyFile) {
    if (!selectedProjectId || !selectedCollectionId) return;
    try {
      const blob = await api.getStudyFile(selectedProjectId, selectedCollectionId, file.id, activeResearchSpaceId);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open file");
    }
  }

  async function handleDeleteStudyFile(fileId: string) {
    if (!selectedProjectId || !selectedCollectionId) return;
    try {
      await api.deleteStudyFile(selectedProjectId, selectedCollectionId, fileId, activeResearchSpaceId);
      setStudyFiles((current) => current.filter((item) => item.id !== fileId));
      setQuickLogFileIds((current) => current.filter((id) => id !== fileId));
      setNoteFileIds((current) => current.filter((id) => id !== fileId));
      setInlineEditFileIds((current) => current.filter((id) => id !== fileId));
      setStatus("File deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete file");
    }
  }

  async function handleAddMember() {
    if (!selectedProjectId || !selectedCollectionId || !newMemberId) return;
    setSaving(true);
    setError("");
    try {
      await api.addCollectionMember(
        selectedProjectId,
        selectedCollectionId,
        hasProjectContext
          ? { member_id: newMemberId, role: newMemberRole }
          : { user_id: newMemberId, role: newMemberRole },
        activeResearchSpaceId,
      );
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
      await api.updateCollectionMember(selectedProjectId, selectedCollectionId, memberRecordId, { role }, activeResearchSpaceId);
      await Promise.all([loadCollections(), loadCollectionDetail(selectedCollectionId)]);
      setStatus("Member role updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update member role");
    }
  }

  async function handleRemoveMember(memberRecordId: string) {
    if (!selectedProjectId || !selectedCollectionId) return;
    try {
      await api.removeCollectionMember(selectedProjectId, selectedCollectionId, memberRecordId, activeResearchSpaceId);
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
        }, activeResearchSpaceId),
        api.setCollectionMeetings(selectedProjectId, selectedCollectionId, {
          meeting_ids: meetingIds,
        }, activeResearchSpaceId),
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
      const result = await api.synthesizeCollection(selectedProjectId, selectedCollectionId, activeResearchSpaceId);
      setCollectionDetail((current) => (current ? { ...current, ai_synthesis: result.ai_synthesis, ai_synthesis_at: result.ai_synthesis_at } : current));
      setStatus("Synthesis updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Synthesis failed");
    } finally {
      setSynthesizing(false);
    }
  }

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

      {studyPaletteOpen ? (() => {
        const norm = studyPaletteQuery.trim().toLowerCase();
        const allStudies = [...activeCollections, ...archivedCollections];
        const filtered = norm
          ? allStudies.filter((s) =>
              s.title.toLowerCase().includes(norm) ||
              (s.description || "").toLowerCase().includes(norm) ||
              (s.hypothesis || "").toLowerCase().includes(norm) ||
              s.status.toLowerCase().includes(norm)
            )
          : allStudies;
        const clampedIndex = Math.min(studyPaletteIndex, Math.max(filtered.length - 1, 0));
        return (
          <div className="cmd-palette-overlay" onClick={() => setStudyPaletteOpen(false)}>
            <div className="cmd-palette" onClick={(e) => e.stopPropagation()}>
              <div className="cmd-palette-input-row">
                <FontAwesomeIcon icon={faSearch} className="cmd-palette-search-icon" />
                <input
                  ref={studyPaletteInputRef}
                  type="text"
                  className="cmd-palette-input"
                  placeholder="Search studies…"
                  value={studyPaletteQuery}
                  onChange={(e) => { setStudyPaletteQuery(e.target.value); setStudyPaletteIndex(0); }}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") { setStudyPaletteOpen(false); return; }
                    if (e.key === "ArrowDown") { e.preventDefault(); setStudyPaletteIndex((i) => Math.min(i + 1, filtered.length - 1)); return; }
                    if (e.key === "ArrowUp") { e.preventDefault(); setStudyPaletteIndex((i) => Math.max(i - 1, 0)); return; }
                    if (e.key === "Enter" && filtered.length > 0) {
                      e.preventDefault();
                      const selected = filtered[clampedIndex];
                      setSelectedCollectionId(selected.id);
                      setTab("overview");
                      setStudyPaletteOpen(false);
                    }
                  }}
                />
                <kbd className="cmd-palette-kbd">esc</kbd>
              </div>
              <div className="cmd-palette-list">
                {filtered.length === 0 ? (
                  <p className="cmd-palette-empty">No studies found.</p>
                ) : filtered.map((study, i) => (
                  <button
                    key={study.id}
                    type="button"
                    className={`cmd-palette-item${i === clampedIndex ? " active" : ""}`}
                    ref={i === clampedIndex ? (el) => el?.scrollIntoView({ block: "nearest" }) : undefined}
                    onMouseEnter={() => setStudyPaletteIndex(i)}
                    onClick={() => {
                      setSelectedCollectionId(study.id);
                      setTab("overview");
                      setStudyPaletteOpen(false);
                    }}
                  >
                    <FontAwesomeIcon icon={faBookOpen} className="cmd-palette-item-icon" />
                    <span>{study.title}</span>
                    <span className="cmd-palette-item-section">{study.status}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        );
      })() : null}

      {!bibliographyOnly && showSpaceHome ? (
        <>
          <div className="delivery-tabs study-home-tabs" data-tour-id="research-study-home">
            <button className={`delivery-tab ${studyHomeView === "dashboard" ? "active" : ""}`} onClick={() => setStudyHomeView("dashboard")}>
              Dashboard
            </button>
            <button className={`delivery-tab ${studyHomeView === "studies" ? "active" : ""}`} onClick={() => setStudyHomeView("studies")}>
              Studies <span className="delivery-tab-count">{studyDigestData.total}</span>
            </button>
            {activeResearchSpace ? <span className="chip small">{activeResearchSpace.title}</span> : null}
            <div className="topbar-project-search workspace-browser-search">
              <FontAwesomeIcon icon={faSearch} />
              <input
                type="text"
                value={studySearchQuery}
                onChange={(event) => setStudySearchQuery(event.target.value)}
                placeholder="Search studies"
              />
            </div>
            {activeResearchSpace ? (
              <button type="button" className="ghost" onClick={() => onClearResearchSpaceFilter?.()}>
                All Studies
              </button>
            ) : null}
            <button
              type="button"
              className="ghost icon-text-button small"
              onClick={() => void handleOpenCollectionsGraph()}
              disabled={loadingCollectionsGraph || filteredActiveCollections.length === 0}
            >
              <FontAwesomeIcon icon={faShareNodes} /> {loadingCollectionsGraph ? "Loading..." : "Graph"}
            </button>
            {!isStudent ? (
              <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openCreateCollectionModal}>
                <FontAwesomeIcon icon={faPlus} /> New Study
              </button>
            ) : null}
          </div>
          <div className="setup-summary-bar">
            <div className="setup-summary-stats">
              {studyHomeView === "dashboard" ? (
                <>
                  <span>{studyDigestData.total} studies</span>
                  <span className="setup-summary-sep" />
                  <span>{studyDigestData.needsReviewCount} needs review</span>
                  <span className="setup-summary-sep" />
                  <span>{studyDigestData.recentCount} recent</span>
                  <span className="setup-summary-sep" />
                  <span>{studyDigestData.deadlineCount} deadlines</span>
                  {studyDigestData.overdueCount > 0 ? (
                    <>
                      <span className="setup-summary-sep" />
                      <span className="summary-stat-danger">{studyDigestData.overdueCount} overdue</span>
                    </>
                  ) : null}
                  {studyDigestData.staleCount > 0 ? (
                    <>
                      <span className="setup-summary-sep" />
                      <span className="summary-stat-warning">{studyDigestData.staleCount} stale</span>
                    </>
                  ) : null}
                </>
              ) : (
                <>
                  <span>{visibleActiveCollections.length} visible studies</span>
                  {visibleArchivedCollections.length > 0 ? (
                    <>
                      <span className="setup-summary-sep" />
                      <span>{visibleArchivedCollections.length} archived</span>
                    </>
                  ) : null}
                </>
              )}
            </div>
          </div>
        </>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      {showSpaceHome ? (
        <div className="workspace-browser-page study-browser-page">
          {studyHomeView === "dashboard" ? (
            <>
              <div className="meetings-detail-section study-heatmap-shell">
                <div className="meetings-detail-head">
                  <div className="meetings-detail-info">
                    <strong>Contribution</strong>
                  </div>
                  <div className="study-heatmap-month-nav">
                    <button
                      type="button"
                      className="ghost icon-only"
                      onClick={() => setStudyHeatmapMonth((value) => addMonths(value, -1))}
                      disabled={!studyHeatmapData.canGoPrev}
                      aria-label="Previous month"
                    >
                      <FontAwesomeIcon icon={faChevronLeft} />
                    </button>
                    <button
                      type="button"
                      className="study-heatmap-month-label"
                      onClick={() => setStudyHeatmapMonth(startOfMonth(new Date()))}
                    >
                      {studyHeatmapData.monthLabel}
                    </button>
                    <button
                      type="button"
                      className="ghost icon-only"
                      onClick={() => setStudyHeatmapMonth((value) => addMonths(value, 1))}
                      disabled={!studyHeatmapData.canGoNext}
                      aria-label="Next month"
                    >
                      <FontAwesomeIcon icon={faChevronRight} />
                    </button>
                  </div>
                </div>
                <div className="study-heatmap-wrap">
                  <div className="study-heatmap-table">
                    <div className="study-heatmap-header">
                      <div className="study-heatmap-corner">
                        <span>Study</span>
                      </div>
                        <div className="study-heatmap-days study-heatmap-days-head" style={{ gridTemplateColumns: `repeat(${studyHeatmapData.days.length}, 15px)` }}>
                          {studyHeatmapData.days.map((day) => (
                          <span
                            key={day.key}
                            className={`study-heatmap-day-label${day.key === new Date().toISOString().slice(0, 10) ? " today" : ""}`}
                            title={day.label}
                          >
                            {day.dayNumber}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="study-heatmap-rows">
                      {studyHeatmapData.rows.map((row) => (
                        <div key={`heatmap-${row.study.id}`} className="study-heatmap-row">
                          <button
                            type="button"
                            className="study-heatmap-row-label"
                            onClick={() => openStudyFromCard(row.study.id)}
                            title={row.study.title || "Untitled Study"}
                          >
                            <strong>{row.study.title || "Untitled Study"}</strong>
                          </button>
                          <div className="study-heatmap-days study-heatmap-days-row" style={{ gridTemplateColumns: `repeat(${studyHeatmapData.days.length}, 15px)` }}>
                            {row.values.map((value, index) => {
                              const intensity = studyHeatmapData.maxCount > 0 ? value / studyHeatmapData.maxCount : 0;
                              const deadlineMarkers = row.deadlines[index];
                              const deadlineTone =
                                deadlineMarkers.some((item) => item.tone === "danger")
                                  ? "danger"
                                  : deadlineMarkers.some((item) => item.tone === "warning")
                                    ? "warning"
                                    : deadlineMarkers.some((item) => item.tone === "muted")
                                      ? "muted"
                                      : null;
                              return (
                                <button
                                  key={`${row.study.id}-${studyHeatmapData.days[index].key}`}
                                  type="button"
                                  className={`study-heatmap-cell${value > 0 ? " active" : ""}${deadlineTone ? ` has-deadline deadline-${deadlineTone}` : ""}`}
                                  style={{
                                    backgroundColor: value > 0
                                      ? `color-mix(in srgb, var(--brand) ${Math.max(18, Math.round(intensity * 88))}%, var(--surface))`
                                      : undefined,
                                  }}
                                  title={
                                    `${row.study.title || "Untitled Study"} · ${studyHeatmapData.days[index].label} · ${value} activities` +
                                    (deadlineMarkers.length
                                      ? ` · ${deadlineMarkers.map((item) => item.label).join(", ")} deadline`
                                      : "")
                                  }
                                  onClick={() => openStudyFromCard(row.study.id)}
                                />
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              {!isStudent ? (
                <div className="study-digest-grid">
                  <section className="study-digest-col">
                    <div className="study-digest-col-head">
                      <span className="study-digest-col-dot dot-warning" />
                      <span className="study-digest-col-label">Needs review</span>
                      <span className="study-digest-col-count">{studyDigestData.needsReview.length}</span>
                    </div>
                    {studyDigestData.needsReview.length > 0 ? studyDigestData.needsReview.map((item) => (
                      <button key={`digest-review-${item.study.id}`} type="button" className="study-digest-row" onClick={() => openStudyFromCard(item.study.id)}>
                        <span className="study-digest-row-title">{item.study.title || "Untitled Study"}</span>
                        <span className="study-digest-row-meta">
                          {item.study.recent_log_count} recent logs · {item.study.study_iterations.length} iterations · {item.study.overdue_action_count} overdue actions
                        </span>
                      </button>
                    )) : <span className="study-digest-nil">No studies need review</span>}
                  </section>
                  <section className="study-digest-col">
                    <div className="study-digest-col-head">
                      <span className="study-digest-col-dot dot-brand" />
                      <span className="study-digest-col-label">Recent activity</span>
                      <span className="study-digest-col-count">{studyDigestData.recent.length}</span>
                    </div>
                    {studyDigestData.recent.length > 0 ? studyDigestData.recent.map((item) => (
                      <button key={`digest-recent-${item.study.id}`} type="button" className="study-digest-row" onClick={() => openStudyFromCard(item.study.id)}>
                        <span className="study-digest-row-title">{item.study.title || "Untitled Study"}</span>
                        <span className="study-digest-row-meta">
                          {item.study.reference_count} references · {item.study.recent_log_count} recent logs · updated {formatRelativeTime(item.study.updated_at)}
                        </span>
                      </button>
                    )) : <span className="study-digest-nil">No recent activity</span>}
                  </section>
                  <section className="study-digest-col">
                    <div className="study-digest-col-head">
                      <span className="study-digest-col-dot dot-danger" />
                      <span className="study-digest-col-label">Deadlines</span>
                      <span className="study-digest-col-count">{studyDigestData.deadlineCount}</span>
                    </div>
                    {(() => {
                      const pressureItems = studyDigestData.deadlines.length > 0 ? studyDigestData.deadlines : studyDigestData.items.filter((item) => item.study.overdue_action_count > 0).slice(0, 4);
                      return pressureItems.length > 0 ? pressureItems.map((item) => {
                        const deadline = item.overdueDeadline || item.upcomingDeadline;
                        const isOverdue = item.study.overdue_action_count > 0 || Boolean(item.overdueDeadline);
                        const deadlinePressure = deadline ? formatDeadlinePressure(deadline.date, new Date()) : null;
                        return (
                          <button key={`digest-deadline-${item.study.id}`} type="button" className={`study-digest-row${isOverdue ? " overdue" : ""}`} onClick={() => openStudyFromCard(item.study.id)}>
                            <span className="study-digest-row-title">{item.study.title || "Untitled Study"}</span>
                            {deadline && deadlinePressure ? (
                              <span className={`study-deadline-badge ${deadlinePressure.tone}`}>
                                {deadlinePressure.label}
                              </span>
                            ) : null}
                            <span className="study-digest-row-meta">
                              {deadline ? `${deadline.label} ${deadline.date.toLocaleDateString()}` : `${item.study.overdue_action_count} overdue actions`} · {item.study.open_action_count} open · {item.study.doing_action_count} doing
                            </span>
                          </button>
                        );
                      }) : <span className="study-digest-nil">No upcoming deadlines</span>;
                    })()}
                  </section>
                  <section className="study-digest-col">
                    <div className="study-digest-col-head">
                      <span className="study-digest-col-dot dot-muted" />
                      <span className="study-digest-col-label">Stale</span>
                      <span className="study-digest-col-count">{studyDigestData.staleCount}</span>
                    </div>
                    {studyDigestData.stale.length > 0 ? studyDigestData.stale.map((item) => (
                      <button key={`digest-stale-${item.study.id}`} type="button" className="study-digest-row stale" onClick={() => openStudyFromCard(item.study.id)}>
                        <span className="study-digest-row-title">{item.study.title || "Untitled Study"}</span>
                        <span className="study-digest-row-meta">
                          {item.study.open_action_count + item.study.doing_action_count} pending actions · updated {formatRelativeTime(item.study.updated_at)}
                        </span>
                      </button>
                    )) : <span className="study-digest-nil">All studies active</span>}
                  </section>
                </div>
              ) : null}
            </>
          ) : null}
          {studyHomeView === "studies" ? (
            <>
              <div className="meetings-toolbar workspace-browser-toolbar">
                <div className="meetings-filter-group workspace-browser-filter-group study-browser-filter-row">
                  <div className="study-browser-filter-pills">
                    {([
                      ["all", "all"],
                      ["needs-review", "needs review"],
                      ["recent", "recent activity"],
                      ["deadlines", "deadlines"],
                      ["stale", "stale"],
                    ] as const).map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={`chip small ${studyDigestFilter === value ? "active" : ""}`}
                        onClick={() => setStudyDigestFilter(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {archivedCollections.length > 0 ? (
                    <button type="button" className="chip small" onClick={() => setShowArchived((value) => !value)}>
                      <FontAwesomeIcon icon={faChevronRight} className={showArchived ? "research-chevron-open" : ""} />
                      Archived ({visibleArchivedCollections.length})
                    </button>
                  ) : null}
                </div>
              </div>
              {visibleActiveCollections.length === 0 && (!showArchived || visibleArchivedCollections.length === 0) ? (
                <div className="empty-state-card">
                  <strong>No studies.</strong>
                </div>
              ) : (
                <>
                  {visibleActiveCollections.length > 0 ? (
                    <div className="workspace-browser-grid" data-tour-id="research-study-grid">
                      {visibleActiveCollections.map((item) => (
                        <div
                          key={item.id}
                          className="study-card-v2"
                          role="button"
                          tabIndex={0}
                          aria-label={`Open ${item.title}`}
                          onClick={() => openStudyFromCard(item.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              openStudyFromCard(item.id);
                            } else if (event.key.toLowerCase() === "e") {
                              event.preventDefault();
                              openEditCollectionFromCard(item);
                            }
                          }}
                        >
                          <div className="study-card-v2-head">
                            <strong className="study-card-v2-title">{item.title || "Untitled Study"}</strong>
                            <div className="study-card-v2-flags">
                              {item.needs_review ? <span className="study-card-flag flag-warning">needs review</span> : null}
                              {item.overdue_action_count > 0 ? <span className="study-card-flag flag-danger">{item.overdue_action_count} overdue</span> : null}
                              {item.recent_log_count > 0 ? <span className="study-card-flag flag-brand">{item.recent_log_count} recent</span> : null}
                              {item.assigned_to_me_action_count > 0 ? <span className="study-card-flag flag-muted">{item.assigned_to_me_action_count} assigned</span> : null}
                              {studyDigestData.items.find((d) => d.study.id === item.id)?.stale ? <span className="study-card-flag flag-stale">stale</span> : null}
                            </div>
                          </div>
                          <p className="study-card-v2-desc">{item.description || item.hypothesis || "No focus"}</p>
                          <div className="study-card-v2-stats">
                            <span>{item.reference_count} refs</span>
                            <span>{item.note_count} logs</span>
                            <span>{item.open_action_count + item.doing_action_count} actions</span>
                            <span>{formatRelativeTime(item.updated_at)}</span>
                          </div>
                          <div className="study-card-v2-foot">
                            <div className="study-card-v2-chips">
                              {item.space_ids.slice(0, 2).map((spaceId) => {
                                const space = availableResearchSpaces.find((entry) => entry.id === spaceId);
                                if (!space) return null;
                                return <span key={`${item.id}-${space.id}`} className="chip small">{space.title}</span>;
                              })}
                              {item.space_ids.length > 2 ? <span className="chip small">+{item.space_ids.length - 2}</span> : null}
                            </div>
                            <div className="study-card-v2-actions">
                              <button type="button" className="ghost" tabIndex={-1} onClick={(event) => { event.stopPropagation(); openEditCollectionFromCard(item); }}>
                                Edit
                              </button>
                              <button type="button" tabIndex={-1} onClick={(event) => { event.stopPropagation(); openStudyFromCard(item.id); }}>
                                Open
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {showArchived && visibleArchivedCollections.length > 0 ? (
                    <div className="workspace-browser-grid study-browser-archived-grid">
                      {visibleArchivedCollections.map((item) => (
                        <div
                          key={item.id}
                          className="study-card-v2 archived"
                          role="button"
                          tabIndex={0}
                          aria-label={`Open ${item.title}`}
                          onClick={() => openStudyFromCard(item.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              openStudyFromCard(item.id);
                            } else if (event.key.toLowerCase() === "e") {
                              event.preventDefault();
                              openEditCollectionFromCard(item);
                            }
                          }}
                        >
                          <div className="study-card-v2-head">
                            <strong className="study-card-v2-title">{item.title || "Untitled Study"}</strong>
                            <span className="study-card-flag flag-muted">Archived</span>
                          </div>
                          <p className="study-card-v2-desc">{item.description || item.hypothesis || "No focus"}</p>
                          <div className="study-card-v2-stats">
                            <span>{item.reference_count} refs</span>
                            <span>{item.note_count} logs</span>
                            <span>{formatRelativeTime(item.updated_at)}</span>
                          </div>
                          <div className="study-card-v2-foot">
                            <div className="study-card-v2-chips">
                              {item.space_ids.slice(0, 2).map((spaceId) => {
                                const space = availableResearchSpaces.find((entry) => entry.id === spaceId);
                                if (!space) return null;
                                return <span key={`${item.id}-${space.id}`} className="chip small">{space.title}</span>;
                              })}
                            </div>
                            <div className="study-card-v2-actions">
                              <button type="button" className="ghost" tabIndex={-1} onClick={(event) => { event.stopPropagation(); openEditCollectionFromCard(item); }}>
                                Edit
                              </button>
                              <button type="button" tabIndex={-1} onClick={(event) => { event.stopPropagation(); openStudyFromCard(item.id); }}>
                                Open
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              )}
            </>
          ) : null}
        </div>
      ) : null}

      {!bibliographyOnly && collectionDetail && selectedCollection ? (
        <div className="study-header">
          <div className="study-header-top">
            <div className="study-header-title-wrap">
              {editingStudyTitle ? (
                <input
                  className="study-header-title-input"
                  value={inlineStudyTitle}
                  autoFocus
                  onChange={(event) => setInlineStudyTitle(event.target.value)}
                  onBlur={() => {
                    setInlineStudyTitle(collectionDetail.title || "");
                    setEditingStudyTitle(false);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleInlineStudyHeaderSave("title");
                    } else if (event.key === "Escape") {
                      event.preventDefault();
                      setInlineStudyTitle(collectionDetail.title || "");
                      setEditingStudyTitle(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className="study-header-title-button"
                  onClick={() => setEditingStudyTitle(true)}
                  title="Edit title"
                >
                  <h2 className="study-header-title">{collectionDetail.title}</h2>
                </button>
              )}
            </div>
            {collectionDetail.members.length > 0 && (
              <div className="study-header-avatars">
                {collectionDetail.members.slice(0, 5).map((member: ResearchCollectionMember) => (
                  <StudyHeaderAvatar key={member.id} member={member} isOnline={studyOnlineUserIds.includes(member.user_id || "")} />
                ))}
                {collectionDetail.members.length > 5 && (
                  <span className="study-avatar study-avatar-overflow" title={`${collectionDetail.members.length - 5} more`}>
                    +{collectionDetail.members.length - 5}
                  </span>
                )}
              </div>
            )}
            {!isStudent ? (
              <div className="study-header-actions">
                <button type="button" className="ghost docs-action-btn" title="Chat" onClick={() => setTab("chat")}>
                  <FontAwesomeIcon icon={faComment} />
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
            ) : null}
          </div>
          <div className="study-header-meta">
            <span className={`chip small ${collectionDetail.status === "active" ? "status-ok" : ""}`}>{collectionDetail.status}</span>
            <span className="study-header-stat">{collectionDetail.reference_count} refs</span>
            <span className="study-header-stat">{collectionDetail.note_count} logs</span>
            <span className="study-header-stat">{collectionDetail.member_count} members</span>
            {collectionDetail.space_ids.map((spaceId) => {
              const space = availableResearchSpaces.find((item) => item.id === spaceId);
              if (!space) return null;
              return <span key={`study-space-${space.id}`} className="chip small">{space.title}</span>;
            })}
            {collectionDetail.hypothesis ? (
              <span className="study-header-hypothesis" title={collectionDetail.hypothesis}>{collectionDetail.hypothesis}</span>
            ) : null}
          </div>
        </div>
      ) : null}

      {!bibliographyOnly && selectedCollectionId ? <div className="delivery-tabs">
        <button className={`delivery-tab ${tab === "overview" ? "active" : ""}`} data-tour-id="study-overview-tab" onClick={() => setTab("overview")}>
          Overview
        </button>
        <button className={`delivery-tab inbox-tab ${tab === "notes" ? "active" : ""}`} data-tour-id="study-inbox-tab" onClick={() => setTab("notes")}>
          <FontAwesomeIcon icon={faInbox} /> Inbox <span className="delivery-tab-count">{notes.length}</span>
          {tabAlerts.inboxAlert ? <span className="tab-alert-dot" /> : null}
        </button>
        <button className={`delivery-tab ${tab === "iterations" ? "active" : ""}`} data-tour-id="study-iterations-tab" onClick={() => setTab("iterations")}>
          Iterations <span className="delivery-tab-count">{studyIterations.length}</span>
        </button>
        <button className={`delivery-tab ${tab === "references" ? "active" : ""}`} data-tour-id="study-references-tab" onClick={() => setTab("references")}>
          References <span className="delivery-tab-count">{references.length}</span>
          {tabAlerts.refsAlert ? <span className="tab-alert-dot tab-alert-info" /> : null}
        </button>
        <button className={`delivery-tab ${tab === "paper" ? "active" : ""}`} data-tour-id="study-paper-tab" onClick={() => setTab("paper")}>
          Paper
          {tabAlerts.paperAlert ? <span className="tab-alert-dot" /> : null}
        </button>
        <button className={`delivery-tab ${tab === "files" ? "active" : ""}`} onClick={() => setTab("files")}>
          Files <span className="delivery-tab-count">{studyFiles.length}</span>
        </button>
        <button className={`delivery-tab ${tab === "todos" ? "active" : ""}`} onClick={() => setTab("todos")}>
          Todos <span className="delivery-tab-count">{notes.reduce((count, note) => count + (note.action_items?.length || 0), 0)}</span>
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
              className="ghost icon-text-button small"
              onClick={openIndexNote}
              disabled={!selectedCollectionId}
            >
              <FontAwesomeIcon icon={faBookOpen} /> {notes.some((item) => item.collection_id === selectedCollectionId && isIndexNote(item)) ? "Open Index" : "New Index"}
            </button>
            <button
              type="button"
              className="ghost icon-text-button small"
              disabled={notes.filter((item) => item.collection_id === selectedCollectionId).length === 0}
              onClick={() => setStudyGraphOpen(true)}
            >
              <FontAwesomeIcon icon={faShareNodes} /> Graph
            </button>
            <button
              type="button"
              className="ghost icon-text-button small"
              disabled={visibleStudyLogNotes.length === 0}
              onClick={() =>
                setFoldedNoteIds((current) => {
                  const next = new Set(current);
                  if (allVisibleStudyLogsFolded) {
                    visibleStudyLogNotes.forEach((note) => next.delete(note.id));
                  } else {
                    visibleStudyLogNotes.forEach((note) => next.add(note.id));
                  }
                  return next;
                })
              }
            >
              {allVisibleStudyLogsFolded ? "Unfold All" : "Fold All"}
            </button>
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
              onClick={() => openCreateNoteModal()}
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

      {tab === "references" && !bibliographyOnly && selectedCollectionId ? renderReferencesTab() : null}
      {bibliographyOnly ? renderBibliographyTab() : null}
      {tab === "notes" && !bibliographyOnly && selectedCollectionId ? renderNotesTab() : null}
      {tab === "todos" && !bibliographyOnly && selectedCollectionId ? renderTodosTab() : null}
      {tab === "paper" && !bibliographyOnly && selectedCollectionId ? renderPaperTab() : null}
      {!bibliographyOnly && selectedCollectionId ? (
        <div style={tab === "chat" ? undefined : { display: "none" }}>{renderChatTab()}</div>
      ) : null}
      {tab === "iterations" && !bibliographyOnly && selectedCollectionId ? renderIterationsTab() : null}
      {tab === "files" && !bibliographyOnly && selectedCollectionId ? renderFilesTab() : null}
      {tab === "overview" && !bibliographyOnly && selectedCollectionId ? renderOverviewTab() : null}

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
      {studyGraphOpen && selectedCollectionId ? (
        <StudyGraphModal
          notes={notes.filter((item) => item.collection_id === selectedCollectionId)}
          references={references.filter((item) => item.collection_id === selectedCollectionId)}
          files={studyFiles.filter((item) => item.collection_id === selectedCollectionId)}
          iterations={studyIterations}
          initialNodeId={activeInboxNoteId ? `log:${activeInboxNoteId}` : null}
          onClose={() => setStudyGraphOpen(false)}
          onOpenNote={(noteId) => {
            setStudyGraphOpen(false);
            handleOpenLinkedNote(noteId);
          }}
          onOpenReference={(referenceId) => {
            setStudyGraphOpen(false);
            handleOpenLinkedReference(referenceId);
          }}
          onOpenFile={(fileId) => {
            setStudyGraphOpen(false);
            const file = studyFiles.find((item) => item.id === fileId);
            if (file) void handleOpenStudyFile(file);
          }}
          onOpenIteration={(iterationId) => {
            setStudyGraphOpen(false);
            handleOpenIteration(iterationId);
          }}
        />
      ) : null}
      {collectionsGraphOpen && collectionsGraphData ? (
        <CollectionsGraphModal
          graphData={collectionsGraphData}
          onClose={() => {
            setCollectionsGraphOpen(false);
            setCollectionsGraphData(null);
          }}
          onOpenStudy={(studyId) => {
            setCollectionsGraphOpen(false);
            setCollectionsGraphData(null);
            openStudyFromCard(studyId);
          }}
          onOpenLog={(logId) => {
            setCollectionsGraphOpen(false);
            setCollectionsGraphData(null);
            handleOpenLinkedNote(logId);
          }}
        />
      ) : null}
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

    const referenceUsage = (referenceId: string) => referenceUsageMap.get(referenceId) || { claimCount: 0, sectionCount: 0, noteCount: 0, total: 0 };

    return (
      <div className="references-tab-fill">
        <div className="meetings-toolbar">
          <div className="meetings-filter-group">
            <select value={refStatusFilter} onChange={(event) => setRefStatusFilter(event.target.value)}>
              <option value="">All statuses</option>
              <option value="unread">Unread</option>
              <option value="reading">Reading</option>
              <option value="read">Read</option>
              <option value="reviewed">Reviewed</option>
            </select>
            <select value={refSortKey} onChange={(event) => setRefSortKey(event.target.value as typeof refSortKey)}>
              <option value="created_at">Newest</option>
              <option value="title">Title</option>
              <option value="connections">Connections</option>
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
                {sortedReferences.map((reference) => (
                  <tr key={reference.id}>
                    <td>
                      <strong>{reference.title}</strong>
                      <span className="muted-small research-inline-meta">{reference.authors.join(", ") || "-"}</span>
                      {reference.venue ? <span className="muted-small research-inline-meta">{reference.venue}</span> : null}
                      {(() => {
                        const usage = referenceUsage(reference.id);
                        return (
                          <span className="research-chip-group ref-usage-row">
                            <span className={`chip small${usage.claimCount > 0 ? " log-chip-promoted" : ""}`}>{usage.claimCount} claims</span>
                            <span className={`chip small${usage.sectionCount > 0 ? " log-chip-promoted" : ""}`}>{usage.sectionCount} sections</span>
                            <span className={`chip small${usage.noteCount > 0 ? "" : ""}`}>{usage.noteCount} notes</span>
                            {usage.total === 0 ? <span className="chip small log-chip-unprocessed">Unlinked</span> : null}
                          </span>
                        );
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
      </div>
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
              {!isStudent ? (
                <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openCreateBibliographyModal}>
                  <FontAwesomeIcon icon={faPlus} /> Add Paper
                </button>
              ) : null}
            </div>
          ) : (
            !isStudent ? (
              <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openCreateBibliographyCollectionModal}>
                <FontAwesomeIcon icon={faPlus} /> New Collection
              </button>
            ) : null
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
                          {!isStudent ? (
                            <button
                              type="button"
                              className="ghost docs-action-btn"
                              title="Summarize"
                              disabled={summarizingId === item.id}
                              onClick={() => void handleSummarizeBibliography(item.id)}
                            >
                              <FontAwesomeIcon icon={faMagicWandSparkles} spin={summarizingId === item.id} />
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="ghost docs-action-btn"
                            title="Copy link"
                            onClick={() => void handleCopyBibliographyPermalink(item)}
                          >
                            <FontAwesomeIcon icon={faLink} />
                          </button>
                          {!isStudent ? (
                            <button
                              type="button"
                              className={`ghost docs-action-btn${confirmingDeleteId === item.id ? " danger confirm-pulse" : ""}`}
                              title={confirmingDeleteId === item.id ? "Click again to confirm" : "Delete paper"}
                              onClick={() => requestConfirmDelete(item.id, () => void handleDeleteBibliography(item.id))}
                            >
                              {confirmingDeleteId === item.id ? <span className="confirm-label">Sure?</span> : <FontAwesomeIcon icon={faTrash} />}
                            </button>
                          ) : null}
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
          {(() => {
            const searchNorm = bibliographySearch.trim().toLowerCase();
            const visFilter = bibliographyVisibilityFilter;
            const filtered = bibliography.filter((item) => {
              if (visFilter && item.visibility !== visFilter) return false;
              if (!searchNorm) return true;
              return (
                item.title.toLowerCase().includes(searchNorm) ||
                item.authors.some((a) => a.toLowerCase().includes(searchNorm)) ||
                (item.venue || "").toLowerCase().includes(searchNorm)
              );
            });
            if (filtered.length === 0) return (
              <div className="empty-message">
                <p>{bibliography.length === 0 ? "No papers in your library yet." : "No papers match your search."}</p>
                <button
                  type="button"
                  className="meetings-new-btn"
                  style={{ marginTop: 8 }}
                  onClick={() => {
                    setBibliographyPickerOpen(false);
                    openCreateBibliographyModal();
                  }}
                >
                  <FontAwesomeIcon icon={faPlus} /> Add reference
                </button>
              </div>
            );
            return (
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
                  {filtered.map((item) => (
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
            <div style={{ padding: "8px 0", textAlign: "center" }}>
              <button
                type="button"
                className="ghost icon-text-button small"
                onClick={() => {
                  setBibliographyPickerOpen(false);
                  openCreateBibliographyModal();
                }}
              >
                <FontAwesomeIcon icon={faPlus} /> Add reference
              </button>
            </div>
            </div>
            );
          })()}
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
      <>
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
        <select className={`research-lane-select${className}`} value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">{noneLabel}</option>
          {NOTE_LANE_OPTIONS.map(([laneValue, laneLabel]) => (
            <option key={laneValue} value={laneValue}>{laneLabel}</option>
          ))}
        </select>
      </>
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
    const searchLower = noteSearchQuery.trim().toLowerCase();
    const visibleNotes = searchLower
      ? notes.filter((note) => {
        if (searchLower.startsWith("#")) {
          return note.tags.some((tag) => tag.toLowerCase().includes(searchLower.slice(1)));
        }
        return (
          note.title.toLowerCase().includes(searchLower) ||
          note.content.toLowerCase().includes(searchLower) ||
          note.tags.some((tag) => tag.toLowerCase().includes(searchLower))
        );
      })
      : notes;
    const collectionVisibleNotes = visibleNotes.filter((note) => note.collection_id === selectedCollectionId);
    const indexNote = collectionVisibleNotes.find((note) => isIndexNote(note)) || null;
    const sortedNotes = [...collectionVisibleNotes.filter((note) => !isIndexNote(note))].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      if (a.starred !== b.starred) return a.starred ? -1 : 1;
      return b.created_at.localeCompare(a.created_at);
    });
    const orderedNotes = sortedNotes;
    const unassignedLogs = orderedNotes.filter((note) => !noteIterationState(note.id).assigned);
    const allVisibleSelected = orderedNotes.length > 0 && orderedNotes.every((note) => selectedInboxLogIds.has(note.id));
    const fileLookup = new Map(studyFiles.map((item) => [item.id, item]));
    const iterationLookup = new Map(studyIterations.map((iteration) => [iteration.id, iteration]));
    const noteLookup = new Map(notes.map((item) => [item.id, item]));
    const noteSuggestions = notes
      .filter((item) => item.collection_id === selectedCollectionId)
      .map((item) => ({
        id: item.id,
        label: item.title || "Untitled Log",
        meta: formatLogTimestamp(item.created_at),
      }));
    const memberSuggestions = (collectionDetail?.members || []).map((member) => ({
      id: member.member_id,
      label: `@${memberMentionHandle(member.member_name)}`,
      meta: member.member_name,
    }));

    function renderReferencedFilePreviews(content: string, fileIds: string[]) {
      const files = extractMarkdownFileLabels(content)
        .map((label) => resolveLinkedFileByLabel(label, fileIds))
        .filter((item): item is ResearchStudyFile => Boolean(item))
        .filter((item, index, arr) => arr.findIndex((candidate) => candidate.id === item.id) === index)
        .filter((item) => isImageMime(item.mime_type) || isCsvMime(item.mime_type, item.original_filename));

      if (files.length === 0) return null;
      return (
        <div className="research-file-preview-list">
          {files.map((file) => (
            <ResearchFilePreviewCard
              key={`file-preview-${file.id}`}
              file={file}
              projectId={selectedProjectId}
              collectionId={selectedCollectionId}
              spaceId={activeResearchSpaceId || undefined}
            />
          ))}
        </div>
      );
    }

    const renderReply = (reply: ResearchNoteReply) => (
      <div key={reply.id} className="research-log-reply">
        <LogAvatar
          name={reply.author_name || "Unknown user"}
          avatarUrl={reply.author_avatar_url}
          className="research-log-reply-avatar"
        />
        <div className="research-log-reply-body">
          <div className="research-log-reply-head">
            <strong>{reply.author_name || "Unknown user"}</strong>
            <span>{formatLogTimestamp(reply.created_at)}</span>
          </div>
          <div className="research-log-text chat-markdown">
            {renderMarkdown(reply.content, {
              onReferenceClick: (label) => handleOpenReferenceByLabel(label, reply.linked_reference_ids),
              onTagClick: handleFilterByTag,
              onFileClick: (label) => handleOpenLinkedFileByLabel(label, []),
              onNoteClick: (label) => handleOpenLinkedNoteByLabel(label),
            })}
          </div>
          {reply.linked_reference_ids.length > 0 ? (
            <div className="research-log-reply-meta">
              {reply.linked_reference_ids.map((referenceId) => {
                const ref = references.find((item) => item.id === referenceId);
                if (!ref) return null;
                return (
                  <button
                    key={`${reply.id}-ref-${referenceId}`}
                    type="button"
                    className="chip small"
                    onClick={() => handleOpenLinkedReference(referenceId)}
                  >
                    {formatRefLabel(ref)}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>
    );
    const renderActionItem = (action: ResearchNote["action_items"][number], key: string) => (
      <div key={key} className={`research-note-action-item${action.is_done ? " done" : ""}`}>
        <span className="research-note-action-checkbox">{action.is_done ? "[x]" : "[ ]"}</span>
        <span className="research-note-action-text">{action.text}</span>
        {action.assignee_name ? (
          <span className="research-note-action-assignee">
            <LogAvatar name={action.assignee_name} avatarUrl={action.assignee_avatar_url} className="research-note-action-avatar" />
            <span>{action.assignee_name}</span>
          </span>
        ) : null}
        {action.due_date ? <span className="chip small">{action.due_date}</span> : null}
      </div>
    );
    function toggleNoteFold(noteId: string) {
      setFoldedNoteIds((current) => {
        const next = new Set(current);
        if (next.has(noteId)) next.delete(noteId);
        else next.add(noteId);
        return next;
      });
    }

    const renderNoteCard = (note: ResearchNote, options?: { stackPreview?: boolean }) => {
      const workflow = noteWorkflow(note);
      const iterationState = noteIterationState(note.id);
      const isSelected = selectedInboxLogIds.has(note.id);
      const isEditing = inlineEditNoteId === note.id;
      const isReplying = replyingNoteId === note.id;
      const isFolded = foldedNoteIds.has(note.id);
      const replyDraft = replyDrafts[note.id] || "";
      const linkedReferencesLabel = note.linked_reference_ids.length === 1 ? "1 ref" : `${note.linked_reference_ids.length} refs`;
      const linkedFilesLabel = note.linked_file_ids.length === 1 ? "1 file" : `${note.linked_file_ids.length} files`;
      const linkedNotes = note.linked_note_ids.map((noteId) => noteLookup.get(noteId)).filter((item): item is ResearchNote => Boolean(item));
      const backlinkNotes = note.backlink_note_ids.map((noteId) => noteLookup.get(noteId)).filter((item): item is ResearchNote => Boolean(item));
      return (
        <article
          key={note.id}
          data-note-id={note.id}
          tabIndex={options?.stackPreview ? -1 : 0}
          className={`research-log-card${isSelected ? " selected" : ""}${isEditing ? " editing" : ""}${workflow.state === "Unprocessed" ? " log-state-unprocessed" : " log-state-promoted"}${iterationState.assigned ? " log-state-iterated" : ""}${note.pinned ? " is-pinned" : ""}${note.starred ? " is-starred" : ""}${activeInboxNoteId === note.id ? " is-active" : ""}${options?.stackPreview ? " in-stack-preview" : ""}${isIndexNote(note) ? " is-index-note" : ""}${isFolded ? " is-folded" : ""}`}
          onFocus={() => {
            if (!options?.stackPreview) setActiveInboxNoteId(note.id);
          }}
          onDoubleClick={() => {
            if (options?.stackPreview) return;
            openEditNoteModal(note);
          }}
        >
          <div
            className="research-log-head"
            onClick={(event) => {
              const target = event.target as HTMLElement | null;
              if (!target) return;
              if (target.closest("button, input, textarea, select, label, a")) return;
              if (options?.stackPreview) return;
              toggleNoteFold(note.id);
            }}
          >
            {!isIndexNote(note) ? (
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
            ) : null}
            <LogAvatar
              name={note.author_name || "Unknown author"}
              avatarUrl={note.author_avatar_url}
            />
            <div className="research-log-author-block">
              <div className="research-log-author-line">
                <strong>{note.author_name || "Unknown author"}</strong>
                <span className="research-log-timestamp">{formatLogTimestamp(note.created_at)} · {formatRelativeTime(note.created_at)}</span>
              </div>
              {!isEditing ? (
                <div className="research-chip-group">
                  {note.lane ? <span className="chip small">{NOTE_LANE_LABELS[note.lane] || note.lane}</span> : null}
                  {workflow.state !== "Unprocessed" ? (
                    <>
                      {workflow.promotedToQuestion ? <span className="chip small log-chip-promoted">→ Question</span> : null}
                      {workflow.promotedToClaim ? <span className="chip small log-chip-promoted">→ Claim</span> : null}
                      {workflow.promotedToSection ? <span className="chip small log-chip-promoted">→ Section</span> : null}
                    </>
                  ) : null}
                  {iterationState.assigned ? <span className="chip small log-chip-iterated">{iterationState.iterationTitle || "Iteration"}</span> : null}
                </div>
              ) : (
                renderLanePills(inlineEditLane, setInlineEditLane, { className: "research-inline-lane-pills" })
              )}
            </div>
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
                  <button
                    type="button"
                    className={`ghost docs-action-btn${note.pinned ? " active" : ""}`}
                    title={note.pinned ? "Unpin" : "Pin"}
                    onClick={() => void handleToggleNotePin(note)}
                  >
                    <FontAwesomeIcon icon={faThumbtack} />
                  </button>
                  <button
                    type="button"
                    className={`ghost docs-action-btn${note.starred ? " active" : ""}`}
                    title={note.starred ? "Unstar" : "Star"}
                    onClick={() => void handleToggleNoteStar(note)}
                  >
                    <FontAwesomeIcon icon={faStar} />
                  </button>
                  <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => startInlineEdit(note)}>
                    <FontAwesomeIcon icon={faPen} />
                  </button>
                  <button type="button" className="ghost docs-action-btn" title="Editor" onClick={() => openEditNoteModal(note)}>
                    <FontAwesomeIcon icon={faBookOpen} />
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
                placeholder="Content (markdown, % refs, @ people)"
              />
              <input
                ref={inlineEditFileInputRef}
                type="file"
                className="bib-pdf-input"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handleUploadStudyFile(file, { linkToInlineEdit: true });
                }}
              />
              <div className="research-log-composer-actions">
                {renderLanePills(inlineEditLane, setInlineEditLane, { className: "research-inline-lane-pills" })}
                <button
                  type="button"
                  className={`ghost icon-text-button small${inlineEditPinned ? " active" : ""}`}
                  onClick={() => setInlineEditPinned((current) => !current)}
                >
                  <FontAwesomeIcon icon={faThumbtack} /> {inlineEditPinned ? "Pinned" : "Pin"}
                </button>
                <button
                  type="button"
                  className={`ghost icon-text-button small${inlineEditStarred ? " active" : ""}`}
                  onClick={() => setInlineEditStarred((current) => !current)}
                >
                  <FontAwesomeIcon icon={faStar} /> {inlineEditStarred ? "Starred" : "Star"}
                </button>
                <button
                  type="button"
                  className="ghost icon-text-button small"
                  disabled={uploadingStudyFile}
                  onClick={() => inlineEditFileInputRef.current?.click()}
                >
                  <FontAwesomeIcon icon={faFileArrowUp} /> {uploadingStudyFile ? "Uploading..." : "Attach"}
                </button>
              </div>
              {inlineEditFileIds.length > 0 ? (
                <div className="research-chip-group">
                  {inlineEditFileIds.map((fileId) => {
                    const file = fileLookup.get(fileId);
                    if (!file) return null;
                    return (
                      <button
                        key={`inline-file-${note.id}-${fileId}`}
                        type="button"
                        className="chip small"
                        onClick={() => void handleOpenStudyFile(file)}
                      >
                        {file.original_filename}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : !isFolded ? (
            <div className="research-log-body">
              <strong>{note.title}</strong>
              <div className="research-log-text chat-markdown">
                {renderMarkdown(note.content, {
                  onReferenceClick: (label) => handleOpenReferenceByLabel(label, note.linked_reference_ids),
                  onTagClick: handleFilterByTag,
                  onFileClick: (label) => handleOpenLinkedFileByLabel(label, note.linked_file_ids),
                  onNoteClick: (label) => handleOpenLinkedNoteByLabel(label, note.linked_note_ids),
                })}
              </div>
              {renderReferencedFilePreviews(note.content, note.linked_file_ids)}
              {note.tags.length > 0 ? (
                <div className="research-chip-group">
                  {note.tags.map((tag) => (
                    <button key={`${note.id}-tag-${tag}`} type="button" className="chip small" onClick={() => handleFilterByTag(tag)}>
                      #{tag}
                    </button>
                  ))}
                </div>
              ) : null}
              {note.linked_reference_ids.length > 0 ? (
                <div className="research-chip-group">
                  {note.linked_reference_ids.map((referenceId) => {
                    const ref = references.find((item) => item.id === referenceId);
                    if (!ref) return null;
                    return (
                      <button
                        key={`${note.id}-ref-${referenceId}`}
                        type="button"
                        className="chip small"
                        onClick={() => handleOpenLinkedReference(referenceId)}
                      >
                        {formatRefLabel(ref)}
                      </button>
                    );
                  })}
                </div>
              ) : null}
              {note.linked_file_ids.length > 0 ? (
                <div className="research-chip-group">
                  {note.linked_file_ids.map((fileId) => {
                    const file = fileLookup.get(fileId);
                    if (!file) return null;
                    return (
                      <button
                        key={`${note.id}-file-${fileId}`}
                        type="button"
                        className="chip small"
                        onClick={() => void handleOpenStudyFile(file)}
                      >
                        {file.original_filename}
                      </button>
                    );
                  })}
                </div>
              ) : null}
              {linkedNotes.length > 0 ? (
                <div className="research-chip-group">
                  {linkedNotes.map((linkedNote) => (
                    <button
                      key={`${note.id}-note-${linkedNote.id}`}
                      type="button"
                      className="chip small"
                      onClick={() => handleOpenLinkedNote(linkedNote.id)}
                    >
                      [[{linkedNote.title || "Untitled Log"}]]
                    </button>
                  ))}
                </div>
              ) : null}
              {backlinkNotes.length > 0 ? (
                <div className="research-linked-note-block">
                  <span className="research-linked-note-label">Backlinks</span>
                  <div className="research-chip-group">
                    {backlinkNotes.map((backlinkNote) => (
                      <button
                        key={`${note.id}-backlink-${backlinkNote.id}`}
                        type="button"
                        className="chip small"
                        onClick={() => handleOpenLinkedNote(backlinkNote.id)}
                      >
                        [[{backlinkNote.title || "Untitled Log"}]]
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              {note.action_items.length > 0 ? (
                <div className="research-note-action-list">
                  {note.action_items.map((action) => renderActionItem(action, `${note.id}-${action.id}`))}
                </div>
              ) : null}
              {note.replies.length > 0 ? (
                <div className="research-log-replies">
                  {note.replies.map(renderReply)}
                </div>
              ) : null}
              {isReplying ? (
                <div className="research-log-reply-composer">
                  <textarea
                    className="research-inline-content research-log-reply-input"
                    value={replyDraft}
                    ref={replyingNoteId === note.id ? replyInputRef : null}
                    onChange={(event) => {
                      const textarea = event.target;
                      handleContentChange(textarea.value, textarea.selectionStart, textarea, "reply", { replyNoteId: note.id });
                    }}
                    rows={2}
                    placeholder="Reply (% refs, @ people)"
                    onKeyDown={(event) => {
                      handleMentionKeyDown(event);
                      if (mentionOpen) return;
                      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                        event.preventDefault();
                        void handleCreateNoteReply(note.id);
                      }
                      if (event.key === "Escape") {
                        setReplyingNoteId(null);
                      }
                    }}
                  />
                  {(replyRefIds[note.id] || []).length > 0 ? (
                    <div className="research-chip-group">
                      {(replyRefIds[note.id] || []).map((referenceId) => {
                        const ref = references.find((item) => item.id === referenceId);
                        if (!ref) return null;
                        return (
                          <span key={`${note.id}-reply-ref-${referenceId}`} className="chip small">
                            {formatRefLabel(ref)}
                            <button
                              type="button"
                              className="ghost icon-only"
                              onClick={() =>
                                setReplyRefIds((current) => ({
                                  ...current,
                                  [note.id]: (current[note.id] || []).filter((id) => id !== referenceId),
                                }))
                              }
                            >
                              ×
                            </button>
                          </span>
                        );
                      })}
                    </div>
                  ) : null}
                  <div className="research-log-reply-actions">
                    <button
                      type="button"
                      className="meetings-new-btn"
                      disabled={!replyDraft.trim() || submittingReplyNoteId === note.id}
                      onClick={() => void handleCreateNoteReply(note.id)}
                    >
                      {submittingReplyNoteId === note.id ? "Replying..." : "Reply"}
                    </button>
                    <button type="button" className="ghost icon-text-button small" onClick={() => setReplyingNoteId(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
          {!isFolded ? (
          <div className="research-log-footer">
            <div className="research-log-meta">
              <span>{linkedReferencesLabel}</span>
              {note.linked_file_ids.length > 0 ? <span>{linkedFilesLabel}</span> : null}
              {linkedNotes.length > 0 ? <span>{linkedNotes.length} links</span> : null}
              {note.action_items.length > 0 ? <span>{note.action_items.length} {note.action_items.length === 1 ? "action" : "actions"}</span> : null}
              {iterationState.assigned && iterationState.iterationTitle ? <span>{iterationState.iterationTitle}</span> : null}
              <span>{note.replies.length} {note.replies.length === 1 ? "reply" : "replies"}</span>
            </div>
            <div className="research-log-actions">
              {!isEditing ? (
                <button
                  type="button"
                  className="ghost icon-text-button small"
                  onClick={() => {
                    setReplyingNoteId((current) => current === note.id ? null : note.id);
                    setReplyDrafts((current) => ({ ...current, [note.id]: current[note.id] || "" }));
                  }}
                >
                  <FontAwesomeIcon icon={faComment} /> Reply
                </button>
              ) : null}
              {!isIndexNote(note) ? (
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
              ) : null}
            </div>
          </div>
          ) : null}
        </article>
      );
    };

    function toggleIterationCollapsed(iterationId: string) {
      setCollapsedIterationIds((current) => {
        const next = new Set(current);
        if (next.has(iterationId)) next.delete(iterationId);
        else next.add(iterationId);
        return next;
      });
    }

    function renderIterationCluster(iterationId: string, clusterNotes: ResearchNote[]) {
      const iteration = iterationLookup.get(iterationId);
      const collapsed = collapsedIterationIds.has(iterationId);
      const stackNotes = clusterNotes.slice(0, 3);
      return (
        <div key={`iteration-cluster-${iterationId}`} className={`iteration-cluster${collapsed ? " collapsed" : ""}`}>
          <button
            type="button"
            className="iteration-cluster-rail"
            onClick={() => toggleIterationCollapsed(iterationId)}
            title={collapsed ? "Expand iteration" : "Collapse iteration"}
          >
            <span className="iteration-cluster-rail-line" />
            <span className="iteration-cluster-rail-count">{clusterNotes.length}</span>
          </button>
          <div className="iteration-cluster-body">
            {collapsed ? (
              <div
                className="iteration-stack"
                style={{ ["--stack-n" as string]: stackNotes.length } as React.CSSProperties}
                onClick={() => toggleIterationCollapsed(iterationId)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") toggleIterationCollapsed(iterationId); }}
              >
                <span className="iteration-stack-label">
                  <strong>{iteration?.title || "Iteration"}</strong>
                  <span>{clusterNotes.length} logs</span>
                </span>
                <div className="iteration-stack-deck">
                  {stackNotes.map((note, index) => (
                    <div
                      key={`${iterationId}-stack-${note.id}`}
                      className="iteration-stack-layer"
                      style={{ ["--i" as string]: index } as React.CSSProperties}
                    >
                      {renderNoteCard(note, { stackPreview: true })}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="research-log-list">
                {clusterNotes.map((clusterNote) => renderNoteCard(clusterNote))}
              </div>
            )}
          </div>
        </div>
      );
    }

    function renderNoteList(noteItems: ResearchNote[]) {
      const renderedIterationIds = new Set<string>();
      return noteItems.map((note) => {
        const iterationState = noteIterationState(note.id);
        if (!iterationState.iterationId) {
          return renderNoteCard(note);
        }
        if (renderedIterationIds.has(iterationState.iterationId)) {
          return null;
        }
        renderedIterationIds.add(iterationState.iterationId);
        const clusterNotes = noteItems.filter((item) => noteIterationState(item.id).iterationId === iterationState.iterationId);
        return renderIterationCluster(iterationState.iterationId, clusterNotes);
      });
    }

    function renderDatedNoteSections(noteItems: ResearchNote[]) {
      const pinnedNotes = noteItems.filter((item) => item.pinned);
      const regularNotes = noteItems.filter((item) => !item.pinned);
      const datedSections = new Map<string, ResearchNote[]>();

      regularNotes.forEach((note) => {
        const label = logDateBucketLabel(note.created_at);
        const current = datedSections.get(label) || [];
        current.push(note);
        datedSections.set(label, current);
      });

      return (
        <>
          <section className="research-log-section research-index-section">
            <div className="log-group-label log-group-index">
              <span>Index</span>
            </div>
            <div className="research-log-list">
              {indexNote ? (
                renderNoteCard(indexNote)
              ) : (
                <button type="button" className="research-index-empty-card" onClick={openIndexNote}>
                  <FontAwesomeIcon icon={faPlus} />
                  <span>New Index</span>
                </button>
              )}
            </div>
          </section>
          {pinnedNotes.length > 0 ? (
            <section className="research-log-section">
              <div className="log-group-label log-group-pinned">
                <FontAwesomeIcon icon={faThumbtack} />
                <span>Pinned</span>
                <span className="delivery-tab-count">{pinnedNotes.length}</span>
              </div>
              <div className="research-log-list">
                {renderNoteList(pinnedNotes)}
              </div>
            </section>
          ) : null}
          {Array.from(datedSections.entries()).map(([label, sectionNotes]) => (
            <section key={`note-section-${label}`} className="research-log-section">
              <div className="log-group-label">
                <span>{label}</span>
                <span className="delivery-tab-count">{sectionNotes.length}</span>
              </div>
              <div className="research-log-list">
                {renderNoteList(sectionNotes)}
              </div>
            </section>
          ))}
        </>
      );
    }

    return (
      <>
        <div className={`research-log-composer${composerExpanded ? " expanded" : ""}`}>
          <input
            ref={quickLogFileInputRef}
            type="file"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleUploadStudyFile(file, { linkToQuickLog: true });
            }}
          />
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
            onBlur={(event) => {
              const related = event.relatedTarget as HTMLElement | null;
              if (related?.closest(".research-log-composer")) return;
              if (!quickLogContent.trim() && !quickLogTitle.trim()) setComposerExpanded(false);
            }}
            onKeyDown={(event) => {
              handleMentionKeyDown(event);
              if (mentionOpen) return;
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void handleQuickLogSubmit();
              }
            }}
            placeholder={composerExpanded ? "Content (markdown, % refs, @ people)" : "Log a finding, observation, or note..."}
          />
          {composerExpanded ? (
            <div className="research-log-composer-actions">
              {renderLanePills(quickLogLane, setQuickLogLane, { className: "research-log-lane-pills" })}
              <button
                type="button"
                className="ghost icon-text-button small"
                disabled={uploadingStudyFile}
                onClick={() => quickLogFileInputRef.current?.click()}
              >
                <FontAwesomeIcon icon={faFileArrowUp} /> {uploadingStudyFile ? "Uploading..." : "Attach"}
              </button>
              <button
                type="button"
                className="ghost icon-text-button small"
                onClick={() => openCreateNoteModal({ seedFromQuickLog: true })}
              >
                <FontAwesomeIcon icon={faBookOpen} /> Editor
              </button>
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
          {composerExpanded && quickLogFileIds.length > 0 ? (
            <div className="research-chip-group">
              {quickLogFileIds.map((fileId) => {
                const file = fileLookup.get(fileId);
                if (!file) return null;
                return (
                  <span key={`quick-file-${fileId}`} className="chip small">
                    {file.original_filename}
                    <button type="button" className="ghost icon-only" onClick={() => setQuickLogFileIds((current) => current.filter((id) => id !== fileId))}>×</button>
                  </span>
                );
              })}
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
              ref={noteSearchInputRef}
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

        <div className="research-log-stream">
          {renderDatedNoteSections(orderedNotes)}
          {orderedNotes.length === 0 ? (
            <p className="empty-message">No logs in this study.</p>
          ) : null}
        </div>

        {mentionOpen && mentionAnchor ? (
          <div
            className="mention-dropdown"
            style={{ position: "fixed", top: mentionAnchor.top, left: mentionAnchor.left }}
          >
            {mentionResults.length === 0 ? (
              <div className="mention-empty">{mentionTrigger === "%" ? "No references found" : "No members found"}</div>
            ) : (
              mentionResults.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  className={`mention-item${index === mentionActiveIndex ? " active" : ""}`}
                  onMouseDown={(event) => { event.preventDefault(); selectMention(item); }}
                  onMouseEnter={() => setMentionActiveIndex(index)}
                >
                  {mentionTrigger === "%" ? (
                    <>
                      <span className="mention-item-title">{(item as ResearchReference).title}</span>
                      <span className="mention-item-meta">
                        {(item as ResearchReference).authors.length > 0 ? (item as ResearchReference).authors[0] : ""}
                        {(item as ResearchReference).year ? ` · ${(item as ResearchReference).year}` : ""}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="mention-item-title">@{memberMentionHandle((item as ResearchCollectionMember).member_name)}</span>
                      <span className="mention-item-meta">
                        {(item as ResearchCollectionMember).member_name}
                        {(item as ResearchCollectionMember).role ? ` · ${(item as ResearchCollectionMember).role}` : ""}
                      </span>
                    </>
                  )}
                </button>
              ))
            )}
          </div>
        ) : null}
      </>
    );
  }

  function renderTodosTab() {
    if (!selectedCollectionId) {
      return <p className="empty-message">Select a study first.</p>;
    }

    const allActions = notes
      .filter((note) => note.collection_id === selectedCollectionId)
      .flatMap((note) =>
        (note.action_items || []).map((action) => ({
          ...action,
          sourceNote: note,
        })),
      )
      .sort((a, b) => {
        if (a.is_done !== b.is_done) return a.is_done ? 1 : -1;
        if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
        if (a.due_date) return -1;
        if (b.due_date) return 1;
        return b.sourceNote.created_at.localeCompare(a.sourceNote.created_at);
      });

    const today = new Date().toISOString().slice(0, 10);
    const filteredActions = allActions.filter((item) => {
      if (todoQuickFilter === "mine") return item.assignee_user_id === currentUser.id;
      if (todoQuickFilter === "overdue") return item.status !== "done" && Boolean(item.due_date && item.due_date < today);
      return true;
    });
    const openActions = filteredActions.filter((item) => item.status === "open");
    const doingActions = filteredActions.filter((item) => item.status === "doing");
    const doneActions = filteredActions.filter((item) => item.status === "done");

    function openSourceLog(noteId: string) {
      setTab("notes");
      setActiveInboxNoteId(noteId);
      const target = document.querySelector(`[data-note-id="${noteId}"]`) as HTMLElement | null;
      target?.scrollIntoView({ block: "center", behavior: "smooth" });
      window.setTimeout(() => target?.focus(), 120);
    }

    function handleTodoDragStart(actionId: string) {
      setDraggingTodoActionId(actionId);
    }

    function handleTodoDragEnd() {
      setDraggingTodoActionId(null);
      setTodoDropStatus(null);
    }

    async function handleTodoDrop(nextStatus: "open" | "doing" | "done") {
      if (!draggingTodoActionId) return;
      setTodoDropStatus(null);
      const action = filteredActions.find((item) => item.id === draggingTodoActionId);
      if (!action || action.status === nextStatus) {
        setDraggingTodoActionId(null);
        return;
      }
      await handleUpdateNoteActionItem(draggingTodoActionId, nextStatus);
      setDraggingTodoActionId(null);
    }

    const renderStatusAction = (item: (typeof filteredActions)[number], nextStatus: "open" | "doing" | "done", label: string) => (
      <button
        type="button"
        className={`chip small research-todo-status-btn${item.status === nextStatus ? " active" : ""}`}
        disabled={updatingActionItemId === item.id || item.status === nextStatus}
        onClick={() => void handleUpdateNoteActionItem(item.id, nextStatus)}
      >
        {label}
      </button>
    );

    const renderTodoRow = (item: (typeof filteredActions)[number]) => (
      <div key={item.id} className={`kanban-list-card${item.is_done ? " done" : ""}`}>
        <div className="kanban-list-card-top">
          <button
            type="button"
            className={`research-note-action-checkbox research-note-action-toggle${item.status === "done" ? " done" : ""}`}
            disabled={updatingActionItemId === item.id}
            onClick={() => void handleUpdateNoteActionItem(item.id, item.status === "done" ? "open" : "done")}
          >
            {item.status === "done" ? "[x]" : "[ ]"}
          </button>
          <strong className="kanban-card-title">{item.text}</strong>
          <div className="kanban-list-status-actions">
            {renderStatusAction(item, "open", "Open")}
            {renderStatusAction(item, "doing", "Doing")}
            {renderStatusAction(item, "done", "Done")}
          </div>
        </div>
        <div className="kanban-card-footer">
          <span className="kanban-card-source" role="button" tabIndex={0} onClick={() => openSourceLog(item.sourceNote.id)}>
            {item.sourceNote.title || "Untitled Log"}
          </span>
          <span className="kanban-card-right">
            {item.due_date ? (
              <span className={`kanban-card-date${item.status !== "done" && item.due_date < today ? " overdue" : ""}`}>
                {formatIsoDateLocal(new Date(`${item.due_date}T00:00:00`))}
              </span>
            ) : null}
            {item.assignee_name ? (
              <LogAvatar name={item.assignee_name} avatarUrl={item.assignee_avatar_url} className="kanban-card-avatar" />
            ) : null}
          </span>
        </div>
      </div>
    );

    const renderBoardColumn = (
      title: string,
      items: typeof filteredActions,
      status: "open" | "doing" | "done",
    ) => (
      <section className={`kanban-col${todoDropStatus === status ? " drop-target" : ""}`}>
        <div className="kanban-col-head">
          <span className={`kanban-col-dot status-${status}`} />
          <span className="kanban-col-title">{title}</span>
          <span className="kanban-col-count">{items.length}</span>
        </div>
        <div
          className="kanban-col-cards"
          onDragOver={(event) => {
            event.preventDefault();
            if (draggingTodoActionId) setTodoDropStatus(status);
          }}
          onDragLeave={() => {
            if (todoDropStatus === status) setTodoDropStatus(null);
          }}
          onDrop={(event) => {
            event.preventDefault();
            void handleTodoDrop(status);
          }}
        >
          {items.map((item) => (
            <div
              key={item.id}
              className={`kanban-card${item.status === "done" ? " done" : ""}${draggingTodoActionId === item.id ? " dragging" : ""}`}
              draggable
              onDragStart={() => handleTodoDragStart(item.id)}
              onDragEnd={handleTodoDragEnd}
              onClick={() => openSourceLog(item.sourceNote.id)}
              role="button"
              tabIndex={0}
            >
              <strong className="kanban-card-title">{item.text}</strong>
              <div className="kanban-card-footer">
                <span className="kanban-card-source">{item.sourceNote.title || "Untitled Log"}</span>
                <span className="kanban-card-right">
                  {item.due_date ? (
                    <span className={`kanban-card-date${item.status !== "done" && item.due_date < today ? " overdue" : ""}`}>
                      {formatIsoDateLocal(new Date(`${item.due_date}T00:00:00`))}
                    </span>
                  ) : null}
                  {item.assignee_name ? (
                    <LogAvatar name={item.assignee_name} avatarUrl={item.assignee_avatar_url} className="kanban-card-avatar" />
                  ) : null}
                </span>
              </div>
            </div>
          ))}
          {items.length === 0 ? (
            <div className="kanban-col-empty">No items</div>
          ) : null}
        </div>
      </section>
    );

    return (
      <div className="research-todo-shell">
        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <span>{allActions.length} actions</span>
            <span className="setup-summary-sep" />
            <span>{openActions.length} open</span>
            <span className="setup-summary-sep" />
            <span>{doingActions.length} doing</span>
            <span className="setup-summary-sep" />
            <span>{doneActions.length} done</span>
          </div>
        </div>
        <div className="meetings-toolbar">
          <div className="meetings-filter-group">
            <button type="button" className={`chip small research-todo-filter-chip${todoQuickFilter === "all" ? " active" : ""}`} onClick={() => setTodoQuickFilter("all")}>
              All
            </button>
            <button type="button" className={`chip small research-todo-filter-chip${todoQuickFilter === "mine" ? " active" : ""}`} onClick={() => setTodoQuickFilter("mine")}>
              Assigned to me
            </button>
            <button type="button" className={`chip small research-todo-filter-chip${todoQuickFilter === "overdue" ? " active" : ""}`} onClick={() => setTodoQuickFilter("overdue")}>
              Overdue
            </button>
          </div>
          <div className="kanban-view-toggle">
            <button type="button" className={`ghost icon-only kanban-view-btn${todoView === "list" ? " active" : ""}`} onClick={() => setTodoView("list")} title="List view">
              <FontAwesomeIcon icon={faList} />
            </button>
            <button type="button" className={`ghost icon-only kanban-view-btn${todoView === "board" ? " active" : ""}`} onClick={() => setTodoView("board")} title="Board view">
              <FontAwesomeIcon icon={faGrip} />
            </button>
          </div>
        </div>
        {todoView === "board" ? (
          <div className="kanban-board">
            {renderBoardColumn("To do", openActions, "open")}
            {renderBoardColumn("Doing", doingActions, "doing")}
            {renderBoardColumn("Done", doneActions, "done")}
          </div>
        ) : (
          <div className="research-todo-sections">
            <section className="research-todo-section">
              <div className="kanban-col-head">
                <span className="kanban-col-dot status-open" />
                <span className="kanban-col-title">To do</span>
                <span className="kanban-col-count">{openActions.length}</span>
              </div>
              <div className="research-todo-list">
                {openActions.length === 0 ? <div className="kanban-col-empty">No open actions</div> : openActions.map(renderTodoRow)}
              </div>
            </section>
            <section className="research-todo-section">
              <div className="kanban-col-head">
                <span className="kanban-col-dot status-doing" />
                <span className="kanban-col-title">Doing</span>
                <span className="kanban-col-count">{doingActions.length}</span>
              </div>
              <div className="research-todo-list">
                {doingActions.length === 0 ? <div className="kanban-col-empty">No in-progress actions</div> : doingActions.map(renderTodoRow)}
              </div>
            </section>
            <section className="research-todo-section">
              <div className="kanban-col-head">
                <span className="kanban-col-dot status-done" />
                <span className="kanban-col-title">Done</span>
                <span className="kanban-col-count">{doneActions.length}</span>
              </div>
              <div className="research-todo-list">
                {doneActions.length === 0 ? <div className="kanban-col-empty">No completed actions</div> : doneActions.map(renderTodoRow)}
              </div>
            </section>
          </div>
        )}
      </div>
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
    const nextActions = [
      !paperSubmissionDeadline ? "Set submission deadline" : null,
      !paperMotivation.trim() && gapNotes.length > 0 ? "Draft motivation from gap logs" : null,
      paperAuthors.length === 0 ? "Add authors" : null,
      paperQuestions.length === 0 ? "Add a research question" : null,
      unprocessedInboxCount > 0 ? `Process ${unprocessedInboxCount} inbox item${unprocessedInboxCount !== 1 ? "s" : ""}` : null,
      unsupportedClaims > 0 ? `Support ${unsupportedClaims} claim${unsupportedClaims !== 1 ? "s" : ""}` : null,
      weakSections > 0 ? `Strengthen ${weakSections} section${weakSections !== 1 ? "s" : ""}` : null,
    ].filter(Boolean) as string[];
    const paperHeaderSignals = [
      <span key="status" className="chip small">{paperStatus.replace(/_/g, " ")}</span>,
      paperSubmissionDeadline ? (
        <span key="submission" className="chip small">{`Submission ${new Date(paperSubmissionDeadline).toLocaleDateString()}`}</span>
      ) : null,
      unprocessedInboxCount > 0 ? (
        <span key="inbox" className="chip small paper-health-alert">{unprocessedInboxCount} inbox to process</span>
      ) : null,
      unsupportedClaims > 0 ? (
        <span key="unsupported" className="chip small paper-health-alert">{unsupportedClaims} unsupported claims</span>
      ) : null,
      weakSections > 0 ? (
        <span key="weak" className="chip small paper-health-alert">{weakSections} weak sections</span>
      ) : null,
    ].filter(Boolean);
    const primaryNextAction = nextActions[0] || null;
    const noteLabel = (note: ResearchNote) => note.title?.trim() || deriveLogTitle(note.content) || "Log";
    const resultLabel = (result: ResearchStudyResult) => result.title?.trim() || "Result";
    const questionLabel = (question: ResearchPaperQuestion, index: number) => question.text.trim() || `Question ${index + 1}`;
    const claimLabel = (claim: ResearchPaperClaim, index: number) => claim.text.trim() || `Claim ${index + 1}`;
    const sectionLabel = (section: ResearchPaperSection, index: number) => section.title.trim() || `Section ${index + 1}`;
    const noteById = new Map(collectionNotes.map((note) => [note.id, note] as const));
    const referenceById = new Map(collectionReferences.map((reference) => [reference.id, reference] as const));
    const resultById = new Map(collectionResults.map((result) => [result.id, result] as const));
    const questionById = new Map(paperQuestions.map((question) => [question.id, question] as const));
    const claimById = new Map(paperClaims.map((claim) => [claim.id, claim] as const));
    const paperEditorReferenceSuggestions = collectionReferences.map((item) => ({
      id: item.id,
      label: formatRefLabel(item),
      meta: item.authors.join(", "),
    }));
    const paperEditorFileSuggestions = studyFiles
      .filter((item) => item.collection_id === selectedCollectionId)
      .map((item) => ({
        id: item.id,
        label: item.original_filename,
        meta: item.mime_type || undefined,
      }));
    const paperEditorFileIds = studyFiles
      .filter((item) => item.collection_id === selectedCollectionId)
      .map((item) => item.id);
    const paperMotivationPreviewFiles = extractMarkdownFileLabels(inlinePaperMotivation)
      .map((label) => resolveLinkedFileByLabel(label, paperEditorFileIds))
      .filter((item): item is ResearchStudyFile => Boolean(item))
      .filter((item, index, arr) => arr.findIndex((candidate) => candidate.id === item.id) === index);
    const paperEditorNoteSuggestions = notes
      .filter((item) => item.collection_id === selectedCollectionId)
      .map((item) => ({
        id: item.id,
        label: item.title || deriveLogTitle(item.content) || "Untitled Log",
        meta: formatLogTimestamp(item.created_at),
      }));
    const paperEditorMemberSuggestions = (collectionDetail.members || []).map((member) => ({
      id: member.member_id,
      label: `@${memberMentionHandle(member.member_name)}`,
      meta: member.member_name,
    }));

    function commitPaperTitle() {
      setPaperTitle(inlinePaperTitle.trim());
      setEditingPaperTitle(false);
    }

    function commitPaperVenue() {
      setPaperVenue(inlinePaperVenue.trim());
      setEditingPaperVenue(false);
    }

    function commitPaperOverleaf() {
      setPaperOverleafUrl(inlinePaperOverleaf.trim());
      setEditingPaperOverleaf(false);
    }

    function commitPaperStatus() {
      setPaperStatus(inlinePaperStatus);
      setEditingPaperStatus(false);
    }

    function commitPaperRegistration() {
      setPaperRegistrationDeadline(inlinePaperRegistration);
      setEditingPaperRegistration(false);
    }

    function commitPaperSubmission() {
      setPaperSubmissionDeadline(inlinePaperSubmission);
      setEditingPaperSubmission(false);
    }

    function commitPaperDecision() {
      setPaperDecisionDate(inlinePaperDecision);
      setEditingPaperDecision(false);
    }

    function commitPaperMotivation() {
      setPaperMotivation(inlinePaperMotivation);
      setEditingPaperMotivation(false);
    }

    function renderInlineEntities(
      entries: Array<{ id: string; label: string; onClick?: () => void }>,
      emptyLabel: string,
    ) {
      if (entries.length === 0) {
        return <span className="paper-inline-empty">{emptyLabel}</span>;
      }
      return (
        <div className="paper-inline-link-list">
          {entries.map((entry) =>
            entry.onClick ? (
              <button key={entry.id} type="button" className="paper-inline-link" onClick={entry.onClick}>
                {entry.label}
              </button>
            ) : (
              <span key={entry.id} className="paper-inline-link paper-inline-link-static">
                {entry.label}
              </span>
            ),
          )}
        </div>
      );
    }

    return (
      <div className="paper-workspace">
        <div className="setup-summary-bar paper-summary-bar">
          <div className="setup-summary-stats">
            <span>{paperQuestions.length} questions</span>
            <span className="setup-summary-sep" />
            <span>{paperClaims.length} claims</span>
            <span className="setup-summary-sep" />
            <span>{paperSections.length} sections</span>
            <span className="setup-summary-sep" />
            <span>{collectionResults.length} results</span>
          </div>
          <div className="research-header-actions">
            {!isStudent ? (
              <>
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
                </>
              ) : null}
          </div>
        </div>

        <section className="meetings-detail-section paper-manuscript-block">
          <div className="paper-manuscript-header">
            <div className="paper-manuscript-title">
              <strong>Paper</strong>
              <div className="paper-health-row">{paperHeaderSignals}</div>
            </div>
          </div>

          {primaryNextAction ? (
            <div className="paper-next-action-strip">
              <button
                type="button"
                className="paper-next-action-link"
                onClick={() => {
                  if (!paperSubmissionDeadline) return;
                  if (paperAuthors.length === 0) {
                    document.querySelector(".paper-author-add-row select")?.scrollIntoView({ behavior: "smooth", block: "center" });
                    return;
                  }
                  if (paperQuestions.length === 0) {
                    document.querySelector(".paper-note-block")?.scrollIntoView({ behavior: "smooth", block: "center" });
                    return;
                  }
                }}
              >
                {primaryNextAction}
              </button>
            </div>
          ) : null}

          <div className="paper-manuscript-topline">
            <div className="paper-inline-form paper-inline-form-title">
              <span>Title</span>
              {editingPaperTitle ? (
                <input
                  autoFocus
                  value={inlinePaperTitle}
                  onChange={(event) => setInlinePaperTitle(event.target.value)}
                  onBlur={commitPaperTitle}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      commitPaperTitle();
                    } else if (event.key === "Escape") {
                      setInlinePaperTitle(paperTitle);
                      setEditingPaperTitle(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className={`paper-inline-value paper-inline-value-title${paperTitle.trim() ? "" : " is-placeholder"}`}
                  onClick={() => {
                    setInlinePaperTitle(paperTitle);
                    setEditingPaperTitle(true);
                  }}
                >
                  {paperTitle.trim() || "Untitled paper"}
                </button>
              )}
            </div>
            <div className="paper-inline-form">
              <span>Venue</span>
              {editingPaperVenue ? (
                <input
                  autoFocus
                  value={inlinePaperVenue}
                  onChange={(event) => setInlinePaperVenue(event.target.value)}
                  onBlur={commitPaperVenue}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      commitPaperVenue();
                    } else if (event.key === "Escape") {
                      setInlinePaperVenue(paperVenue);
                      setEditingPaperVenue(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className={`paper-inline-value${paperVenue.trim() ? "" : " is-placeholder"}`}
                  onClick={() => {
                    setInlinePaperVenue(paperVenue);
                    setEditingPaperVenue(true);
                  }}
                >
                  {paperVenue.trim() || "Set venue"}
                </button>
              )}
            </div>
            <div className="paper-inline-form">
              <span>Overleaf</span>
              {editingPaperOverleaf ? (
                <input
                  autoFocus
                  value={inlinePaperOverleaf}
                  onChange={(event) => setInlinePaperOverleaf(event.target.value)}
                  onBlur={commitPaperOverleaf}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      commitPaperOverleaf();
                    } else if (event.key === "Escape") {
                      setInlinePaperOverleaf(paperOverleafUrl);
                      setEditingPaperOverleaf(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className={`paper-inline-value${paperOverleafUrl.trim() ? "" : " is-placeholder"}`}
                  onClick={() => {
                    setInlinePaperOverleaf(paperOverleafUrl);
                    setEditingPaperOverleaf(true);
                  }}
                >
                  {paperOverleafUrl.trim() || "Set overleaf"}
                </button>
              )}
            </div>
          </div>

          <div className="paper-manuscript-meta-row">
            <div className="paper-compact-field">
              <span>Status</span>
              {editingPaperStatus ? (
                <select
                  autoFocus
                  value={inlinePaperStatus}
                  onChange={(event) => setInlinePaperStatus(event.target.value)}
                  onBlur={commitPaperStatus}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setInlinePaperStatus(paperStatus);
                      setEditingPaperStatus(false);
                    }
                  }}
                >
                  <option value="not_started">Not started</option>
                  <option value="drafting">Drafting</option>
                  <option value="internal_review">Internal review</option>
                  <option value="submitted">Submitted</option>
                  <option value="published">Published</option>
                </select>
              ) : (
                <button
                  type="button"
                  className="paper-inline-chip-button"
                  onClick={() => {
                    setInlinePaperStatus(paperStatus);
                    setEditingPaperStatus(true);
                  }}
                >
                  {paperStatus.replace(/_/g, " ")}
                </button>
              )}
            </div>
            <div className="paper-compact-field">
              <span>Registration</span>
              {editingPaperRegistration ? (
                <input
                  autoFocus
                  type="date"
                  value={inlinePaperRegistration}
                  onChange={(event) => setInlinePaperRegistration(event.target.value)}
                  onBlur={commitPaperRegistration}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setInlinePaperRegistration(paperRegistrationDeadline);
                      setEditingPaperRegistration(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className={`paper-inline-chip-button${paperRegistrationDeadline ? "" : " is-placeholder"}`}
                  onClick={() => {
                    setInlinePaperRegistration(paperRegistrationDeadline);
                    setEditingPaperRegistration(true);
                  }}
                >
                  {paperRegistrationDeadline || "Set registration"}
                </button>
              )}
            </div>
            <div className="paper-compact-field">
              <span>Submission</span>
              {editingPaperSubmission ? (
                <input
                  autoFocus
                  type="date"
                  value={inlinePaperSubmission}
                  onChange={(event) => setInlinePaperSubmission(event.target.value)}
                  onBlur={commitPaperSubmission}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setInlinePaperSubmission(paperSubmissionDeadline);
                      setEditingPaperSubmission(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className={`paper-inline-chip-button${paperSubmissionDeadline ? "" : " is-placeholder"}`}
                  onClick={() => {
                    setInlinePaperSubmission(paperSubmissionDeadline);
                    setEditingPaperSubmission(true);
                  }}
                >
                  {paperSubmissionDeadline || "Set submission"}
                </button>
              )}
            </div>
            <div className="paper-compact-field">
              <span>Decision</span>
              {editingPaperDecision ? (
                <input
                  autoFocus
                  type="date"
                  value={inlinePaperDecision}
                  onChange={(event) => setInlinePaperDecision(event.target.value)}
                  onBlur={commitPaperDecision}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setInlinePaperDecision(paperDecisionDate);
                      setEditingPaperDecision(false);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className={`paper-inline-chip-button${paperDecisionDate ? "" : " is-placeholder"}`}
                  onClick={() => {
                    setInlinePaperDecision(paperDecisionDate);
                    setEditingPaperDecision(true);
                  }}
                >
                  {paperDecisionDate || "Set decision"}
                </button>
              )}
            </div>
          </div>

          <div className="paper-note-editor-shell">
            <div className="paper-note-editor-head">
              <strong>Motivation</strong>
            </div>
            {editingPaperMotivation ? (
              <div className="paper-note-editor-rich">
                <StudyLogRichEditor
                  key={`paper-motivation:${selectedCollectionId}:${editingPaperMotivation ? "edit" : "read"}`}
                  value={inlinePaperMotivation}
                  placeholder="Write motivation"
                  onChange={setInlinePaperMotivation}
                  referenceSuggestions={paperEditorReferenceSuggestions}
                  fileSuggestions={paperEditorFileSuggestions}
                  noteSuggestions={paperEditorNoteSuggestions}
                  memberSuggestions={paperEditorMemberSuggestions}
                  linkedFiles={paperMotivationPreviewFiles}
                  projectId={selectedProjectId}
                  collectionId={selectedCollectionId}
                  spaceId={activeResearchSpaceId || undefined}
                  tagSuggestions={noteTagOptions}
                  onPasteImage={async (file) => {
                    const created = await handleUploadStudyFile(file);
                    return created ? { id: created.id, label: created.original_filename } : null;
                  }}
                />
                <div className="paper-note-editor-actions">
                  <button type="button" className="ghost" onClick={() => { setInlinePaperMotivation(paperMotivation); setEditingPaperMotivation(false); }}>
                    Cancel
                  </button>
                  <button type="button" className="ghost" onClick={commitPaperMotivation}>
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <div
                role="button"
                tabIndex={0}
                className={`paper-note-editor-preview${paperMotivation.trim() ? "" : " is-placeholder"}`}
                onClick={() => {
                  setInlinePaperMotivation(paperMotivation);
                  setEditingPaperMotivation(true);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setInlinePaperMotivation(paperMotivation);
                    setEditingPaperMotivation(true);
                  }
                }}
              >
                {paperMotivation.trim()
                  ? renderMarkdown(paperMotivation, {
                      onFileClick: (label) => handleOpenLinkedFileByLabel(label, paperEditorFileIds),
                      onNoteClick: (label) => handleOpenLinkedNoteByLabel(label),
                    })
                  : "Write motivation"}
              </div>
            )}
          </div>
        </section>

        <section className="paper-manuscript-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Authors</strong>
            </div>
          </div>
          <div className="paper-stack paper-stack-plain">
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
              <div key={author.id} className="paper-note-block paper-note-block-compact">
                <div className="paper-note-head">
                  <strong>{index + 1}. {author.display_name}</strong>
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
        </section>

        <section className="paper-manuscript-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Questions</strong>
            </div>
            <button type="button" className="meetings-new-btn" onClick={() => setPaperQuestions((items) => [...items, newPaperQuestion()])}>
              <FontAwesomeIcon icon={faPlus} /> Add
            </button>
          </div>
          <div className="paper-stack paper-stack-plain">
            {paperQuestions.length === 0 ? <p className="muted-small">No questions.</p> : null}
            {paperQuestions.map((item, index) => (
              <article key={item.id} className="paper-note-block">
                <div className="paper-note-head">
                  <strong>Question {index + 1}</strong>
                  <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => setPaperQuestions((items) => items.filter((entry) => entry.id !== item.id))}>
                    <FontAwesomeIcon icon={faXmark} />
                  </button>
                </div>
                <textarea
                  className="paper-note-textarea"
                  rows={3}
                  value={item.text}
                  onChange={(event) =>
                    setPaperQuestions((items) => items.map((entry) => (entry.id === item.id ? { ...entry, text: event.target.value } : entry)))
                  }
                />
                <div className="paper-evidence-summary">
                  <div className="paper-evidence-line">
                    <strong>Logs</strong>
                    {renderInlineEntities(
                      item.note_ids
                        .map((noteId) => noteById.get(noteId))
                        .filter((note): note is ResearchNote => Boolean(note))
                        .map((note) => ({
                          id: note.id,
                          label: noteLabel(note),
                          onClick: () => {
                            setTab("notes");
                            setActiveInboxNoteId(note.id);
                          },
                        })),
                      "No logs linked",
                    )}
                  </div>
                </div>
                <details className="paper-link-details">
                  <summary className="paper-link-toggle">Edit links</summary>
                  <div className="paper-link-group">
                    {collectionNotes.map((note) => (
                      <label key={`${item.id}-question-note-${note.id}`} className="paper-link-chip">
                        <input
                          type="checkbox"
                          checked={item.note_ids.includes(note.id)}
                          onChange={() =>
                            setPaperQuestions((items) =>
                              items.map((entry) =>
                                entry.id === item.id ? { ...entry, note_ids: toggleId(entry.note_ids, note.id) } : entry,
                              ),
                            )
                          }
                        />
                        <span>{noteLabel(note)}</span>
                      </label>
                    ))}
                  </div>
                </details>
              </article>
            ))}
          </div>
        </section>

        <section className="paper-manuscript-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Claims</strong>
            </div>
            <button type="button" className="meetings-new-btn" onClick={() => setPaperClaims((items) => [...items, newPaperClaim()])}>
              <FontAwesomeIcon icon={faPlus} /> Add
            </button>
          </div>
          <div className="paper-stack paper-stack-plain">
            {paperClaims.length === 0 ? <p className="muted-small">No claims.</p> : null}
            {paperClaims.map((item, index) => (
              <article key={item.id} className={`paper-note-block${item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? " paper-note-block-alert" : ""}`}>
                <div className="paper-note-head">
                  <div className="paper-note-head-main">
                    <strong>Claim {index + 1}</strong>
                    <div className="paper-evidence-strip">
                      <span className="chip small">{item.status.replace(/_/g, " ")}</span>
                      {item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? (
                        <span className="chip small paper-health-alert">Missing evidence</span>
                      ) : null}
                      {item.audit_status ? (
                        <span className={`chip small paper-audit-status paper-audit-status-${item.audit_status}`}>{item.audit_status.replace(/_/g, " ")}</span>
                      ) : null}
                    </div>
                  </div>
                  <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => setPaperClaims((items) => items.filter((entry) => entry.id !== item.id))}>
                    <FontAwesomeIcon icon={faXmark} />
                  </button>
                </div>
                <textarea
                  className="paper-note-textarea"
                  rows={4}
                  value={item.text}
                  onChange={(event) =>
                    setPaperClaims((items) => items.map((entry) => (entry.id === item.id ? { ...entry, text: event.target.value } : entry)))
                  }
                />
                {item.audit_summary ? (
                  <div className="paper-audit-box">
                    <p>{item.audit_summary}</p>
                    <div className="paper-audit-meta">
                      {item.supporting_reference_ids.length ? <span className="muted-small">{item.supporting_reference_ids.length} supporting references</span> : null}
                      {item.supporting_note_ids.length ? <span className="muted-small">{item.supporting_note_ids.length} supporting logs</span> : null}
                      {item.audit_confidence !== null ? <span className="muted-small">{Math.round(item.audit_confidence * 100)}% confidence</span> : null}
                      {item.audited_at ? <span className="muted-small">{formatRelativeTime(item.audited_at)}</span> : null}
                    </div>
                    {item.missing_evidence.length > 0 ? (
                      <div className="paper-evidence-strip">
                        {item.missing_evidence.map((entry) => (
                          <span key={`${item.id}-${entry}`} className="chip small paper-health-alert">{entry}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="paper-evidence-summary">
                  <div className="paper-evidence-line">
                    <strong>Questions</strong>
                    {renderInlineEntities(
                      item.question_ids
                        .map((questionId) => questionById.get(questionId))
                        .filter((question): question is ResearchPaperQuestion => Boolean(question))
                        .map((question, questionIndex) => ({
                          id: question.id,
                          label: questionLabel(question, paperQuestions.findIndex((entry) => entry.id === question.id)),
                        })),
                      "No questions linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>References</strong>
                    {renderInlineEntities(
                      item.reference_ids
                        .map((referenceId) => referenceById.get(referenceId))
                        .filter((reference): reference is ResearchReference => Boolean(reference))
                        .map((reference) => ({
                          id: reference.id,
                          label: reference.title || "Reference",
                          onClick: () => {
                            setTab("references");
                            openEditReferenceModal(reference);
                          },
                        })),
                      "No references linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>Logs</strong>
                    {renderInlineEntities(
                      item.note_ids
                        .map((noteId) => noteById.get(noteId))
                        .filter((note): note is ResearchNote => Boolean(note))
                        .map((note) => ({
                          id: note.id,
                          label: noteLabel(note),
                          onClick: () => {
                            setTab("notes");
                            setActiveInboxNoteId(note.id);
                          },
                        })),
                      "No logs linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>Results</strong>
                    {renderInlineEntities(
                      item.result_ids
                        .map((resultId) => resultById.get(resultId))
                        .filter((result): result is ResearchStudyResult => Boolean(result))
                        .map((result) => ({
                          id: result.id,
                          label: resultLabel(result),
                          onClick: () => setTab("iterations"),
                        })),
                      "No results linked",
                    )}
                  </div>
                </div>
                <details className="paper-link-details">
                  <summary className="paper-link-toggle">Edit links</summary>
                  <div className="paper-link-block">
                    <strong>Questions</strong>
                    <div className="paper-link-group">
                      {paperQuestions.map((question) => (
                        <label key={`${item.id}-${question.id}`} className="paper-link-chip">
                          <input
                            type="checkbox"
                            checked={item.question_ids.includes(question.id)}
                            onChange={() =>
                              setPaperClaims((items) =>
                                items.map((entry) =>
                                  entry.id === item.id ? { ...entry, question_ids: toggleId(entry.question_ids, question.id) } : entry,
                                ),
                              )
                            }
                          />
                          <span>{question.text || "Question"}</span>
                        </label>
                      ))}
                    </div>
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
                                  entry.id === item.id ? { ...entry, reference_ids: toggleId(entry.reference_ids, reference.id) } : entry,
                                ),
                              )
                            }
                          />
                          <span>{reference.title || "Reference"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Logs</strong>
                    <div className="paper-link-group">
                      {collectionNotes.map((note) => (
                        <label key={`${item.id}-note-${note.id}`} className="paper-link-chip">
                          <input
                            type="checkbox"
                            checked={item.note_ids.includes(note.id)}
                            onChange={() =>
                              setPaperClaims((items) =>
                                items.map((entry) =>
                                  entry.id === item.id ? { ...entry, note_ids: toggleId(entry.note_ids, note.id) } : entry,
                                ),
                              )
                            }
                          />
                          <span>{noteLabel(note)}</span>
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
                                  entry.id === item.id ? { ...entry, result_ids: toggleId(entry.result_ids, result.id) } : entry,
                                ),
                              )
                            }
                          />
                          <span>{resultLabel(result)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </details>
              </article>
            ))}
          </div>
        </section>

        <section className="paper-manuscript-section">
          <div className="meetings-detail-head">
            <div className="meetings-detail-info">
              <strong>Sections</strong>
            </div>
            <button type="button" className="meetings-new-btn" onClick={() => setPaperSections((items) => [...items, newPaperSection()])}>
              <FontAwesomeIcon icon={faPlus} /> Add Section
            </button>
          </div>
          <div className="paper-stack paper-stack-plain">
            {paperSections.length === 0 ? <p className="muted-small">No sections.</p> : null}
            {paperSections.map((item, index) => (
              <article key={item.id} className={`paper-note-block${item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? " paper-note-block-alert" : ""}`}>
                <div className="paper-note-head">
                  <div className="paper-note-head-main">
                    <strong>Section {index + 1}</strong>
                    <div className="paper-evidence-strip">
                      <span className="chip small">{item.status.replace(/_/g, " ")}</span>
                      {item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0 ? (
                        <span className="chip small paper-health-alert">Weak section</span>
                      ) : null}
                    </div>
                  </div>
                  <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => setPaperSections((items) => items.filter((entry) => entry.id !== item.id))}>
                    <FontAwesomeIcon icon={faXmark} />
                  </button>
                </div>
                <div className="paper-section-inline-row">
                  <label className="paper-field-block">
                    <span>Title</span>
                    <input
                      value={item.title}
                      onChange={(event) =>
                        setPaperSections((items) => items.map((entry) => (entry.id === item.id ? { ...entry, title: event.target.value } : entry)))
                      }
                    />
                  </label>
                  <label className="paper-field-block">
                    <span>Status</span>
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
                <div className="paper-evidence-summary">
                  <div className="paper-evidence-line">
                    <strong>Questions</strong>
                    {renderInlineEntities(
                      item.question_ids
                        .map((questionId) => questionById.get(questionId))
                        .filter((question): question is ResearchPaperQuestion => Boolean(question))
                        .map((question) => ({
                          id: question.id,
                          label: question.text || "Question",
                        })),
                      "No questions linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>Claims</strong>
                    {renderInlineEntities(
                      item.claim_ids
                        .map((claimId) => claimById.get(claimId))
                        .filter((claim): claim is ResearchPaperClaim => Boolean(claim))
                        .map((claim) => ({
                          id: claim.id,
                          label: claim.text || "Claim",
                        })),
                      "No claims linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>References</strong>
                    {renderInlineEntities(
                      item.reference_ids
                        .map((referenceId) => referenceById.get(referenceId))
                        .filter((reference): reference is ResearchReference => Boolean(reference))
                        .map((reference) => ({
                          id: reference.id,
                          label: reference.title || "Reference",
                          onClick: () => {
                            setTab("references");
                            openEditReferenceModal(reference);
                          },
                        })),
                      "No references linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>Logs</strong>
                    {renderInlineEntities(
                      item.note_ids
                        .map((noteId) => noteById.get(noteId))
                        .filter((note): note is ResearchNote => Boolean(note))
                        .map((note) => ({
                          id: note.id,
                          label: noteLabel(note),
                          onClick: () => {
                            setTab("notes");
                            setActiveInboxNoteId(note.id);
                          },
                        })),
                      "No logs linked",
                    )}
                  </div>
                  <div className="paper-evidence-line">
                    <strong>Results</strong>
                    {renderInlineEntities(
                      item.result_ids
                        .map((resultId) => resultById.get(resultId))
                        .filter((result): result is ResearchStudyResult => Boolean(result))
                        .map((result) => ({
                          id: result.id,
                          label: resultLabel(result),
                          onClick: () => setTab("iterations"),
                        })),
                      "No results linked",
                    )}
                  </div>
                </div>
                <details className="paper-link-details">
                  <summary className="paper-link-toggle">Edit links</summary>
                  <div className="paper-link-block">
                    <strong>Questions</strong>
                    <div className="paper-link-group">
                      {paperQuestions.map((question) => (
                        <label key={`${item.id}-q-${question.id}`} className="paper-link-chip">
                          <input type="checkbox" checked={item.question_ids.includes(question.id)} onChange={() => setPaperSections((items) => items.map((entry) => entry.id === item.id ? { ...entry, question_ids: toggleId(entry.question_ids, question.id) } : entry))} />
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
                          <input type="checkbox" checked={item.claim_ids.includes(claim.id)} onChange={() => setPaperSections((items) => items.map((entry) => entry.id === item.id ? { ...entry, claim_ids: toggleId(entry.claim_ids, claim.id) } : entry))} />
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
                          <input type="checkbox" checked={item.reference_ids.includes(reference.id)} onChange={() => setPaperSections((items) => items.map((entry) => entry.id === item.id ? { ...entry, reference_ids: toggleId(entry.reference_ids, reference.id) } : entry))} />
                          <span>{reference.title || "Reference"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Logs</strong>
                    <div className="paper-link-group">
                      {collectionNotes.map((note) => (
                        <label key={`${item.id}-section-note-${note.id}`} className="paper-link-chip">
                          <input type="checkbox" checked={item.note_ids.includes(note.id)} onChange={() => setPaperSections((items) => items.map((entry) => entry.id === item.id ? { ...entry, note_ids: toggleId(entry.note_ids, note.id) } : entry))} />
                          <span>{noteLabel(note)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="paper-link-block">
                    <strong>Results</strong>
                    <div className="paper-link-group">
                      {collectionResults.map((result) => (
                        <label key={`${item.id}-section-result-${result.id}`} className="paper-link-chip">
                          <input type="checkbox" checked={item.result_ids.includes(result.id)} onChange={() => setPaperSections((items) => items.map((entry) => entry.id === item.id ? { ...entry, result_ids: toggleId(entry.result_ids, result.id) } : entry))} />
                          <span>{resultLabel(result)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </details>
              </article>
            ))}
          </div>
        </section>
      </div>
    );
  }

  function renderChatTab() {
    if (!collectionDetail || !selectedCollectionId) {
      return null;
    }
    return (
      <div className="study-chat-tab-shell">
        <StudyCollabChat
          key={`study-chat:${selectedProjectId}:${selectedCollectionId}:${activeResearchSpaceId}`}
          projectId={selectedProjectId}
          collectionId={selectedCollectionId}
          researchSpaceId={activeResearchSpaceId || null}
          currentUser={currentUser}
          members={collectionDetail.members || []}
          threadTitle={collectionDetail.title}
          hideParticipants
          onOnlineUsersChange={setStudyOnlineUserIds}
        />
      </div>
    );
  }

  function renderFilesTab() {
    if (!selectedCollectionId) {
      return <p className="empty-message">Select a study to manage its files.</p>;
    }

    const fileSearchItems = studyFiles.map((file) => ({
      id: file.id,
      label: file.original_filename,
      icon: faFile,
      section: file.mime_type || undefined,
    }));

    return (
      <div className="study-files-shell">
        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <span>{studyFiles.length} file{studyFiles.length === 1 ? "" : "s"}</span>
          </div>
          <div className="workspace-browser-summary-actions">
            <div className="kanban-view-toggle">
              <button type="button" className={`ghost icon-only kanban-view-btn${filesView === "grid" ? " active" : ""}`} onClick={() => setFilesView("grid")} title="Grid view">
                <FontAwesomeIcon icon={faGrip} />
              </button>
              <button type="button" className={`ghost icon-only kanban-view-btn${filesView === "list" ? " active" : ""}`} onClick={() => setFilesView("list")} title="List view">
                <FontAwesomeIcon icon={faList} />
              </button>
            </div>
            <button type="button" className="ghost icon-text-button small" onClick={() => setFileSearchOpen(true)} title="Search files (Ctrl+F)">
              <FontAwesomeIcon icon={faSearch} /> Search
            </button>
            <input
              ref={quickLogFileInputRef}
              type="file"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleUploadStudyFile(file);
              }}
            />
            <button
              type="button"
              className="meetings-new-btn"
              disabled={uploadingStudyFile}
              onClick={() => quickLogFileInputRef.current?.click()}
            >
              <FontAwesomeIcon icon={faFileArrowUp} /> {uploadingStudyFile ? "Uploading..." : "Upload"}
            </button>
          </div>
        </div>

        {studyFiles.length === 0 ? (
          <p className="empty-message">No files in this study.</p>
        ) : filesView === "grid" ? (
          <div className="files-grid">
            {studyFiles.map((file) => (
              <div key={file.id} className="file-card" role="button" tabIndex={0} onClick={() => void handleOpenStudyFile(file)}>
                <div className="file-card-head">
                  <FontAwesomeIcon icon={faFile} className="file-card-icon" />
                  <span className="file-card-size">{formatFileSize(file.file_size_bytes)}</span>
                </div>
                <strong className="file-card-name">{file.original_filename}</strong>
                <div className="file-card-meta">
                  <span>{file.uploaded_by_name || "Unknown"}</span>
                  <span>{formatRelativeTime(file.created_at)}</span>
                </div>
                <div className="file-card-actions">
                  <button type="button" className="ghost" tabIndex={-1} onClick={(e) => { e.stopPropagation(); void handleOpenStudyFile(file); }}>Open</button>
                  {!isStudent ? <button type="button" className="ghost" tabIndex={-1} onClick={(e) => { e.stopPropagation(); void handleDeleteStudyFile(file.id); }}>Delete</button> : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="files-list">
            {studyFiles.map((file) => (
              <div key={file.id} className="file-list-row" role="button" tabIndex={0} onClick={() => void handleOpenStudyFile(file)}>
                <FontAwesomeIcon icon={faFile} className="file-list-icon" />
                <strong className="file-list-name">{file.original_filename}</strong>
                <span className="file-list-meta">{formatFileSize(file.file_size_bytes)}</span>
                <span className="file-list-meta">{file.uploaded_by_name || "Unknown"}</span>
                <span className="file-list-meta">{formatRelativeTime(file.created_at)}</span>
                <div className="file-list-actions">
                  <button type="button" className="ghost" tabIndex={-1} onClick={(e) => { e.stopPropagation(); void handleOpenStudyFile(file); }}>Open</button>
                  {!isStudent ? <button type="button" className="ghost" tabIndex={-1} onClick={(e) => { e.stopPropagation(); void handleDeleteStudyFile(file.id); }}>Delete</button> : null}
                </div>
              </div>
            ))}
          </div>
        )}

        {fileSearchOpen ? (
          <CommandPalette
            items={fileSearchItems}
            onSelect={(id) => {
              setFileSearchOpen(false);
              const file = studyFiles.find((f) => f.id === id);
              if (file) void handleOpenStudyFile(file);
            }}
            onClose={() => setFileSearchOpen(false)}
            aggressiveKeyboardCapture
          />
        ) : null}
      </div>
    );
  }

  function renderIterationsTab() {
    if (!collectionDetail || !selectedCollectionId) {
      return <p className="empty-message">Select a study to manage its iterations.</p>;
    }

    const collectionNotes = notes.filter((item) => item.collection_id === selectedCollectionId);
    const collectionFiles = studyFiles.filter((item) => item.collection_id === selectedCollectionId);
    const fileLookup = new Map(collectionFiles.map((item) => [item.id, item]));
    const referenceLookup = new Map(references.map((item) => [item.id, item]));
    const orderedResults = sortedStudyResults();
    const iterationReferenceSuggestions = references
      .filter((item) => item.collection_id === selectedCollectionId)
      .map((item) => ({
        id: item.id,
        label: formatRefLabel(item),
        meta: item.authors.join(", "),
      }));
    const iterationFileSuggestions = collectionFiles.map((item) => ({
      id: item.id,
      label: item.original_filename,
      meta: item.mime_type || undefined,
    }));
    const iterationNoteSuggestions = collectionNotes.map((item) => ({
      id: item.id,
      label: item.title || "Untitled Log",
      meta: formatLogTimestamp(item.created_at),
    }));
    const iterationMemberSuggestions = (collectionDetail.members || []).map((member) => ({
      id: member.member_id,
      label: `@${memberMentionHandle(member.member_name)}`,
      meta: member.member_name,
    }));

    function updateIterationInline(iterationId: string, patch: Partial<ResearchStudyIteration>) {
      setStudyIterations((items) => items.map((entry) => (entry.id === iterationId ? { ...entry, ...patch } : entry)));
    }

    function iterationReviewMarkdown(iteration: ResearchStudyIteration): string {
      const sections: string[] = [];
      if (iteration.summary?.trim()) {
        sections.push(iteration.summary.trim());
      }
      const appendListSection = (title: string, items: string[]) => {
        if (!items.length) return;
        sections.push(`## ${title}\n${items.map((item) => `- ${item}`).join("\n")}`);
      };
      appendListSection("What Changed", iteration.what_changed);
      appendListSection("Improvements", iteration.improvements);
      appendListSection("Regressions", iteration.regressions);
      appendListSection("Unclear", iteration.unclear_points);
      appendListSection("Next Actions", iteration.next_actions);
      return sections.join("\n\n").trim();
    }

    function renderIterationNoteCard(note: ResearchNote) {
      return (
        <div
          key={note.id}
          className="iteration-evidence-entry"
        >
          <div className="iteration-evidence-entry-head">
            <LogAvatar
              name={note.author_name || "Unknown author"}
              avatarUrl={note.author_avatar_url}
              className="iteration-evidence-avatar"
            />
            <div className="iteration-evidence-entry-meta">
              <button type="button" className="iteration-inline-link" onClick={() => handleOpenLinkedNote(note.id)}>
                {note.title || deriveLogTitle(note.content) || "Log"}
              </button>
              <span>{formatLogTimestamp(note.created_at)}</span>
            </div>
          </div>
          <div className="iteration-evidence-entry-body chat-markdown">
            {renderMarkdown(note.content || deriveLogTitle(note.content) || "No content", {
              onReferenceClick: (label) => handleOpenReferenceByLabel(label, note.linked_reference_ids),
              onTagClick: handleFilterByTag,
              onFileClick: (label) => handleOpenLinkedFileByLabel(label, note.linked_file_ids),
              onNoteClick: (label) => handleOpenLinkedNoteByLabel(label, note.linked_note_ids),
            })}
          </div>
          <div className="iteration-evidence-entry-foot">
            {note.replies.length ? <span>{note.replies.length} replies</span> : null}
            {note.action_items.length ? <span>{note.action_items.length} actions</span> : null}
            {note.linked_file_ids.length ? <span>{note.linked_file_ids.length} files</span> : null}
          </div>
        </div>
      );
    }

    function renderIterationFileCard(file: ResearchStudyFile) {
      return (
        <div
          key={file.id}
          className="iteration-evidence-entry iteration-evidence-entry-compact"
        >
          <div className="iteration-evidence-entry-head">
            <span className="meetings-source-icon">
              <FontAwesomeIcon icon={faFileArrowUp} />
            </span>
            <div className="iteration-evidence-entry-meta">
              <button type="button" className="iteration-inline-link" onClick={() => void handleOpenStudyFile(file)}>
                {file.original_filename}
              </button>
              <span>{file.mime_type || "file"} · {formatFileSize(file.file_size_bytes || 0)}</span>
            </div>
          </div>
        </div>
      );
    }

    function renderIterationReferenceCard(reference: ResearchReference) {
      return (
        <div
          key={reference.id}
          className="iteration-evidence-entry"
        >
          <div className="iteration-evidence-entry-head">
            <span className="meetings-source-icon">
              <FontAwesomeIcon icon={faBookOpen} />
            </span>
            <div className="iteration-evidence-entry-meta">
              <button type="button" className="iteration-inline-link" onClick={() => handleOpenLinkedReference(reference.id)}>
                {reference.title}
              </button>
              <span>{formatRefLabel(reference)}</span>
            </div>
          </div>
          <div className="iteration-evidence-entry-body">
            {reference.abstract
              ? `${reference.abstract.slice(0, 180)}${reference.abstract.length > 180 ? "..." : ""}`
              : reference.authors.join(", ")}
          </div>
        </div>
      );
    }

    return (
      <div className="paper-workspace">
        {studyIterations.length > 0 ? (
          <div className="iteration-timeline">
            {studyIterations.map((iter, idx) => {
              const hasResult = iterationResults(iter.id).length > 0;
              return (
                <button
                  key={iter.id}
                  type="button"
                  className={`iteration-step${expandedIterationId === iter.id ? " active" : ""}${iter.reviewed_at ? " reviewed" : ""}${hasResult ? " has-result" : ""}`}
                  onClick={() => setExpandedIterationId((c) => (c === iter.id ? null : iter.id))}
                >
                  <span className="iteration-step-num">{idx + 1}</span>
                  <span className="iteration-step-label">{iter.title || `Iteration ${idx + 1}`}</span>
                  <span className="iteration-step-meta">
                    {iter.improvements.length > 0 ? <span className="iteration-step-up">+{iter.improvements.length}</span> : null}
                    {iter.regressions.length > 0 ? <span className="iteration-step-down">-{iter.regressions.length}</span> : null}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}

        {orderedResults.length > 0 ? (
          <div className="meetings-detail-section">
            <div className="meetings-detail-head">
              <div className="meetings-detail-info">
                <strong>Results</strong>
              </div>
              <div className="research-header-actions">
                {!isStudent ? (
                  <button
                    type="button"
                    className="ghost icon-text-button small"
                    disabled={comparingResults || orderedResults.length < 2}
                    onClick={() => void handleCompareResults()}
                  >
                    <FontAwesomeIcon icon={faMagicWandSparkles} spin={comparingResults} /> {comparingResults ? "Comparing..." : "Compare Results"}
                  </button>
                ) : null}
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
                      {result.file_ids.length ? <span className="chip small">{result.file_ids.length} files</span> : null}
                      {result.improvements.length ? <span className="chip small">{result.improvements.length} improvements</span> : null}
                      {result.regressions.length ? <span className="chip small">{result.regressions.length} regressions</span> : null}
                    </div>
                    <p>{result.summary || "No summary."}</p>
                    {result.file_ids.length > 0 ? (
                      <div className="research-chip-group">
                        {result.file_ids.map((fileId) => {
                          const file = fileLookup.get(fileId);
                          if (!file) return null;
                          return <span key={`${result.id}-file-${fileId}`} className="chip small">{file.original_filename}</span>;
                        })}
                      </div>
                    ) : null}
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
          <div key={iteration.id} className={`meetings-detail-section iteration-workspace-card${expandedIterationId === iteration.id ? " is-expanded" : ""}`}>
            <div
              className="meetings-detail-head iteration-workspace-head"
              onClick={(event) => {
                const target = event.target as HTMLElement | null;
                if (!target) return;
                if (target.closest("button, input, textarea, select, label, a")) return;
                setExpandedIterationId((current) => (current === iteration.id ? null : iteration.id));
              }}
            >
              <div className="meetings-detail-info iteration-head-info">
                <div className="iteration-head-title-row">
                  {editingIterationTitleId === iteration.id ? (
                    <input
                      className="iteration-inline-title-input"
                      value={inlineIterationTitle}
                      autoFocus
                      onChange={(event) => setInlineIterationTitle(event.target.value)}
                      onBlur={() => {
                        updateIterationInline(iteration.id, { title: inlineIterationTitle.trim() });
                        setEditingIterationTitleId(null);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          updateIterationInline(iteration.id, { title: inlineIterationTitle.trim() });
                          setEditingIterationTitleId(null);
                        } else if (event.key === "Escape") {
                          event.preventDefault();
                          setEditingIterationTitleId(null);
                          setInlineIterationTitle(iteration.title || "");
                        }
                      }}
                    />
                  ) : (
                    <strong
                      className="iteration-inline-title"
                      onClick={() => {
                        setEditingIterationTitleId(iteration.id);
                        setInlineIterationTitle(iteration.title || "");
                      }}
                    >
                      {iteration.title || `Iteration ${index + 1}`}
                    </strong>
                  )}
                  <div className="iteration-head-meta">
                    {iteration.reviewed_at ? <span className="chip small">Reviewed</span> : <span className="chip small paper-health-alert">Review pending</span>}
                    {iteration.file_ids.length ? <span className="chip small">{iteration.file_ids.length} files</span> : null}
                    {iteration.improvements.length ? <span className="chip small">{iteration.improvements.length} improvements</span> : null}
                    {iteration.regressions.length ? <span className="chip small">{iteration.regressions.length} regressions</span> : null}
                    {iteration.next_actions.length ? <span className="chip small">{iteration.next_actions.length} next actions</span> : null}
                  </div>
                </div>
              </div>
              <div className="research-header-actions">
                {editingIterationStartId === iteration.id ? (
                  <input
                    type="date"
                    className="iteration-inline-date-input"
                    value={inlineIterationStart}
                    autoFocus
                    onChange={(event) => setInlineIterationStart(event.target.value)}
                    onBlur={() => {
                      updateIterationInline(iteration.id, { start_date: inlineIterationStart || null });
                      setEditingIterationStartId(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        updateIterationInline(iteration.id, { start_date: inlineIterationStart || null });
                        setEditingIterationStartId(null);
                      } else if (event.key === "Escape") {
                        event.preventDefault();
                        setEditingIterationStartId(null);
                        setInlineIterationStart(iteration.start_date || "");
                      }
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    className="chip small iteration-inline-chip"
                    onClick={() => {
                      setEditingIterationStartId(iteration.id);
                      setInlineIterationStart(iteration.start_date || "");
                    }}
                  >
                    {iteration.start_date || "Start"}
                  </button>
                )}
                <span className="iteration-inline-date-sep">-</span>
                {editingIterationEndId === iteration.id ? (
                  <input
                    type="date"
                    className="iteration-inline-date-input"
                    value={inlineIterationEnd}
                    autoFocus
                    onChange={(event) => setInlineIterationEnd(event.target.value)}
                    onBlur={() => {
                      updateIterationInline(iteration.id, { end_date: inlineIterationEnd || null });
                      setEditingIterationEndId(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        updateIterationInline(iteration.id, { end_date: inlineIterationEnd || null });
                        setEditingIterationEndId(null);
                      } else if (event.key === "Escape") {
                        event.preventDefault();
                        setEditingIterationEndId(null);
                        setInlineIterationEnd(iteration.end_date || "");
                      }
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    className="chip small iteration-inline-chip"
                    onClick={() => {
                      setEditingIterationEndId(iteration.id);
                      setInlineIterationEnd(iteration.end_date || "");
                    }}
                  >
                    {iteration.end_date || "End"}
                  </button>
                )}
                <span className="chip small">{iteration.note_ids.length} logs</span>
                <span className="chip small">{iterationResults(iteration.id).length} results</span>
                {!isStudent ? (
                  <button
                    type="button"
                    className="ghost icon-text-button small"
                    disabled={reviewingIterationId === iteration.id}
                    onClick={() => void handleReviewIteration(iteration.id)}
                  >
                    <FontAwesomeIcon icon={faMagicWandSparkles} spin={reviewingIterationId === iteration.id} /> {reviewingIterationId === iteration.id ? "Reviewing..." : "Review"}
                  </button>
                ) : null}
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
                  className="ghost docs-action-btn"
                  title="Remove"
                  onClick={() => setStudyIterations((items) => items.filter((entry) => entry.id !== iteration.id))}
                >
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>
            <div className="paper-stack">
              <div className="iteration-summary-block chat-markdown">
                {iteration.summary
                  ? renderMarkdown(iteration.summary, {
                      onReferenceClick: (label) => handleOpenReferenceByLabel(label, []),
                      onTagClick: handleFilterByTag,
                      onFileClick: (label) => handleOpenLinkedFileByLabel(label, iteration.file_ids),
                      onNoteClick: (label) => handleOpenLinkedNoteByLabel(label),
                    })
                  : "No review yet."}
              </div>
            </div>
            {expandedIterationId === iteration.id ? (() => {
              const iterationNotes = collectionNotes.filter((note) => iteration.note_ids.includes(note.id));
              const iterationFiles = iteration.file_ids
                .map((fileId) => fileLookup.get(fileId))
                .filter((item): item is ResearchStudyFile => Boolean(item));
              const iterationReferences = iteration.reference_ids
                .map((referenceId) => referenceLookup.get(referenceId))
                .filter((item): item is ResearchReference => Boolean(item));
              const iterationActions = iterationNotes.flatMap((note) =>
                note.action_items.map((action) => ({ action, note })),
              );
              const relatedResults = iterationResults(iteration.id);

              return (
                <div className="paper-stack iteration-workspace-body">
                  <div className="iteration-evidence-grid">
                    <div className="paper-link-block iteration-section-card">
                      <strong>Logs</strong>
                      <div className="iteration-evidence-list">
                        {iterationNotes.length === 0 ? <span className="muted-small">None</span> : null}
                        {iterationNotes.map((note) => renderIterationNoteCard(note))}
                      </div>
                    </div>
                    <div className="paper-link-block iteration-section-card">
                      <strong>Files</strong>
                      <div className="iteration-evidence-list">
                        {iterationFiles.length === 0 ? <span className="muted-small">None</span> : null}
                        {iterationFiles.map((file) => renderIterationFileCard(file))}
                      </div>
                    </div>
                    <div className="paper-link-block iteration-section-card">
                      <strong>References</strong>
                      <div className="iteration-evidence-list">
                        {iterationReferences.length === 0 ? <span className="muted-small">None</span> : null}
                        {iterationReferences.map((reference) => renderIterationReferenceCard(reference))}
                      </div>
                    </div>
                    <div className="paper-link-block iteration-section-card">
                      <strong>Actions</strong>
                      <div className="iteration-action-list">
                        {iterationActions.length === 0 ? <span className="muted-small">None</span> : null}
                        {iterationActions.map(({ action, note }) => (
                          <div
                            key={`${iteration.id}-action-${action.id}`}
                            className="iteration-action-row"
                          >
                            <span className={`research-note-action-checkbox research-note-action-toggle${action.status === "done" ? " done" : ""}`}>
                              {action.status === "done" ? "[x]" : action.status === "doing" ? "[-]" : "[ ]"}
                            </span>
                            <span className="iteration-action-row-main">
                              <strong>{action.text}</strong>
                              <span>
                                <button type="button" className="iteration-inline-link" onClick={() => handleOpenLinkedNote(note.id)}>
                                  {note.title || deriveLogTitle(note.content) || "Log"}
                                </button>
                                {action.assignee_name ? ` · ${action.assignee_name}` : ""}
                                {action.due_date ? ` · ${action.due_date}` : ""}
                              </span>
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {iteration.reviewed_at && iterationReviewMarkdown(iteration) ? (
                    <div className="paper-link-block iteration-section-card">
                      <strong>Review</strong>
                      <div className="iteration-review-note chat-markdown">
                        {renderMarkdown(iterationReviewMarkdown(iteration), {
                          onReferenceClick: (label) => handleOpenReferenceByLabel(label, iteration.reference_ids),
                          onTagClick: handleFilterByTag,
                          onFileClick: (label) => handleOpenLinkedFileByLabel(label, iteration.file_ids),
                          onNoteClick: (label) => handleOpenLinkedNoteByLabel(label, iteration.note_ids),
                        })}
                      </div>
                    </div>
                  ) : null}

                  <div className="paper-link-block iteration-section-card">
                    <strong>Comments</strong>
                    <div className="iteration-comments-editor-shell">
                      <StudyLogRichEditor
                        key={`iteration-comments:${iteration.id}`}
                        value={iteration.user_comments || ""}
                        placeholder="Write"
                        onChange={(value) =>
                          setStudyIterations((items) =>
                            items.map((entry) => (entry.id === iteration.id ? { ...entry, user_comments: value || null } : entry))
                          )
                        }
                        referenceSuggestions={iterationReferenceSuggestions}
                        fileSuggestions={iterationFileSuggestions}
                        noteSuggestions={iterationNoteSuggestions.filter((item) => !iteration.note_ids.includes(item.id))}
                        memberSuggestions={iterationMemberSuggestions}
                        tagSuggestions={noteTagOptions}
                        projectId={selectedProjectId}
                        collectionId={selectedCollectionId}
                        spaceId={activeResearchSpaceId || undefined}
                      />
                    </div>
                  </div>

                  {relatedResults.length > 0 ? (
                    <div className="paper-link-block iteration-section-card">
                      <strong>Results</strong>
                      <div className="iteration-result-list">
                        {relatedResults.map((result) => {
                          const delta = resultDeltaLabel(result, previousStudyResult(result.id));
                          return (
                            <div key={result.id} className="paper-item-card iteration-result-card">
                              <div className="paper-item-head">
                                <strong>{result.title}</strong>
                                <span className="chip small">{result.updated_at ? formatRelativeTime(result.updated_at) : "Result"}</span>
                              </div>
                              <div className="paper-evidence-strip">
                                <span className="chip small">{result.note_ids.length} logs</span>
                                <span className="chip small">{result.reference_ids.length} references</span>
                                {result.file_ids.length ? <span className="chip small">{result.file_ids.length} files</span> : null}
                              </div>
                              <div className="iteration-summary-block chat-markdown">
                                {result.summary
                                  ? renderMarkdown(result.summary, {
                                      onReferenceClick: (label) => handleOpenReferenceByLabel(label, []),
                                      onTagClick: handleFilterByTag,
                                      onFileClick: (label) => handleOpenLinkedFileByLabel(label, result.file_ids),
                                      onNoteClick: (label) => handleOpenLinkedNoteByLabel(label),
                                    })
                                  : "No summary."}
                              </div>
                              {delta ? <span className="muted-small">{delta}</span> : null}
                            </div>
                          );
                        })}
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
              );
            })() : null}
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
    const unprocessedInboxCount = collectionNotes.filter(
      (note) =>
        !paperQuestions.some((item) => item.note_ids.includes(note.id)) &&
        !paperClaims.some((item) => item.note_ids.includes(note.id)) &&
        !paperSections.some((item) => item.note_ids.includes(note.id))
    ).length;
    const unsupportedClaims = paperClaims.filter((item) => item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0).length;
    const weakSections = paperSections.filter((item) => item.claim_ids.length + item.reference_ids.length + item.note_ids.length + item.result_ids.length === 0).length;

    const attentionItems = [
      !paperSubmissionDeadline ? { text: "Set the paper submission deadline", level: "alert" as const, tab: "paper" as Tab } : null,
      unprocessedInboxCount > 0 ? { text: `${unprocessedInboxCount} inbox item${unprocessedInboxCount !== 1 ? "s" : ""} to process`, level: "warn" as const, tab: "notes" as Tab } : null,
      studyResults.length === 0 ? { text: "No results yet — create one from an iteration review", level: "info" as const, tab: "iterations" as Tab } : null,
      unsupportedClaims > 0 ? { text: `${unsupportedClaims} claim${unsupportedClaims !== 1 ? "s" : ""} need${unsupportedClaims === 1 ? "s" : ""} evidence`, level: "alert" as const, tab: "paper" as Tab } : null,
      weakSections > 0 ? { text: `${weakSections} section${weakSections !== 1 ? "s" : ""} need${weakSections === 1 ? "s" : ""} more support`, level: "alert" as const, tab: "paper" as Tab } : null,
      references.length === 0 ? { text: "Import your first references from Bibliography", level: "info" as const, tab: "references" as Tab } : null,
    ].filter(Boolean) as { text: string; level: "alert" | "warn" | "info"; tab: Tab }[];

    // Unified recent activity feed
    const recentActivity: { id: string; kind: "result" | "reference" | "log"; title: string; meta: string; date: string; tab: Tab }[] = [
      ...sortedStudyResults().slice(0, 3).map((r) => ({ id: r.id, kind: "result" as const, title: r.title, meta: r.summary || "No summary", date: r.updated_at || r.created_at || "", tab: "iterations" as Tab })),
      ...[...references].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3).map((r) => ({ id: r.id, kind: "reference" as const, title: r.title, meta: r.authors.join(", ") || "—", date: r.created_at, tab: "references" as Tab })),
      ...[...collectionNotes].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3).map((n) => ({ id: n.id, kind: "log" as const, title: n.title, meta: n.author_name || "—", date: n.created_at, tab: "notes" as Tab })),
    ].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 8);

    // Context links summary
    const linkChips: { label: string; code: string }[] = [
      ...collectionDetail.wp_ids.map((id) => { const item = wps.find((e) => e.id === id); return item ? { label: "WP", code: item.code } : null; }).filter(Boolean) as { label: string; code: string }[],
      ...collectionDetail.task_ids.map((id) => { const item = tasks.find((e) => e.id === id); return item ? { label: "Task", code: item.code } : null; }).filter(Boolean) as { label: string; code: string }[],
      ...collectionDetail.deliverable_ids.map((id) => { const item = deliverables.find((e) => e.id === id); return item ? { label: "Del", code: item.code } : null; }).filter(Boolean) as { label: string; code: string }[],
    ];
    const hasLinks = linkChips.length > 0 || collectionDetail.meetings.length > 0;

    return (
      <div className="ov2">
        {/* ── Focus ── */}
        {editingStudyFocus ? (
          <input
            className="study-overview-description-input"
            value={inlineStudyFocus}
            autoFocus
            placeholder="Add a focus / description…"
            onChange={(event) => setInlineStudyFocus(event.target.value)}
            onBlur={() => {
              setInlineStudyFocus(collectionDetail.description || collectionDetail.hypothesis || "");
              setEditingStudyFocus(false);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void handleInlineStudyHeaderSave("focus");
              } else if (event.key === "Escape") {
                event.preventDefault();
                setInlineStudyFocus(collectionDetail.description || collectionDetail.hypothesis || "");
                setEditingStudyFocus(false);
              }
            }}
          />
        ) : (
          <p
            className={`study-overview-description${inlineStudyFocus.trim() ? "" : " is-empty"}`}
            onClick={() => setEditingStudyFocus(true)}
            title="Click to edit"
          >
            {inlineStudyFocus.trim() || "Click to add a focus / description…"}
          </p>
        )}

        {/* ── Summary line ── */}
        <div className="ov2-summary">
          <button type="button" className="ov2-summary-item" onClick={() => setTab("references")}>{references.length} refs</button>
          <span className="ov2-dot" />
          <button type="button" className="ov2-summary-item" onClick={() => setTab("notes")}>{collectionNotes.length} logs</button>
          <span className="ov2-dot" />
          <button type="button" className="ov2-summary-item" onClick={() => setTab("iterations")}>{studyResults.length} results</button>
          <span className="ov2-dot" />
          <button type="button" className="ov2-summary-item" onClick={() => setTab("paper")}>{paperClaims.length} claims</button>
          <span className="ov2-dot" />
          <button type="button" className="ov2-summary-item" onClick={() => setTab("paper")}>{paperSections.length} sections</button>
          {paperSubmissionDeadline ? (
            <>
              <span className="ov2-dot" />
              <button type="button" className="ov2-summary-item" onClick={() => setTab("paper")}>
                deadline {new Date(paperSubmissionDeadline).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
              </button>
            </>
          ) : null}
        </div>

        {/* ── AI Synthesis ── */}
        {!isStudent ? (
          <section className="ov2-section">
            <div className="ov2-section-head">
              <span className="ov2-section-label">Synthesis</span>
              {collectionDetail.ai_synthesis_at ? <span className="ov2-section-meta">{formatRelativeTime(collectionDetail.ai_synthesis_at)}</span> : null}
              <button type="button" className="ghost icon-text-button small" disabled={synthesizing} onClick={handleSynthesize}>
                <FontAwesomeIcon icon={faMagicWandSparkles} /> {synthesizing ? "Running…" : "Synthesize"}
              </button>
            </div>
            {collectionDetail.ai_synthesis && synthesis ? (
              <div className="ov2-synthesis">
                <p className="ov2-synthesis-summary">{synthesis.summary || collectionDetail.ai_synthesis}</p>
                {(synthesis.findings?.length || synthesis.knowledge_state?.length || synthesis.open_questions?.length || synthesis.decisions?.length || synthesis.tasks?.length || synthesis.evidence?.length || synthesis.discussion_points?.length) ? (
                  <>
                    {!synthesisExpanded ? (
                      <button type="button" className="ghost icon-text-button small" onClick={() => setSynthesisExpanded(true)}>
                        <FontAwesomeIcon icon={faChevronDown} /> Show details
                      </button>
                    ) : (
                      <>
                        <button type="button" className="ghost icon-text-button small" onClick={() => setSynthesisExpanded(false)}>
                          <FontAwesomeIcon icon={faChevronUp} /> Hide details
                        </button>
                        <div className="ov2-synthesis-details">
                          {synthesis.findings?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Findings</strong>
                              <ul>{synthesis.findings.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {synthesis.knowledge_state?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Knowledge State</strong>
                              <ul>{synthesis.knowledge_state.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {synthesis.open_questions?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Open Questions</strong>
                              <ul>{synthesis.open_questions.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {synthesis.decisions?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Decisions</strong>
                              <ul>{synthesis.decisions.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {synthesis.discussion_points?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Discussions</strong>
                              <ul>{synthesis.discussion_points.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {synthesis.tasks?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Tasks</strong>
                              <ul>{synthesis.tasks.map((item) => <li key={item}>{item}</li>)}</ul>
                            </div>
                          ) : null}
                          {synthesis.output_readiness ? (
                            <div className="ov2-synth-group">
                              <strong>Output Readiness — {synthesis.output_readiness.status || "Unknown"}</strong>
                              <ul>
                                {synthesis.output_readiness.missing?.map((item) => <li key={item}>Missing: {item}</li>)}
                                {synthesis.output_readiness.next_actions?.map((item) => <li key={item}>Next: {item}</li>)}
                              </ul>
                            </div>
                          ) : null}
                          {synthesis.evidence?.length ? (
                            <div className="ov2-synth-group">
                              <strong>Evidence</strong>
                              <ul>{synthesis.evidence.map((item, i) => <li key={`ev-${i}`}>{item.claim}{item.sources?.length ? ` — ${item.sources.join(", ")}` : ""}</li>)}</ul>
                            </div>
                          ) : null}
                        </div>
                      </>
                    )}
                  </>
                ) : null}
              </div>
            ) : (
              <p className="ov2-empty">No synthesis yet. Click Synthesize to generate one.</p>
            )}
          </section>
        ) : null}

        {/* ── Attention ── */}
        {attentionItems.length > 0 ? (
          <section className="ov2-section">
            <div className="ov2-section-head">
              <span className="ov2-section-label">Attention</span>
              <span className="ov2-section-meta">{attentionItems.length} item{attentionItems.length !== 1 ? "s" : ""}</span>
            </div>
            <div className="ov2-attention-list">
              {attentionItems.map((item) => (
                <button key={item.text} type="button" className={`ov2-attention-card level-${item.level}`} onClick={() => setTab(item.tab)}>
                  <span className="ov2-attention-dot" />
                  <span className="ov2-attention-text">{item.text}</span>
                  <FontAwesomeIcon icon={faChevronRight} className="ov2-attention-arrow" />
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {/* ── What's Moving ── */}
        {recentActivity.length > 0 ? (
          <section className="ov2-section">
            <div className="ov2-section-head">
              <span className="ov2-section-label">What's Moving</span>
            </div>
            <div className="ov2-activity-list">
              {recentActivity.map((item) => (
                <button key={`${item.kind}-${item.id}`} type="button" className="ov2-activity-row" onClick={() => setTab(item.tab)}>
                  <span className={`ov2-activity-kind kind-${item.kind}`}>{item.kind}</span>
                  <strong className="ov2-activity-title">{item.title}</strong>
                  <span className="ov2-activity-meta">{item.meta}</span>
                  <span className="ov2-activity-time">{formatRelativeTime(item.date)}</span>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {/* ── Team ── */}
        <section className="ov2-section">
          <div className="ov2-section-head">
            <span className="ov2-section-label">Team</span>
            <span className="ov2-section-meta">{collectionDetail.members.length}</span>
            {!isStudent ? (
              <button type="button" className="ghost icon-text-button small" onClick={() => setMemberModalOpen(true)}>
                <FontAwesomeIcon icon={faPlus} /> Manage
              </button>
            ) : null}
          </div>
          {collectionDetail.members.length > 0 ? (
            <div className="ov2-team-row">
              {collectionDetail.members.map((member: ResearchCollectionMember) => (
                <div key={member.id} className="ov2-team-member">
                  <LogAvatar name={member.member_name} avatarUrl={member.avatar_url} />
                  <div className="ov2-team-info">
                    <strong>{member.member_name}</strong>
                    <span>{member.role}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="ov2-empty">No members yet.</p>
          )}
        </section>

        {/* ── Links (collapsed) ── */}
        {hasLinks || !isStudent ? (
          <section className="ov2-section ov2-links-section">
            <button type="button" className="ov2-links-toggle" onClick={() => setOverviewLinksExpanded((v) => !v)}>
              <FontAwesomeIcon icon={faLink} />
              <span className="ov2-section-label">Links</span>
              {linkChips.length > 0 ? <span className="ov2-section-meta">{linkChips.map((c) => `${c.label} ${c.code}`).join(", ")}{collectionDetail.meetings.length > 0 ? ` · ${collectionDetail.meetings.length} meeting${collectionDetail.meetings.length !== 1 ? "s" : ""}` : ""}</span> : <span className="ov2-section-meta">None</span>}
              <FontAwesomeIcon icon={overviewLinksExpanded ? faChevronUp : faChevronDown} className="ov2-links-chevron" />
            </button>
            {overviewLinksExpanded ? (
              <div className="ov2-links-body">
                <div className="research-chip-group">
                  {linkChips.map((c, i) => (
                    <span key={`lk-${i}`} className="chip small"><span className="chip-type-label">{c.label}</span> {c.code}</span>
                  ))}
                  {collectionDetail.meetings.map((meeting) => (
                    <span key={meeting.id} className="chip small"><FontAwesomeIcon icon={faCalendarDay} /> {meeting.title}</span>
                  ))}
                </div>
                {!isStudent ? (
                  <button type="button" className="ghost icon-text-button small" onClick={openWbsModal}>
                    <FontAwesomeIcon icon={faPen} /> Edit links
                  </button>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}
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
            {availableResearchSpaces.length > 0 ? (
              <div className="full-span">
                <span className="form-label">Spaces</span>
                <div className="research-lane-pills">
                  {availableResearchSpaces.map((space) => {
                    const active = collectionSpaceIds.includes(space.id);
                    return (
                      <button
                        key={space.id}
                        type="button"
                        className={`research-lane-pill ${active ? "active" : ""}`}
                        onClick={() => setCollectionSpaceIds((current) => toggleListValue(current, space.id))}
                      >
                        {space.title}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
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
                onClick={() => void (isBatchMode && !isStudent ? handleImportBibliographyIdentifiers() : (isBibtexMode && !isStudent ? handleImportBibliographyBibtex() : handleSaveBibliography()))}
              >
                {saving ? ((isBatchMode || isBibtexMode) && !isStudent ? "Importing..." : "Saving...") : isCreate ? ((isBatchMode || isBibtexMode) && !isStudent ? "Import" : "Add") : "Save"}
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
                {!isStudent ? (
                  <button className={`delivery-tab ${bibliographyCreateTab === "batch" ? "active" : ""}`} onClick={() => setBibliographyCreateTab("batch")}>
                    Batch
                  </button>
                ) : null}
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
                      {canExtractAbstract && !isStudent ? (
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
                      {canExtractConcepts && !isStudent ? (
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
    if (typeof document === "undefined") return null;
    const linkableReferences = Array.from(
      new Map(
        [...references, ...allReferences]
          .filter((item) => !noteCollectionId || item.collection_id === noteCollectionId)
          .map((item) => [item.id, item]),
      ).values(),
    );
    const linkableReferenceMap = new Map(linkableReferences.map((item) => [item.id, item]));
    const derivedTags = deriveMarkdownTags(noteContent);
    const derivedActionItems = extractDraftActionItems(noteContent);
    const editorReferenceSuggestions = linkableReferences.map((item) => ({
      id: item.id,
      label: formatRefLabel(item),
      meta: item.authors.join(", "),
    }));
    const editorFileSuggestions = studyFiles
      .filter((item) => item.collection_id === noteCollectionId)
      .map((item) => ({
        id: item.id,
        label: item.original_filename,
        meta: item.mime_type || undefined,
      }));
    const citedPreviewFiles = extractMarkdownFileLabels(noteContent)
      .map((label) => resolveLinkedFileByLabel(label, noteFileIds))
      .filter((item): item is ResearchStudyFile => Boolean(item))
      .filter((item, index, arr) => arr.findIndex((candidate) => candidate.id === item.id) === index);
    const resolvedLinkedNoteIds = collectResolvedLinkedNoteIds(noteContent, editingNoteId);
    const linkedNotes = resolvedLinkedNoteIds
      .map((noteId) => resolveLinkedNoteById(noteId))
      .filter((item): item is ResearchNote => Boolean(item));
    const backlinkNotes = noteModalMode === "edit" && editingNoteId
      ? notes
          .filter((item) => item.id === editingNoteId)
          .flatMap((item) => item.backlink_note_ids)
          .map((noteId) => resolveLinkedNoteById(noteId))
          .filter((item): item is ResearchNote => Boolean(item))
      : [];
    const editorNoteSuggestions = notes
      .filter((item) => item.collection_id === noteCollectionId && item.id !== editingNoteId)
      .map((item) => ({
        id: item.id,
        label: item.title || "Untitled Log",
        meta: formatLogTimestamp(item.created_at),
      }));
    const editorMemberSuggestions = (collectionDetail?.members || []).map((member) => ({
      id: member.member_id,
      label: `@${memberMentionHandle(member.member_name)}`,
      meta: member.member_name,
    }));
    const filteredNoteTemplates = noteTemplates.filter((template) => {
      const query = noteTemplateSearch.trim().toLowerCase();
      if (!query) return true;
      return [template.name, template.title || "", template.content, template.created_by_name || ""]
        .some((value) => value.toLowerCase().includes(query));
    });

    return createPortal(
      <div className="modal-overlay research-editor-overlay" role="dialog" aria-modal="true" onClick={() => closeNoteModal()}>
        <div className="modal-card settings-modal-card research-editor-modal" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <h3>{noteType === "index" ? (noteModalMode === "create" ? "New Index" : "Edit Index") : (noteModalMode === "create" ? "New Log" : "Edit Log")}</h3>
            <div className="modal-head-actions">
              <button
                type="button"
                className={`ghost docs-action-btn${notePinned ? " active" : ""}`}
                title={notePinned ? "Unpin" : "Pin"}
                onClick={() => setNotePinned((current) => !current)}
              >
                <FontAwesomeIcon icon={faThumbtack} />
              </button>
              <button
                type="button"
                className={`ghost docs-action-btn${noteStarred ? " active" : ""}`}
                title={noteStarred ? "Unstar" : "Star"}
                onClick={() => setNoteStarred((current) => !current)}
              >
                <FontAwesomeIcon icon={faStar} />
              </button>
              <button type="button" className="ghost" onClick={() => setNoteTemplateLibraryOpen(true)}>
                Templates
              </button>
              <button type="button" className="ghost" disabled={!noteContent.trim()} onClick={openSaveTemplateModal}>
                Save as Template
              </button>
              <button type="button" disabled={!noteCollectionId || !noteContent.trim() || saving} onClick={handleSaveNote}>
                {saving ? "Saving..." : noteType === "index" ? (noteModalMode === "create" ? "Add Index" : "Save Index") : (noteModalMode === "create" ? "Add Log" : "Save Log")}
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={() => closeNoteModal()} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>
          <div className="research-editor-shell">
            <div className="research-editor-main">
              <div className="research-editor-meta">
                <label>
                  Title
                  <input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} autoFocus />
                </label>
              </div>
              <div className="research-editor-workbench mode-write">
                <div className="research-editor-pane research-editor-write-pane">
                  <StudyLogRichEditor
                    key={`${noteModalMode}:${editingNoteId ?? "new"}:${noteCollectionId}`}
                    value={noteContent}
                    placeholder="Write"
                    onChange={setNoteContent}
                    referenceSuggestions={editorReferenceSuggestions}
                    fileSuggestions={editorFileSuggestions}
                    noteSuggestions={editorNoteSuggestions}
                    memberSuggestions={editorMemberSuggestions}
                    linkedFiles={citedPreviewFiles}
                    projectId={selectedProjectId}
                    collectionId={noteCollectionId}
                    spaceId={activeResearchSpaceId || undefined}
                    tagSuggestions={noteTagOptions}
                    onReferenceLinked={(referenceId) => {
                      setNoteReferenceIds((current) => current.includes(referenceId) ? current : [...current, referenceId]);
                    }}
                    onFileLinked={(fileId) => {
                      setNoteFileIds((current) => current.includes(fileId) ? current : [...current, fileId]);
                    }}
                    onNoteLinked={(noteId) => {
                      setNoteLinkedNoteIds((current) => current.includes(noteId) ? current : [...current, noteId]);
                    }}
                    onPasteImage={async (file) => {
                      const created = await handleUploadStudyFile(file, { linkToNoteModal: true });
                      return created ? { id: created.id, label: created.original_filename } : null;
                    }}
                    onReady={(editor) => {
                      noteEditorRef.current = editor;
                    }}
                  />
                </div>
              </div>
            </div>
            <aside className="research-editor-sidebar">
              <label>
                Lane
                {renderLanePills(noteLane, setNoteLane)}
              </label>
              <div className="research-editor-side-block">
                <strong>Tags</strong>
                <div className="research-chip-group">
                  {derivedTags.length === 0 ? <span className="muted-small">No tags</span> : null}
                  {derivedTags.map((tag) => (
                    <button key={`note-tag-${tag}`} type="button" className="chip small" onClick={() => handleFilterByTag(tag)}>
                      #{tag}
                    </button>
                  ))}
                </div>
              </div>
              <div className="research-editor-side-block">
                <div className="research-editor-side-head">
                  <strong>Files</strong>
                  <button type="button" className="ghost icon-text-button small" disabled={uploadingStudyFile} onClick={() => noteModalFileInputRef.current?.click()}>
                    <FontAwesomeIcon icon={faFileArrowUp} /> {uploadingStudyFile ? "Uploading..." : "Attach"}
                  </button>
                </div>
                <input
                  ref={noteModalFileInputRef}
                  type="file"
                  className="bib-pdf-input"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void handleUploadStudyFile(file, { linkToNoteModal: true });
                  }}
                />
                <div className="research-chip-group">
                  {noteFileIds.length === 0 ? <span className="muted-small">No files</span> : null}
                  {noteFileIds.map((fileId) => {
                    const file = studyFiles.find((item) => item.id === fileId);
                    if (!file) return null;
                    return (
                      <button key={`note-file-${fileId}`} type="button" className="chip small" onClick={() => void handleOpenStudyFile(file)}>
                        {file.original_filename}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="research-editor-side-block">
                <strong>References</strong>
                <div className="research-chip-group">
                  {noteReferenceIds.length === 0 ? <span className="muted-small">Use % in the editor</span> : null}
                  {noteReferenceIds.map((referenceId) => {
                    const ref = linkableReferenceMap.get(referenceId) || references.find((item) => item.id === referenceId) || allReferences.find((item) => item.id === referenceId);
                    if (!ref) return null;
                    return (
                      <button key={`note-ref-${referenceId}`} type="button" className="chip small" onClick={() => handleOpenLinkedReference(referenceId)}>
                        {formatRefLabel(ref)}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="research-editor-side-block">
                <strong>Links</strong>
                <div className="research-chip-group">
                  {linkedNotes.length === 0 ? null : linkedNotes.map((linkedNote) => (
                    <button
                      key={`note-link-${linkedNote.id}`}
                      type="button"
                      className="chip small"
                      onClick={() => handleOpenLinkedNote(linkedNote.id)}
                    >
                      [[{linkedNote.title || "Untitled Log"}]]
                    </button>
                  ))}
                  {linkedNotes.length === 0 ? <span className="muted-small">No links</span> : null}
                </div>
              </div>
              {backlinkNotes.length > 0 ? (
                <div className="research-editor-side-block">
                  <strong>Backlinks</strong>
                  <div className="research-chip-group">
                    {backlinkNotes.map((backlinkNote) => (
                      <button
                        key={`note-backlink-${backlinkNote.id}`}
                        type="button"
                        className="chip small"
                        onClick={() => handleOpenLinkedNote(backlinkNote.id)}
                      >
                        [[{backlinkNote.title || "Untitled Log"}]]
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="research-editor-side-block">
                <strong>Actions</strong>
                <div className="research-note-action-list compact">
                  {derivedActionItems.length === 0 ? <span className="muted-small">No actions</span> : null}
                  {derivedActionItems.map((item, index) => (
                    <div key={`draft-action-${index}`} className={`research-note-action-item${item.isDone ? " done" : ""}`}>
                      <span className="research-note-action-checkbox">{item.isDone ? "[x]" : "[ ]"}</span>
                      <span className="research-note-action-text">{item.text}</span>
                      {item.assigneeHandle ? <span className="chip small">@{item.assigneeHandle}</span> : null}
                      {item.dueDate ? <span className="chip small">{item.dueDate}</span> : null}
                    </div>
                  ))}
                </div>
              </div>
            </aside>
          </div>
          {noteTemplateLibraryOpen ? (
            <div className="research-note-template-overlay" onClick={() => setNoteTemplateLibraryOpen(false)}>
              <div className="research-note-template-panel" onClick={(event) => event.stopPropagation()}>
                <div className="workpane-head">
                  <h3>Templates</h3>
                  <div className="workpane-actions">
                    <input
                      className="meetings-search"
                      value={noteTemplateSearch}
                      onChange={(event) => setNoteTemplateSearch(event.target.value)}
                      placeholder="Search template"
                    />
                    <button type="button" className="ghost" onClick={() => setNoteTemplateLibraryOpen(false)}>
                      Close
                    </button>
                  </div>
                </div>
                <div className="research-note-template-list">
                  {filteredNoteTemplates.map((template) => (
                    <article key={template.id} className="research-note-template-card">
                      <div className="research-note-template-card-head">
                        <strong>{template.name}</strong>
                        <div className="research-chip-group">
                          <span className="chip small">{template.is_system ? "System" : "Mine"}</span>
                          {template.lane ? <span className="chip small">{NOTE_LANE_LABELS[template.lane] || template.lane}</span> : null}
                          <span className="chip small">{template.note_type}</span>
                        </div>
                      </div>
                      {template.title ? <div className="research-note-template-title">{template.title}</div> : null}
                      <div className="research-note-template-content">{template.content || "Empty"}</div>
                      <div className="research-note-template-actions">
                        <button type="button" onClick={() => applyNoteTemplate(template)}>
                          Use
                        </button>
                        {template.can_manage ? (
                          <button
                            type="button"
                            className="ghost danger"
                            disabled={deletingNoteTemplateId === template.id}
                            onClick={() => void handleDeleteNoteTemplate(template.id)}
                          >
                            {deletingNoteTemplateId === template.id ? "Deleting..." : "Delete"}
                          </button>
                        ) : null}
                      </div>
                    </article>
                  ))}
                  {filteredNoteTemplates.length === 0 ? (
                    <div className="research-note-template-empty">No templates</div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
          {noteTemplateSaveOpen ? (
            <div className="research-note-template-overlay" onClick={() => setNoteTemplateSaveOpen(false)}>
              <div className="research-note-template-save-card" onClick={(event) => event.stopPropagation()}>
                <div className="modal-head">
                  <h3>Save Template</h3>
                  <div className="modal-head-actions">
                    <button type="button" disabled={!noteTemplateName.trim() || savingNoteTemplate} onClick={() => void handleCreateNoteTemplate()}>
                      {savingNoteTemplate ? "Saving..." : "Save"}
                    </button>
                    <button type="button" className="ghost docs-action-btn" onClick={() => setNoteTemplateSaveOpen(false)} title="Close">
                      <FontAwesomeIcon icon={faXmark} />
                    </button>
                  </div>
                </div>
                <div className="form-grid">
                  <label className="full-span">
                    Name
                    <input value={noteTemplateName} onChange={(event) => setNoteTemplateName(event.target.value)} autoFocus />
                  </label>
                  {currentUser.platform_role === "super_admin" ? (
                    <label>
                      Scope
                      <select value={noteTemplateSystem ? "system" : "personal"} onChange={(event) => setNoteTemplateSystem(event.target.value === "system")}>
                        <option value="personal">Personal</option>
                        <option value="system">System</option>
                      </select>
                    </label>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>,
      document.body,
    );
  }

  function renderMemberModal() {
    const existingMemberIds = new Set(collectionDetail?.members.map((item) => item.member_id) || []);
    const availableMembersForCollection = hasProjectContext
      ? members.filter((item) => !existingMemberIds.has(item.id))
      : discoverableUsers.filter((item) => !existingMemberIds.has(item.id));

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
                    {"full_name" in item ? item.full_name : item.display_name}
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
