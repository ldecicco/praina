import { useEffect, useRef, useState } from "react";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import { Extension } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import { Markdown } from "@tiptap/markdown";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import katex from "katex";
import { api } from "../lib/api";
import type { ResearchStudyFile } from "../types";
import {
  faBold,
  faCode,
  faHeading,
  faItalic,
  faListOl,
  faListUl,
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

              for (const match of text.matchAll(/@\[[^\]]+\]/g)) {
                const start = base + (match.index ?? 0);
                const end = start + match[0].length;
                decorations.push(Decoration.inline(start, end, { class: "study-log-editor-citation-token" }));
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
  linkedFiles?: ResearchStudyFile[];
  projectId?: string | null;
  collectionId?: string | null;
  spaceId?: string;
  tagSuggestions?: string[];
  onReferenceLinked?: (referenceId: string) => void;
  onFileLinked?: (fileId: string) => void;
};

type SuggestionState =
  | {
      open: false;
    }
  | {
      open: true;
      trigger: "@" | "#" | "!";
      query: string;
      rangeFrom: number;
      rangeTo: number;
      top: number;
      left: number;
    };

export function StudyLogRichEditor({
  value,
  placeholder,
  onChange,
  onReady,
  referenceSuggestions = [],
  fileSuggestions = [],
  linkedFiles = [],
  projectId,
  collectionId,
  spaceId,
  tagSuggestions = [],
  onReferenceLinked,
  onFileLinked,
}: Props) {
  const [tableMenuOpen, setTableMenuOpen] = useState(false);
  const [tableGridHover, setTableGridHover] = useState<[number, number]>([0, 0]);
  const [suggestionState, setSuggestionState] = useState<SuggestionState>({ open: false });
  const [suggestionActiveIndex, setSuggestionActiveIndex] = useState(0);
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
    suggestionState.open && suggestionState.trigger === "@"
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

  const activeSuggestions =
    suggestionState.open && suggestionState.trigger === "@"
      ? filteredReferenceSuggestions.map((item) => ({ key: item.id, label: item.label, meta: item.meta }))
      : suggestionState.open && suggestionState.trigger === "!"
      ? filteredFileSuggestions.map((item) => ({ key: item.id, label: item.label, meta: item.meta }))
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
      const match = before.match(/(?:^|[\s([])([@#!])([A-Za-z0-9_./-]*)$/);
      if (!match) {
        closeSuggestions();
        return;
      }
      const trigger = match[1] as "@" | "#" | "!";
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
        const item = filteredReferenceSuggestions[index];
        if (!item) return false;
        activeEditor
          .chain()
          .focus()
          .deleteRange({ from: state.rangeFrom, to: state.rangeTo })
          .insertContent(`@[${item.label}] `)
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
    editorDom?.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handleDocumentMouseDown);
    return () => {
      activeEditor.off("update", updateSuggestions);
      activeEditor.off("selectionUpdate", updateSuggestions);
      activeEditor.off("focus", updateSuggestions);
      activeEditor.off("blur", handleBlur);
      editorDom?.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleDocumentMouseDown);
    };
  }, [activeSuggestions.length, editor, filteredFileSuggestions, filteredReferenceSuggestions, filteredTagSuggestions, onFileLinked, onReferenceLinked, suggestionActiveIndex]);

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
          className="study-log-editor-suggestions"
          style={{ top: suggestionState.top, left: suggestionState.left }}
        >
          {activeSuggestions.map((item, index) => (
            <button
              key={item.key}
              type="button"
              className={`study-log-editor-suggestion${index === suggestionActiveIndex ? " active" : ""}`}
              onMouseDown={(event) => {
                event.preventDefault();
                if (suggestionState.trigger === "@") {
                  const ref = filteredReferenceSuggestions[index];
                  if (!ref || !editor) return;
                  editor
                    .chain()
                    .focus()
                    .deleteRange({ from: suggestionState.rangeFrom, to: suggestionState.rangeTo })
                    .insertContent(`@[${ref.label}] `)
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
              <span>{item.label}</span>
              {item.meta ? <small>{item.meta}</small> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
