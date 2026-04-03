import { useEffect, useRef, useState } from "react";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import { Extension } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import { Markdown } from "@tiptap/markdown";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import katex from "katex";
import { api } from "../lib/api";
import type { ResearchStudyFile } from "../types";
import { CommandPalette, type CommandItem } from "./CommandPalette";
import {
  faBold,
  faCode,
  faHeading,
  faItalic,
  faLink,
  faListOl,
  faListUl,
  faHashtag,
  faAt,
  faCalendarDay,
  faFileLines,
  faListCheck,
  faMinus,
  faQuoteLeft,
  faTable,
} from "@fortawesome/free-solid-svg-icons";

type ReferenceSuggestion = {
  id: string;
  label: string;
  meta?: string;
};

type FileSuggestion = {
  id: string;
  label: string;
  meta?: string;
};

type NoteSuggestion = {
  id: string;
  label: string;
  meta?: string;
};

type MemberSuggestion = {
  id: string;
  label: string;
  meta?: string;
};

type FilePreviewCacheValue =
  | { kind: "image"; objectUrl: string }
  | { kind: "csv"; rows: string[][] };

const filePreviewCache = new Map<string, FilePreviewCacheValue>();

function isImageMime(mimeType: string | null | undefined): boolean {
  return (mimeType || "").toLowerCase().startsWith("image/");
}

function isCsvMime(mimeType: string | null | undefined, filename: string): boolean {
  const mime = (mimeType || "").toLowerCase();
  return mime.includes("csv") || filename.toLowerCase().endsWith(".csv");
}

function normalizeActionDateToken(value: string): string | null {
  const raw = (value || "").trim();
  if (!raw) return null;
  try {
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
      return raw;
    }
    const match = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!match) return null;
    const day = Number(match[1]);
    const month = Number(match[2]);
    const year = Number(match[3]);
    const date = new Date(year, month - 1, day);
    if (
      date.getFullYear() !== year ||
      date.getMonth() !== month - 1 ||
      date.getDate() !== day
    ) {
      return null;
    }
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  } catch {
    return null;
  }
}

function formatEditorActionDate(value: string): string {
  const normalized = normalizeActionDateToken(value);
  if (!normalized) return value;
  const [year, month, day] = normalized.split("-");
  return `${Number(day)}/${Number(month)}/${year}`;
}

function parseMarkdownLink(raw: string): { label: string; href: string } | null {
  const match = raw.match(/^\[([^\]]+)\]\(((?:https?:\/\/|#)[^\s)]+)\)$/);
  if (!match) return null;
  return {
    label: match[1] || "",
    href: match[2] || "",
  };
}

function findMarkdownLinkAtSelection(editor: Editor): { from: number; to: number; label: string; href: string } | null {
  const { from, to, $from } = editor.state.selection;
  const parentText = $from.parent.textContent || "";
  const blockStart = $from.start();
  const localFrom = from - blockStart;
  const localTo = to - blockStart;

  for (const match of parentText.matchAll(/\[([^\]]+)\]\(((?:https?:\/\/|#)[^\s)]+)\)/g)) {
    const raw = match[0] || "";
    const label = match[1] || "";
    const href = match[2] || "";
    const start = match.index ?? 0;
    const end = start + raw.length;
    const overlaps = localFrom <= end && localTo >= start;
    const containsCursor = localFrom >= start && localFrom <= end;
    if (!overlaps && !containsCursor) continue;
    return {
      from: blockStart + start,
      to: blockStart + end,
      label,
      href,
    };
  }

  return null;
}

function findRenderedLinkAtCursor(
  editor: Editor,
): { from: number; to: number; label: string; href: string; cursorOffset: number } | null {
  const selection = editor.state.selection;
  if (!selection.empty) return null;
  const { from, $from } = selection;
  const parent = $from.parent;
  const parentStart = $from.start();
  let match: { from: number; to: number; label: string; href: string; cursorOffset: number } | null = null;

  parent.forEach((child, offset) => {
    if (match || !child.isText) return;
    const linkMark = child.marks.find((mark) => mark.type.name === "link");
    if (!linkMark) return;
    const label = child.text || "";
    const start = parentStart + offset;
    const end = start + label.length;
    if (from < start || from > end) return;
    const href = String(linkMark.attrs?.href || "").trim();
    if (!href) return;
    match = {
      from: start,
      to: end,
      label,
      href,
      cursorOffset: Math.max(0, Math.min(label.length, from - start)),
    };
  });

  return match;
}

function createFilePreviewWidget(
  file: ResearchStudyFile,
  projectId: string,
  collectionId: string,
  spaceId?: string,
): HTMLElement {
  const container = document.createElement("div");
  container.className = "study-log-editor-file-widget";
  const cacheKey = `${projectId}:${collectionId}:${spaceId || ""}:${file.id}`;

  function renderLoading() {
    container.innerHTML = `<div class="study-log-editor-file-widget-loading">${file.original_filename}</div>`;
  }

  function renderImage(objectUrl: string) {
    container.innerHTML = "";
    const img = document.createElement("img");
    img.src = objectUrl;
    img.alt = file.original_filename;
    img.className = "study-log-editor-file-widget-image";
    container.appendChild(img);
  }

  function renderCsv(rows: string[][]) {
    container.innerHTML = "";
    const scroll = document.createElement("div");
    scroll.className = "study-log-editor-file-widget-scroll";
    const table = document.createElement("table");
    table.className = "markdown-table";
    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scroll.appendChild(table);
    container.appendChild(scroll);
  }

  const cached = filePreviewCache.get(cacheKey);
  if (cached?.kind === "image") {
    renderImage(cached.objectUrl);
    return container;
  }
  if (cached?.kind === "csv") {
    renderCsv(cached.rows);
    return container;
  }

  renderLoading();
  void api.getStudyFile(projectId, collectionId, file.id, spaceId).then(async (blob) => {
    if (isImageMime(file.mime_type)) {
      const objectUrl = URL.createObjectURL(blob);
      filePreviewCache.set(cacheKey, { kind: "image", objectUrl });
      renderImage(objectUrl);
      return;
    }
    const text = await blob.text();
    const rows = text
      .trim()
      .split(/\r?\n/)
      .slice(0, 8)
      .map((line) => line.split(",").slice(0, 6).map((cell) => cell.trim()));
    filePreviewCache.set(cacheKey, { kind: "csv", rows });
    renderCsv(rows);
  }).catch(() => {
    container.innerHTML = `<div class="study-log-editor-file-widget-loading">${file.original_filename}</div>`;
  });

  return container;
}

function createTaskCheckboxWidget(state: "open" | "done" | "doing"): HTMLElement {
  const container = document.createElement("span");
  container.className = `study-log-editor-task-checkbox-widget state-${state}`;
  return container;
}

function createHorizontalRuleWidget(): HTMLElement {
  const container = document.createElement("div");
  container.className = "study-log-editor-hr-widget";
  const hr = document.createElement("hr");
  container.appendChild(hr);
  return container;
}

function createLiveMarkdownTokensExtension(options: {
  getLinkedFiles: () => ResearchStudyFile[];
  getProjectId: () => string | null | undefined;
  getCollectionId: () => string | null | undefined;
  getSpaceId: () => string | undefined;
}) {
  return Extension.create({
    name: "liveMarkdownTokens",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey("study-log-live-markdown-tokens"),
        props: {
          decorations: (state) => {
            const decorations: Decoration[] = [];
            const selectionFrom = state.selection.from;
            const selectionTo = state.selection.to;

            function overlaps(from: number, to: number) {
              return !(selectionTo <= from || selectionFrom >= to);
            }

            state.doc.descendants((node, pos, parent) => {
              if (!node.isText || !node.text) return;
              if (parent?.type.name === "codeBlock") return;
              if (node.marks.some((mark) => mark.type.name === "code")) return;
              const text = node.text;
              const base = pos;

              for (const match of text.matchAll(/(^|\n)(\[(?: |x|X|-)\])(?=\s)/g)) {
                const prefix = match[1] || "";
                const marker = match[2] || "";
                const start = base + (match.index ?? 0) + prefix.length;
                const end = start + marker.length;
                if (overlaps(start, end)) continue;
                const stateName = marker === "[x]" || marker === "[X]"
                  ? "done"
                  : marker === "[-]"
                  ? "doing"
                  : "open";
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-hidden-token" }));
                decorations.push(
                  Decoration.widget(start, () => createTaskCheckboxWidget(stateName), { side: 0 }),
                );
              }

              for (const match of text.matchAll(/(^|\n)(---|\*\*\*|___)(?=\n|$)/g)) {
                const prefix = match[1] || "";
                const marker = match[2] || "";
                const start = base + (match.index ?? 0) + prefix.length;
                const end = start + marker.length;
                if (overlaps(start, end)) continue;
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-hidden-token" }));
                decorations.push(
                  Decoration.widget(start, () => createHorizontalRuleWidget(), { side: 0 }),
                );
              }

              for (const match of text.matchAll(/(?:@|%)\[[^\]]+\]/g)) {
                const start = base + (match.index ?? 0);
                const end = start + match[0].length;
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-citation-token" }));
              }

              for (const match of text.matchAll(/\[[^\]]+\]\(((?:https?:\/\/|#)[^\s)]+)\)/g)) {
                const start = base + (match.index ?? 0);
                const end = start + match[0].length;
                if (overlaps(start, end)) continue;
                const parsed = parseMarkdownLink(match[0]);
                decorations.push(Decoration.inline(start, end, {
                  class: "study-log-editor-link-token",
                  "data-link-start": String(start),
                  "data-link-end": String(end),
                  "data-link-label": parsed?.label || "",
                  "data-link-href": parsed?.href || "",
                }));
              }

              for (const match of text.matchAll(/(^|[\s(>])@([A-Za-z0-9][A-Za-z0-9_.-]*)/g)) {
                const prefix = match[1] || "";
                const handle = match[2] || "";
                const start = base + (match.index ?? 0) + prefix.length;
                const end = start + handle.length + 1;
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-member-token" }));
              }

              for (const match of text.matchAll(/\[\[[^\]]+\]\]/g)) {
                const start = base + (match.index ?? 0);
                const end = start + match[0].length;
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-note-token" }));
              }

              for (const match of text.matchAll(/!\[[^\]]+\]/g)) {
                const start = base + (match.index ?? 0);
                const end = start + match[0].length;
                const label = match[0].slice(2, -1).trim().toLowerCase();
                const linkedFiles = options.getLinkedFiles();
                const projectId = options.getProjectId();
                const collectionId = options.getCollectionId();
                const spaceId = options.getSpaceId();
                const file = linkedFiles.find((item) => item.original_filename.trim().toLowerCase() === label);
                const canPreview = Boolean(
                  file &&
                  projectId &&
                  collectionId &&
                  (isImageMime(file.mime_type) || isCsvMime(file.mime_type, file.original_filename))
                );
                if (!canPreview || !file) {
                  decorations.push(Decoration.inline(start, end, { class: "study-log-editor-file-token" }));
                  continue;
                }
                if (overlaps(start, end)) {
                  decorations.push(Decoration.inline(start, end, { class: "study-log-editor-file-token" }));
                  continue;
                }
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-hidden-token" }));
                decorations.push(
                  Decoration.widget(
                    start,
                    () => createFilePreviewWidget(file, projectId!, collectionId!, spaceId),
                    { side: 1 },
                  ),
                );
              }

              for (const match of text.matchAll(/(^|[\s(>])#([A-Za-z0-9][A-Za-z0-9_/-]*)/g)) {
                const prefix = match[1] || "";
                const tag = match[2] || "";
                const start = base + (match.index ?? 0) + prefix.length;
                const end = start + tag.length + 1;
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-tag-token" }));
              }

              for (const match of text.matchAll(/\$([^$\n]+?)\$/g)) {
                const raw = match[0];
                const expression = match[1] || "";
                const start = base + (match.index ?? 0);
                const end = start + raw.length;
                if (overlaps(start, end)) {
                  decorations.push(Decoration.inline(start, end, { class: "study-log-editor-math-token" }));
                  continue;
                }
                const widget = document.createElement("span");
                widget.className = "study-log-editor-math-render";
                try {
                  widget.innerHTML = katex.renderToString(expression.trim(), {
                    displayMode: false,
                    throwOnError: false,
                    strict: "ignore",
                  });
                } catch {
                  widget.textContent = raw;
                }
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-hidden-token" }));
                decorations.push(Decoration.widget(start, widget, { side: 0 }));
              }

              for (const match of text.matchAll(/(?:(?:->)\s*)?(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{4})/g)) {
                const raw = match[0];
                const token = match[1] || "";
                const normalized = normalizeActionDateToken(token);
                if (!normalized) continue;
                const start = base + (match.index ?? 0) + raw.lastIndexOf(token);
                const end = start + token.length;
                decorations.push(
                  Decoration.inline(start, end, {
                    class: "study-log-editor-action-date-token",
                    "data-date-start": String(start),
                    "data-date-end": String(end),
                    "data-date-value": normalized,
                  }),
                );
              }
            });

            return DecorationSet.create(state.doc, decorations);
          },
        },
      }),
    ];
  },
  });
}

type Props = {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onReady?: (editor: Editor | null) => void;
  referenceSuggestions?: ReferenceSuggestion[];
  fileSuggestions?: FileSuggestion[];
  noteSuggestions?: NoteSuggestion[];
  memberSuggestions?: MemberSuggestion[];
  linkedFiles?: ResearchStudyFile[];
  projectId?: string | null;
  collectionId?: string | null;
  spaceId?: string;
  tagSuggestions?: string[];
  onReferenceLinked?: (referenceId: string) => void;
  onFileLinked?: (fileId: string) => void;
  onNoteLinked?: (noteId: string) => void;
  onPasteImage?: (file: File) => Promise<{ id: string; label: string } | null>;
};

type SuggestionState =
  | {
      open: false;
    }
  | {
      open: true;
      trigger: "@" | "#" | "!" | "%" | "[[";
      query: string;
      rangeFrom: number;
      rangeTo: number;
      top: number;
      left: number;
    };

type ActionDatePopoverState =
  | { open: false }
  | {
      open: true;
      from: number;
      to: number;
      value: string;
      top: number;
      left: number;
    };

type LinkPopoverState =
  | { open: false }
  | {
      open: true;
      from: number;
      to: number;
      label: string;
      href: string;
    };

export function StudyLogRichEditor({
  value,
  placeholder,
  onChange,
  onReady,
  referenceSuggestions = [],
  fileSuggestions = [],
  noteSuggestions = [],
  memberSuggestions = [],
  linkedFiles = [],
  projectId,
  collectionId,
  spaceId,
  tagSuggestions = [],
  onReferenceLinked,
  onFileLinked,
  onNoteLinked,
  onPasteImage,
}: Props) {
  const [tableMenuOpen, setTableMenuOpen] = useState(false);
  const [tableGridHover, setTableGridHover] = useState<[number, number]>([0, 0]);
  const [suggestionState, setSuggestionState] = useState<SuggestionState>({ open: false });
  const [suggestionActiveIndex, setSuggestionActiveIndex] = useState(0);
  const [actionDatePopover, setActionDatePopover] = useState<ActionDatePopoverState>({ open: false });
  const [linkPopover, setLinkPopover] = useState<LinkPopoverState>({ open: false });
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const tableMenuRef = useRef<HTMLDivElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const suggestionStateRef = useRef<SuggestionState>({ open: false });
  const linkedFilesRef = useRef<ResearchStudyFile[]>(linkedFiles);
  const projectIdRef = useRef<string | null | undefined>(projectId);
  const collectionIdRef = useRef<string | null | undefined>(collectionId);
  const spaceIdRef = useRef<string | undefined>(spaceId);

  useEffect(() => {
    linkedFilesRef.current = linkedFiles;
  }, [linkedFiles]);

  useEffect(() => {
    projectIdRef.current = projectId;
  }, [projectId]);

  useEffect(() => {
    collectionIdRef.current = collectionId;
  }, [collectionId]);

  useEffect(() => {
    spaceIdRef.current = spaceId;
  }, [spaceId]);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Link.configure({
        openOnClick: false,
        autolink: false,
        linkOnPaste: true,
      }),
      Placeholder.configure({ placeholder }),
      createLiveMarkdownTokensExtension({
        getLinkedFiles: () => linkedFilesRef.current,
        getProjectId: () => projectIdRef.current,
        getCollectionId: () => collectionIdRef.current,
        getSpaceId: () => spaceIdRef.current,
      }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      Markdown.configure({
        markedOptions: {
          gfm: true,
          breaks: true,
        },
      }),
    ],
    content: value || "",
    contentType: "markdown",
    editorProps: {
      attributes: {
        class: "study-log-editor-content",
      },
      handlePaste(view, event) {
        if (!onPasteImage) return false;
        const clipboardEvent = event as ClipboardEvent;
        const items = Array.from(clipboardEvent.clipboardData?.items || []);
        const imageItem = items.find((item) => item.type.startsWith("image/"));
        if (!imageItem) return false;
        const blob = imageItem.getAsFile();
        if (!blob) return false;
        event.preventDefault();
        const extension = blob.type.split("/")[1] || "png";
        const fileName = blob.name && blob.name.trim()
          ? blob.name
          : `clipboard-image-${Date.now()}.${extension}`;
        const file = new File([blob], fileName, {
          type: blob.type || "image/png",
          lastModified: Date.now(),
        });
        const insertFrom = view.state.selection.from;
        const insertTo = view.state.selection.to;
        void onPasteImage(file).then((created) => {
          if (!created) return;
          const tr = view.state.tr.insertText(`![${created.label}] `, insertFrom, insertTo);
          view.dispatch(tr);
          view.focus();
          onFileLinked?.(created.id);
        }).catch(() => {
          /* caller surfaces upload errors */
        });
        return true;
      },
    },
    onUpdate: ({ editor: nextEditor }) => {
      const next = nextEditor.getMarkdown();
      if (next !== value) onChange(next);
    },
  }, [placeholder]);

  useEffect(() => {
    onReady?.(editor ?? null);
    return () => onReady?.(null);
  }, [editor, onReady]);

  useEffect(() => {
    suggestionStateRef.current = suggestionState;
  }, [suggestionState]);

  useEffect(() => {
    if (!editor) return;
    const current = editor.getMarkdown();
    if (current === value) return;
    editor.commands.setContent(value || "", { contentType: "markdown" });
  }, [editor, value]);

  useEffect(() => {
    if (!editor) return;
    editor.view.dispatch(editor.state.tr.setMeta("study-log-refresh-previews", Date.now()));
  }, [editor, linkedFiles, projectId, collectionId, spaceId]);

  useEffect(() => {
    if (!commandPaletteOpen) return;
    setSuggestionState({ open: false });
    setTableMenuOpen(false);
    setActionDatePopover({ open: false });
  }, [commandPaletteOpen]);

  useEffect(() => {
    if (!tableMenuOpen) return;
    function handleClick(event: MouseEvent) {
      if (tableMenuRef.current && !tableMenuRef.current.contains(event.target as Node)) {
        setTableMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [tableMenuOpen]);

  const filteredReferenceSuggestions =
    suggestionState.open && suggestionState.trigger === "%"
      ? referenceSuggestions
          .filter((item) => {
            const q = suggestionState.query.trim().toLowerCase();
            if (!q) return true;
            return (
              item.label.toLowerCase().includes(q) ||
              (item.meta || "").toLowerCase().includes(q)
            );
          })
          .slice(0, 8)
      : [];

  const filteredMemberSuggestions =
    suggestionState.open && suggestionState.trigger === "@"
      ? memberSuggestions
          .filter((item) => {
            const q = suggestionState.query.trim().toLowerCase();
            if (!q) return true;
            return (
              item.label.toLowerCase().includes(q) ||
              (item.meta || "").toLowerCase().includes(q)
            );
          })
          .slice(0, 8)
      : [];

  const filteredFileSuggestions =
    suggestionState.open && suggestionState.trigger === "!"
      ? fileSuggestions
          .filter((item) => {
            const q = suggestionState.query.trim().toLowerCase();
            if (!q) return true;
            return (
              item.label.toLowerCase().includes(q) ||
              (item.meta || "").toLowerCase().includes(q)
            );
          })
          .slice(0, 8)
      : [];

  const filteredTagSuggestions =
    suggestionState.open && suggestionState.trigger === "#"
      ? tagSuggestions
          .filter((item) => {
            const q = suggestionState.query.trim().toLowerCase();
            if (!q) return true;
            return item.toLowerCase().includes(q);
          })
          .slice(0, 8)
      : [];

  const filteredNoteSuggestions =
    suggestionState.open && suggestionState.trigger === "[["
      ? noteSuggestions
          .filter((item) => {
            const q = suggestionState.query.trim().toLowerCase();
            if (!q) return true;
            return (
              item.label.toLowerCase().includes(q) ||
              (item.meta || "").toLowerCase().includes(q)
            );
          })
          .slice(0, 8)
      : [];

  const activeSuggestions =
    suggestionState.open && suggestionState.trigger === "@"
      ? filteredMemberSuggestions.map((item) => ({ key: item.id, label: item.label, meta: item.meta }))
      : suggestionState.open && suggestionState.trigger === "%"
      ? filteredReferenceSuggestions.map((item) => ({ key: item.id, label: item.label, meta: item.meta }))
      : suggestionState.open && suggestionState.trigger === "!"
      ? filteredFileSuggestions.map((item) => ({ key: item.id, label: item.label, meta: item.meta }))
      : suggestionState.open && suggestionState.trigger === "[["
      ? filteredNoteSuggestions.map((item) => ({ key: item.id, label: item.label, meta: item.meta }))
      : filteredTagSuggestions.map((item) => ({ key: item, label: `#${item}`, meta: undefined as string | undefined }));

  useEffect(() => {
    if (!suggestionState.open) {
      if (suggestionActiveIndex !== 0) setSuggestionActiveIndex(0);
      return;
    }
    if (suggestionActiveIndex >= activeSuggestions.length) {
      setSuggestionActiveIndex(activeSuggestions.length > 0 ? 0 : 0);
    }
  }, [activeSuggestions.length, suggestionActiveIndex, suggestionState.open]);

  useEffect(() => {
    if (!editor) return;
    const activeEditor = editor;

    function closeSuggestions() {
      setSuggestionState((current) => (current.open ? { open: false } : current));
    }

    function updateSuggestions() {
      const { from, $from } = activeEditor.state.selection;
      if (!activeEditor.isFocused) {
        closeSuggestions();
        return;
      }
      if (
        $from.parent.type.name === "codeBlock" ||
        $from.marks().some((mark) => mark.type.name === "code")
      ) {
        closeSuggestions();
        return;
      }
      const lookbackStart = Math.max(0, from - 80);
      const before = activeEditor.state.doc.textBetween(lookbackStart, from, "\n", " ");
      const noteMatch = before.match(/\[\[([^[\]]*)$/);
      if (noteMatch) {
        const query = noteMatch[1] || "";
        const rangeFrom = from - query.length - 2;
        const coords = activeEditor.view.coordsAtPos(from);
        setSuggestionState({
          open: true,
          trigger: "[[",
          query,
          rangeFrom,
          rangeTo: from,
          top: coords.bottom + 8,
          left: coords.left,
        });
        return;
      }
      const match = before.match(/(?:^|[\s([])([@#!%])([A-Za-z0-9_./-]*)$/);
      if (!match) {
        closeSuggestions();
        return;
      }
      const trigger = match[1] as "@" | "#" | "!" | "%";
      const query = match[2] || "";
      const rangeFrom = from - query.length - 1;
      const coords = activeEditor.view.coordsAtPos(from);
      setSuggestionState({
        open: true,
        trigger,
        query,
        rangeFrom,
        rangeTo: from,
        top: coords.bottom + 8,
        left: coords.left,
      });
    }

    function applySuggestion(index: number) {
      const state = suggestionStateRef.current;
      if (!state.open) return false;
      if (state.trigger === "@") {
        const item = filteredMemberSuggestions[index];
        if (!item) return false;
        activeEditor
          .chain()
          .focus()
          .deleteRange({ from: state.rangeFrom, to: state.rangeTo })
          .insertContent(`${item.label} `)
          .run();
        setSuggestionState({ open: false });
        return true;
      }
      if (state.trigger === "%") {
        const item = filteredReferenceSuggestions[index];
        if (!item) return false;
        activeEditor
          .chain()
          .focus()
          .deleteRange({ from: state.rangeFrom, to: state.rangeTo })
          .insertContent(`%[${item.label}] `)
          .run();
        onReferenceLinked?.(item.id);
        setSuggestionState({ open: false });
        return true;
      }
      if (state.trigger === "!") {
        const item = filteredFileSuggestions[index];
        if (!item) return false;
        activeEditor
          .chain()
          .focus()
          .deleteRange({ from: state.rangeFrom, to: state.rangeTo })
          .insertContent(`![${item.label}] `)
          .run();
        onFileLinked?.(item.id);
        setSuggestionState({ open: false });
        return true;
      }
      if (state.trigger === "[[") {
        const item = filteredNoteSuggestions[index];
        if (!item) return false;
        activeEditor
          .chain()
          .focus()
          .deleteRange({ from: state.rangeFrom, to: state.rangeTo })
          .insertContent(`[[${item.label}]] `)
          .run();
        onNoteLinked?.(item.id);
        setSuggestionState({ open: false });
        return true;
      }
      const tag = filteredTagSuggestions[index];
      if (!tag) return false;
      activeEditor
        .chain()
        .focus()
        .deleteRange({ from: state.rangeFrom, to: state.rangeTo })
        .insertContent(`#${tag} `)
        .run();
      setSuggestionState({ open: false });
      return true;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        event.stopPropagation();
        activeEditor.commands.blur();
        setCommandPaletteOpen(true);
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        activeEditor.chain().focus().insertContent("\t").run();
        setSuggestionState({ open: false });
        return;
      }
      const state = suggestionStateRef.current;
      if (!state.open || activeSuggestions.length === 0) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSuggestionActiveIndex((current) => (current + 1) % activeSuggestions.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSuggestionActiveIndex((current) => (current - 1 + activeSuggestions.length) % activeSuggestions.length);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        applySuggestion(suggestionActiveIndex);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setSuggestionState({ open: false });
      }
    }

    function handleDocumentMouseDown(event: MouseEvent) {
      if (shellRef.current?.contains(event.target as Node)) return;
      closeSuggestions();
      setActionDatePopover({ open: false });
      setLinkPopover({ open: false });
    }

    function maybeHandleTokenInteraction(event: MouseEvent) {
      const target = event.target as HTMLElement | null;
      const token = target?.closest?.(".study-log-editor-action-date-token") as HTMLElement | null;
      if (!token) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const from = Number(token.dataset.dateStart || "");
      const to = Number(token.dataset.dateEnd || "");
      const value = token.dataset.dateValue || "";
      if (!Number.isFinite(from) || !Number.isFinite(to) || !value) {
        setActionDatePopover({ open: false });
        return;
      }
      const rect = token.getBoundingClientRect();
      setActionDatePopover({
        open: true,
        from,
        to,
        value,
        top: rect.bottom + 8,
        left: rect.left,
      });
      setLinkPopover({ open: false });
    }

    function handleEditorMouseDown(event: MouseEvent) {
      maybeHandleTokenInteraction(event);
    }

    function handleShellClickCapture(event: MouseEvent) {
      maybeHandleTokenInteraction(event);
    }

    updateSuggestions();
    const handleBlur = () => {
      window.setTimeout(() => {
        if (!activeEditor.isFocused) closeSuggestions();
      }, 120);
    };
    activeEditor.on("update", updateSuggestions);
    activeEditor.on("selectionUpdate", updateSuggestions);
    activeEditor.on("focus", updateSuggestions);
    activeEditor.on("blur", handleBlur);
    let editorDom: HTMLElement | null = null;
    try {
      editorDom = activeEditor.view?.dom ?? null;
    } catch {
      editorDom = null;
    }
    const shell = shellRef.current;
    editorDom?.addEventListener("keydown", handleKeyDown);
    editorDom?.addEventListener("mousedown", handleEditorMouseDown);
    shell?.addEventListener("click", handleShellClickCapture, true);
    shell?.addEventListener("mousedown", handleShellClickCapture, true);
    document.addEventListener("mousedown", handleDocumentMouseDown);
    return () => {
      activeEditor.off("update", updateSuggestions);
      activeEditor.off("selectionUpdate", updateSuggestions);
      activeEditor.off("focus", updateSuggestions);
      activeEditor.off("blur", handleBlur);
      editorDom?.removeEventListener("keydown", handleKeyDown);
      editorDom?.removeEventListener("mousedown", handleEditorMouseDown);
      shell?.removeEventListener("click", handleShellClickCapture, true);
      shell?.removeEventListener("mousedown", handleShellClickCapture, true);
      document.removeEventListener("mousedown", handleDocumentMouseDown);
    };
  }, [activeSuggestions.length, editor, filteredFileSuggestions, filteredMemberSuggestions, filteredNoteSuggestions, filteredReferenceSuggestions, filteredTagSuggestions, onFileLinked, onNoteLinked, onReferenceLinked, suggestionActiveIndex]);

  function openReferenceInsert() {
    editor?.chain().focus().insertContent("%").run();
  }

  function openMemberInsert() {
    editor?.chain().focus().insertContent("@").run();
  }

  function openTagInsert() {
    editor?.chain().focus().insertContent("#").run();
  }

  function openFileInsert() {
    editor?.chain().focus().insertContent("!").run();
  }

  function openNoteLinkInsert() {
    editor?.chain().focus().insertContent("[[").run();
  }

  function applyActionDate(value: string) {
    if (!editor || !actionDatePopover.open) return;
    const normalized = normalizeActionDateToken(value);
    if (!normalized) return;
    const display = formatEditorActionDate(normalized);
    editor
      .chain()
      .focus()
      .deleteRange({ from: actionDatePopover.from, to: actionDatePopover.to })
      .insertContentAt(actionDatePopover.from, display)
      .run();
    setActionDatePopover({ open: false });
  }

  function insertMarkdownLink() {
    if (!editor) return;
    const renderedLink = findRenderedLinkAtCursor(editor);
    if (renderedLink) {
      setLinkPopover({
        open: true,
        from: renderedLink.from,
        to: renderedLink.to,
        label: renderedLink.label,
        href: renderedLink.href,
      });
      return;
    }
    const existingLink = findMarkdownLinkAtSelection(editor);
    if (existingLink) {
      setLinkPopover({
        open: true,
        from: existingLink.from,
        to: existingLink.to,
        label: existingLink.label,
        href: existingLink.href,
      });
      return;
    }
    const { from, to } = editor.state.selection;
    const selectedText = from === to ? "" : editor.state.doc.textBetween(from, to, "\n", " ");
    const label = selectedText.trim() || "Link";
    setLinkPopover({
      open: true,
      from,
      to,
      label,
      href: "https://",
    });
  }

  function applyMarkdownLink(label: string, href: string) {
    if (!editor || !linkPopover.open) return;
    const nextLabel = label.trim() || "Link";
    const nextHref = href.trim() || "https://";
    editor
      .chain()
      .focus()
      .deleteRange({ from: linkPopover.from, to: linkPopover.to })
      .insertContentAt(linkPopover.from, {
        type: "text",
        text: nextLabel,
        marks: [
          {
            type: "link",
            attrs: {
              href: nextHref,
            },
          },
        ],
      })
      .run();
    setLinkPopover({ open: false });
  }

  function removeMarkdownLink() {
    if (!editor || !linkPopover.open) return;
    const nextLabel = linkPopover.label.trim() || "Link";
    editor
      .chain()
      .focus()
      .deleteRange({ from: linkPopover.from, to: linkPopover.to })
      .insertContentAt(linkPopover.from, nextLabel)
      .run();
    setLinkPopover({ open: false });
  }

  const commandItems: CommandItem[] = editor
    ? [
        { id: "bold", label: "Bold", icon: faBold, section: "Format" },
        { id: "italic", label: "Italic", icon: faItalic, section: "Format" },
        { id: "heading", label: "Heading", icon: faHeading, section: "Format" },
        { id: "bullet-list", label: "Bullet List", icon: faListUl, section: "Format" },
        { id: "ordered-list", label: "Ordered List", icon: faListOl, section: "Format" },
        { id: "blockquote", label: "Quote", icon: faQuoteLeft, section: "Format" },
        { id: "code-block", label: "Code Block", icon: faCode, section: "Format" },
        { id: "horizontal-rule", label: "Horizontal Rule", icon: faMinus, section: "Insert" },
        { id: "task", label: "Task", icon: faListCheck, section: "Insert" },
        { id: "link", label: "Link", icon: faLink, section: "Insert" },
        { id: "reference", label: "Reference", icon: faAt, section: "Insert" },
        { id: "member", label: "Member", icon: faAt, section: "Insert" },
        { id: "tag", label: "Tag", icon: faHashtag, section: "Insert" },
        { id: "file", label: "File", icon: faFileLines, section: "Insert" },
        { id: "log-link", label: "Log Link", icon: faLink, section: "Insert" },
        { id: "due-date", label: "Due Date", icon: faCalendarDay, section: "Insert" },
        { id: "table", label: "Table", icon: faTable, section: "Insert" },
        ...(editor.isActive("table")
          ? [
              { id: "table-add-row", label: "Add Row", icon: faTable, section: "Table" },
              { id: "table-delete-row", label: "Delete Row", icon: faTable, section: "Table" },
              { id: "table-add-column", label: "Add Column", icon: faTable, section: "Table" },
              { id: "table-delete-column", label: "Delete Column", icon: faTable, section: "Table" },
              { id: "table-delete", label: "Delete Table", icon: faTable, section: "Table" },
            ]
          : []),
      ]
    : [];

  function handleCommandSelect(id: string) {
    if (!editor) return;
    setCommandPaletteOpen(false);
    switch (id) {
      case "bold":
        editor.chain().focus().toggleBold().run();
        break;
      case "italic":
        editor.chain().focus().toggleItalic().run();
        break;
      case "heading":
        editor.chain().focus().toggleHeading({ level: 2 }).run();
        break;
      case "bullet-list":
        editor.chain().focus().toggleBulletList().run();
        break;
      case "ordered-list":
        editor.chain().focus().toggleOrderedList().run();
        break;
      case "blockquote":
        editor.chain().focus().toggleBlockquote().run();
        break;
      case "code-block":
        editor.chain().focus().toggleCodeBlock().run();
        break;
      case "horizontal-rule":
        editor.chain().focus().setHorizontalRule().run();
        break;
      case "task":
        editor.chain().focus().insertContent("[ ] ").run();
        break;
      case "link":
        insertMarkdownLink();
        break;
      case "reference":
        openReferenceInsert();
        break;
      case "member":
        openMemberInsert();
        break;
      case "tag":
        openTagInsert();
        break;
      case "file":
        openFileInsert();
        break;
      case "log-link":
        openNoteLinkInsert();
        break;
      case "due-date":
        editor.chain().focus().insertContent(new Date().toISOString().slice(0, 10)).run();
        break;
      case "table":
        editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
        break;
      case "table-add-row":
        editor.chain().focus().addRowAfter().run();
        break;
      case "table-delete-row":
        editor.chain().focus().deleteRow().run();
        break;
      case "table-add-column":
        editor.chain().focus().addColumnAfter().run();
        break;
      case "table-delete-column":
        editor.chain().focus().deleteColumn().run();
        break;
      case "table-delete":
        editor.chain().focus().deleteTable().run();
        break;
      default:
        break;
    }
  }

  return (
    <div ref={shellRef} className="study-log-editor-shell">
      <div className="study-log-editor-toolbar meetings-toolbar">
        <div className="meetings-filter-group">
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("bold") ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleBold().run()}
            title="Bold"
          >
            <FontAwesomeIcon icon={faBold} />
          </button>
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("italic") ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleItalic().run()}
            title="Italic"
          >
            <FontAwesomeIcon icon={faItalic} />
          </button>
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("heading", { level: 2 }) ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}
            title="Heading"
          >
            <FontAwesomeIcon icon={faHeading} />
          </button>
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("bulletList") ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleBulletList().run()}
            title="Bullet List"
          >
            <FontAwesomeIcon icon={faListUl} />
          </button>
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("orderedList") ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleOrderedList().run()}
            title="Ordered List"
          >
            <FontAwesomeIcon icon={faListOl} />
          </button>
          <button
            type="button"
            className="ghost docs-action-btn"
            onClick={insertMarkdownLink}
            title="Link"
          >
            <FontAwesomeIcon icon={faLink} />
          </button>
          <button
            type="button"
            className="ghost docs-action-btn"
            onClick={() => editor?.chain().focus().insertContent("[ ] ").run()}
            title="Task"
          >
            <FontAwesomeIcon icon={faListCheck} />
          </button>
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("blockquote") ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleBlockquote().run()}
            title="Quote"
          >
            <FontAwesomeIcon icon={faQuoteLeft} />
          </button>
          <button
            type="button"
            className={`ghost docs-action-btn ${editor?.isActive("codeBlock") ? "active" : ""}`}
            onClick={() => editor?.chain().focus().toggleCodeBlock().run()}
            title="Code Block"
          >
            <FontAwesomeIcon icon={faCode} />
          </button>
          <button
            type="button"
            className="ghost docs-action-btn"
            onClick={() => editor?.chain().focus().setHorizontalRule().run()}
            title="Horizontal Rule"
          >
            <FontAwesomeIcon icon={faMinus} />
          </button>
          <div className="proposal-table-menu-wrapper" ref={tableMenuRef}>
            <button
              type="button"
              className={`ghost docs-action-btn ${editor?.isActive("table") ? "active" : ""}`}
              onClick={() => setTableMenuOpen((prev) => !prev)}
              title="Table"
            >
              <FontAwesomeIcon icon={faTable} />
            </button>
            {tableMenuOpen ? (
              <div className="proposal-table-dropdown">
                {!editor?.isActive("table") ? (
                  <>
                    <div className="proposal-table-grid-label">
                      {tableGridHover[0] > 0 ? `${tableGridHover[0]} × ${tableGridHover[1]} table` : "Select size"}
                    </div>
                    <div className="proposal-table-grid" onMouseLeave={() => setTableGridHover([0, 0])}>
                      {Array.from({ length: 6 }, (_, row) =>
                        Array.from({ length: 6 }, (_, col) => (
                          <div
                            key={`${row}-${col}`}
                            className={`proposal-table-grid-cell ${row < tableGridHover[0] && col < tableGridHover[1] ? "active" : ""}`}
                            onMouseEnter={() => setTableGridHover([row + 1, col + 1])}
                            onClick={() => {
                              editor?.chain().focus().insertTable({ rows: row + 2, cols: col + 1, withHeaderRow: true }).run();
                              setTableMenuOpen(false);
                              setTableGridHover([0, 0]);
                            }}
                          />
                        )),
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={() => { editor?.chain().focus().addRowBefore().run(); setTableMenuOpen(false); }}>Add Row Before</button>
                    <button type="button" onClick={() => { editor?.chain().focus().addRowAfter().run(); setTableMenuOpen(false); }}>Add Row After</button>
                    <button type="button" onClick={() => { editor?.chain().focus().addColumnBefore().run(); setTableMenuOpen(false); }}>Add Column Before</button>
                    <button type="button" onClick={() => { editor?.chain().focus().addColumnAfter().run(); setTableMenuOpen(false); }}>Add Column After</button>
                    <button type="button" onClick={() => { editor?.chain().focus().deleteRow().run(); setTableMenuOpen(false); }}>Delete Row</button>
                    <button type="button" onClick={() => { editor?.chain().focus().deleteColumn().run(); setTableMenuOpen(false); }}>Delete Column</button>
                    <button type="button" className="danger" onClick={() => { editor?.chain().focus().deleteTable().run(); setTableMenuOpen(false); }}>Delete Table</button>
                  </>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
      {editor?.isActive("table") ? (
        <div className="study-log-table-actions">
          <button type="button" className="ghost icon-text-button small" onClick={() => editor.chain().focus().addColumnAfter().run()}>
            Add Column
          </button>
          <button type="button" className="ghost icon-text-button small" onClick={() => editor.chain().focus().deleteColumn().run()}>
            Delete Column
          </button>
          <button type="button" className="ghost icon-text-button small" onClick={() => editor.chain().focus().addRowAfter().run()}>
            Add Row
          </button>
          <button type="button" className="ghost icon-text-button small" onClick={() => editor.chain().focus().deleteRow().run()}>
            Delete Row
          </button>
          <button type="button" className="ghost icon-text-button small danger" onClick={() => editor.chain().focus().deleteTable().run()}>
            Delete Table
          </button>
        </div>
      ) : null}
      <div className="study-log-editor-stage">
        <EditorContent editor={editor} />
      </div>
      {suggestionState.open && activeSuggestions.length > 0 ? (
        <div
          className="study-log-editor-suggestions cmd-palette"
          style={{ top: suggestionState.top, left: suggestionState.left }}
        >
          <div className="study-log-editor-suggestions-head cmd-palette-input-row">
            <FontAwesomeIcon icon={triggerIcon(suggestionState.trigger)} className="cmd-palette-search-icon" />
            <span className="study-log-editor-suggestions-label">
              {suggestionState.trigger === "@" ? "Members" : suggestionState.trigger === "%" ? "References" : suggestionState.trigger === "#" ? "Tags" : suggestionState.trigger === "!" ? "Files" : "Logs"}
            </span>
            <kbd className="cmd-palette-kbd">enter</kbd>
          </div>
          <div className="study-log-editor-suggestions-list cmd-palette-list">
          {activeSuggestions.map((item, index) => (
            <button
              key={item.key}
              type="button"
              className={`study-log-editor-suggestion cmd-palette-item${index === suggestionActiveIndex ? " active" : ""}`}
              onMouseDown={(event) => {
                event.preventDefault();
                if (suggestionState.trigger === "@") {
                  const member = filteredMemberSuggestions[index];
                  if (!member || !editor) return;
                  editor
                    .chain()
                    .focus()
                    .deleteRange({ from: suggestionState.rangeFrom, to: suggestionState.rangeTo })
                    .insertContent(`${member.label} `)
                    .run();
                } else if (suggestionState.trigger === "%") {
                  const ref = filteredReferenceSuggestions[index];
                  if (!ref || !editor) return;
                  editor
                    .chain()
                    .focus()
                    .deleteRange({ from: suggestionState.rangeFrom, to: suggestionState.rangeTo })
                    .insertContent(`%[${ref.label}] `)
                    .run();
                  onReferenceLinked?.(ref.id);
                } else if (suggestionState.trigger === "!") {
                  const file = filteredFileSuggestions[index];
                  if (!file || !editor) return;
                  editor
                    .chain()
                    .focus()
                    .deleteRange({ from: suggestionState.rangeFrom, to: suggestionState.rangeTo })
                    .insertContent(`![${file.label}] `)
                    .run();
                  onFileLinked?.(file.id);
                } else if (suggestionState.trigger === "[[") {
                  const note = filteredNoteSuggestions[index];
                  if (!note || !editor) return;
                  editor
                    .chain()
                    .focus()
                    .deleteRange({ from: suggestionState.rangeFrom, to: suggestionState.rangeTo })
                    .insertContent(`[[${note.label}]] `)
                    .run();
                  onNoteLinked?.(note.id);
                } else {
                  const tag = filteredTagSuggestions[index];
                  if (!tag || !editor) return;
                  editor
                    .chain()
                    .focus()
                    .deleteRange({ from: suggestionState.rangeFrom, to: suggestionState.rangeTo })
                    .insertContent(`#${tag} `)
                    .run();
                }
                setSuggestionState({ open: false });
              }}
            >
              <FontAwesomeIcon icon={triggerIcon(suggestionState.trigger)} className="cmd-palette-item-icon" />
              <span className="study-log-editor-suggestion-body">
                <span className="study-log-editor-suggestion-title">{item.label}</span>
                {item.meta ? <small>{item.meta}</small> : null}
              </span>
            </button>
          ))}
          </div>
        </div>
      ) : null}
      {actionDatePopover.open ? (
        <div
          className="study-log-editor-action-date-popover cmd-palette"
          style={{ top: actionDatePopover.top, left: actionDatePopover.left }}
        >
          <div className="study-log-editor-suggestions-head cmd-palette-input-row">
            <FontAwesomeIcon icon={faCalendarDay} className="cmd-palette-search-icon" />
            <span className="study-log-editor-suggestions-label">Due Date</span>
          </div>
          <div className="study-log-editor-action-date-body">
            <input
              type="date"
              value={actionDatePopover.value}
              onChange={(event) => applyActionDate(event.target.value)}
              autoFocus
            />
            <button type="button" className="ghost" onClick={() => setActionDatePopover({ open: false })}>
              Close
            </button>
          </div>
        </div>
      ) : null}
      {linkPopover.open ? (
        <div className="cmd-palette-overlay" onClick={() => setLinkPopover({ open: false })}>
          <div className="study-log-editor-link-palette cmd-palette" onClick={(event) => event.stopPropagation()}>
            <div className="study-log-editor-suggestions-head cmd-palette-input-row">
              <FontAwesomeIcon icon={faLink} className="cmd-palette-search-icon" />
              <span className="study-log-editor-suggestions-label">Link</span>
              <kbd className="cmd-palette-kbd">esc</kbd>
            </div>
            <div className="study-log-editor-link-body">
              <label>
                <span>Label</span>
                <input
                  type="text"
                  value={linkPopover.label}
                  onChange={(event) => setLinkPopover((current) => current.open ? { ...current, label: event.target.value } : current)}
                  autoFocus
                />
              </label>
              <label>
                <span>URL</span>
                <input
                  type="text"
                  value={linkPopover.href}
                  onChange={(event) => setLinkPopover((current) => current.open ? { ...current, href: event.target.value } : current)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      applyMarkdownLink(linkPopover.label, linkPopover.href);
                    } else if (event.key === "Escape") {
                      event.preventDefault();
                      setLinkPopover({ open: false });
                    }
                  }}
                />
              </label>
              <div className="study-log-editor-link-actions">
                <button type="button" onClick={() => applyMarkdownLink(linkPopover.label, linkPopover.href)}>
                  Save
                </button>
                <button type="button" className="ghost" onClick={removeMarkdownLink}>
                  Remove
                </button>
                <button type="button" className="ghost" onClick={() => setLinkPopover({ open: false })}>
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      {commandPaletteOpen ? (
        <CommandPalette
          items={commandItems}
          onSelect={handleCommandSelect}
          onClose={() => setCommandPaletteOpen(false)}
          aggressiveKeyboardCapture
        />
      ) : null}
    </div>
  );
}
  function triggerIcon(trigger: "@" | "#" | "!" | "%" | "[[") {
    if (trigger === "@") return faAt;
    if (trigger === "%") return faAt;
    if (trigger === "#") return faHashtag;
    if (trigger === "!") return faFileLines;
    return faLink;
  }
