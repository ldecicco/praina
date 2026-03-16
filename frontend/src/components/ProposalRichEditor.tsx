import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Extension } from "@tiptap/core";
import Collaboration from "@tiptap/extension-collaboration";
import CollaborationCaret from "@tiptap/extension-collaboration-caret";
import { EditorContent, useEditor } from "@tiptap/react";
import { ySyncPluginKey } from "@tiptap/y-tiptap";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import Image from "@tiptap/extension-image";
import { Table, TableRow, TableHeader, TableCell } from "@tiptap/extension-table";
import { Markdown } from "@tiptap/markdown";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faAlignCenter,
  faAlignJustify,
  faAlignLeft,
  faAlignRight,
  faBold,
  faCode,
  faComment,
  faHeading,
  faImage,
  faItalic,
  faListOl,
  faListUl,
  faQuoteLeft,
  faReply,
  faTable,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";

import { renderMarkdown } from "../lib/renderMarkdown";
import { api } from "../lib/api";
import { ProposalCollabProvider, collabFieldName, isCollabDocEmpty } from "../lib/collab";
import type { AuthUser, ProposalReviewFinding } from "../types";

type EditorMode = "write" | "markdown" | "preview";
const PROPOSAL_COLLAB_ENABLED = import.meta.env.VITE_ENABLE_PROPOSAL_COLLAB !== "0";
type CollabPresenceUser = {
  clientId: number;
  id?: string;
  name: string;
  color: string;
  isCurrentUser: boolean;
};

type Props = {
  value: string;
  placeholder: string;
  onChange: (value: string, options?: { remote?: boolean }) => void;
  projectId?: string;
  sectionId?: string;
  hasCollabState?: boolean;
  findings?: ProposalReviewFinding[];
  currentUser?: AuthUser | null;
  onCreateComment?: (anchorText: string, anchorPrefix: string, anchorSuffix: string, summary: string) => void;
  onReplyToFinding?: (parentId: string, summary: string) => void;
  onDeleteFinding?: (findingId: string) => void;
};

type TextSegment = {
  start: number;
  end: number;
  pos: number;
};

const proposalReviewPluginKey = new PluginKey("proposal-review-annotations");

function collectTextSegments(doc: Parameters<NonNullable<ReturnType<typeof useEditor>>["state"]["doc"]["descendants"]>[0] extends never ? never : any): { plainText: string; segments: TextSegment[] } {
  const segments: TextSegment[] = [];
  let plainText = "";
  doc.descendants((node: { isText: boolean; text?: string }, pos: number) => {
    if (!node.isText || !node.text) return;
    const start = plainText.length;
    plainText += node.text;
    segments.push({
      start,
      end: plainText.length,
      pos,
    });
  });
  return { plainText, segments };
}

function locateFindingRange(
  plainText: string,
  segments: TextSegment[],
  finding: ProposalReviewFinding
): { from: number; to: number } | null {
  if (!finding.anchor_text?.trim()) return null;
  const needle = finding.anchor_text.trim();
  const candidates: number[] = [];
  let cursor = plainText.indexOf(needle);
  while (cursor !== -1) {
    candidates.push(cursor);
    cursor = plainText.indexOf(needle, cursor + 1);
  }
  if (candidates.length === 0) return null;

  const prefix = finding.anchor_prefix?.trim() || "";
  const suffix = finding.anchor_suffix?.trim() || "";
  const preferredIndex =
    candidates.find((index) => {
      const before = prefix ? plainText.slice(Math.max(0, index - prefix.length - 24), index) : "";
      const after = suffix
        ? plainText.slice(index + needle.length, index + needle.length + suffix.length + 24)
        : "";
      return (!prefix || before.includes(prefix)) && (!suffix || after.includes(suffix));
    }) ?? candidates[0];

  const endIndex = preferredIndex + needle.length;
  const startSegment = segments.find((segment) => preferredIndex >= segment.start && preferredIndex < segment.end);
  const endSegment = segments.find((segment) => endIndex > segment.start && endIndex <= segment.end);
  if (!startSegment || !endSegment) return null;

  return {
    from: startSegment.pos + (preferredIndex - startSegment.start),
    to: endSegment.pos + (endIndex - endSegment.start),
  };
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function buildPresenceUsers(provider: ProposalCollabProvider | null, currentUserId?: string | null): CollabPresenceUser[] {
  if (!provider) return [];
  const items: CollabPresenceUser[] = [];
  for (const [clientId, state] of provider.awareness.getStates().entries()) {
    const user = state.user as { id?: string; name?: string; color?: string } | undefined;
    if (!user?.name || !user.color) continue;
    items.push({
      clientId,
      id: user.id,
      name: user.name,
      color: user.color,
      isCurrentUser: Boolean(currentUserId && user.id === currentUserId),
    });
  }

  return items.sort((left, right) => {
    if (left.isCurrentUser && !right.isCurrentUser) return -1;
    if (!left.isCurrentUser && right.isCurrentUser) return 1;
    return left.name.localeCompare(right.name);
  });
}

function createCollabCaret(user: { name: string; color: string }): HTMLElement {
  const cursor = document.createElement("span");
  cursor.classList.add("proposal-collab-caret");
  cursor.style.setProperty("--collab-color", user.color);

  const stem = document.createElement("span");
  stem.classList.add("proposal-collab-caret-stem");
  cursor.appendChild(stem);

  const label = document.createElement("span");
  label.classList.add("proposal-collab-caret-label");
  label.textContent = user.name;
  cursor.appendChild(label);

  return cursor;
}

function createCollabSelection(user: { color: string }) {
  return {
    class: "proposal-collab-selection",
    style: `--collab-color: ${user.color}; background-color: color-mix(in srgb, ${user.color} 22%, transparent);`,
  };
}

export function ProposalRichEditor({
  value,
  placeholder,
  onChange,
  projectId,
  sectionId,
  hasCollabState = false,
  findings = [],
  currentUser,
  onCreateComment,
  onReplyToFinding,
  onDeleteFinding,
}: Props) {
  const [mode, setMode] = useState<EditorMode>("write");
  const [activeFindingId, setActiveFindingId] = useState<string>("");
  const [hasSelection, setHasSelection] = useState(false);
  const [commentInput, setCommentInput] = useState("");
  const [commentingActive, setCommentingActive] = useState(false);
  const [replyingToId, setReplyingToId] = useState<string | null>(null);
  const [replyInput, setReplyInput] = useState("");
  const [tableMenuOpen, setTableMenuOpen] = useState(false);
  const [tableGridHover, setTableGridHover] = useState<[number, number]>([0, 0]);
  const [imageUploading, setImageUploading] = useState(false);
  const [presenceUsers, setPresenceUsers] = useState<CollabPresenceUser[]>([]);
  const findingsRef = useRef<ProposalReviewFinding[]>([]);
  const activeFindingIdRef = useRef("");
  const imageInputRef = useRef<HTMLInputElement>(null);
  const tableMenuRef = useRef<HTMLDivElement>(null);
  const collabSeededRef = useRef(false);
  const [collabProvider, setCollabProvider] = useState<ProposalCollabProvider | null>(null);
  const collabToken = api.getAuthToken();
  const collabEnabled = Boolean(PROPOSAL_COLLAB_ENABLED && projectId && sectionId && currentUser && collabToken);

  const anchoredFindings = useMemo(
    () => findings.filter((item) => item.scope === "anchor" && item.anchor_text && item.status !== "resolved"),
    [findings]
  );

  findingsRef.current = anchoredFindings;
  activeFindingIdRef.current = activeFindingId;

  // Close table menu on outside click
  useEffect(() => {
    if (!tableMenuOpen) return;
    function handleClick(e: MouseEvent) {
      if (tableMenuRef.current && !tableMenuRef.current.contains(e.target as Node)) {
        setTableMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [tableMenuOpen]);

  const proposalReviewAnnotations = useMemo(
    () =>
      Extension.create({
        name: "proposalReviewAnnotations",
        addProseMirrorPlugins() {
          return [
            new Plugin({
              key: proposalReviewPluginKey,
              props: {
                decorations(state) {
                  const currentFindings = findingsRef.current;
                  if (!currentFindings.length) {
                    return DecorationSet.empty;
                  }
                  const { plainText, segments } = collectTextSegments(state.doc);
                  const decorations = currentFindings.flatMap((finding) => {
                    const range = locateFindingRange(plainText, segments, finding);
                    if (!range) return [];
                    const toneClass =
                      finding.finding_type === "comment"
                        ? "comment"
                        : finding.finding_type === "issue"
                          ? "issue"
                          : finding.finding_type === "strength"
                            ? "strength"
                            : "warning";
                    const activeClass = finding.id === activeFindingIdRef.current ? "active" : "";
                    return [
                      Decoration.inline(range.from, range.to, {
                        class: `proposal-review-highlight ${toneClass} ${activeClass}`.trim(),
                        "data-review-finding-id": finding.id,
                      }),
                    ];
                  });
                  return DecorationSet.create(state.doc, decorations);
                },
              },
            }),
          ];
        },
      }),
    []
  );

  useEffect(() => {
    collabSeededRef.current = false;
    if (!collabEnabled || !projectId || !sectionId || !currentUser || !collabToken) {
      setCollabProvider(null);
      setPresenceUsers([]);
      return;
    }
    const provider = new ProposalCollabProvider(projectId, sectionId, collabToken, {
      id: currentUser.id,
      name: currentUser.display_name,
    });
    setCollabProvider(provider);
    provider.connect();
    return () => {
      provider.destroy();
      setCollabProvider((current) => (current === provider ? null : current));
    };
  }, [collabEnabled, projectId, sectionId, currentUser?.id, currentUser?.display_name, collabToken]);

  useEffect(() => {
    if (!collabProvider) {
      setPresenceUsers([]);
      return;
    }
    const syncPresence = () => {
      setPresenceUsers(buildPresenceUsers(collabProvider, currentUser?.id));
    };
    syncPresence();
    collabProvider.awareness.on("change", syncPresence);
    collabProvider.awareness.on("update", syncPresence);
    return () => {
      collabProvider.awareness.off("change", syncPresence);
      collabProvider.awareness.off("update", syncPresence);
    };
  }, [collabProvider, currentUser?.id]);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({ undoRedo: collabProvider ? false : undefined }),
      Placeholder.configure({ placeholder }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Image,
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
      ...(collabProvider
        ? [
            Collaboration.configure({
              document: collabProvider.doc,
              field: collabFieldName(),
            }),
            CollaborationCaret.configure({
              provider: collabProvider,
              user: {
                name: currentUser?.display_name || "User",
                color: String(collabProvider.awareness.getLocalState()?.user?.color || "#7c5cfc"),
              },
              render: createCollabCaret,
              selectionRender: createCollabSelection,
            }),
          ]
        : []),
      proposalReviewAnnotations,
    ],
    content: collabProvider ? undefined : value || "",
    contentType: collabProvider ? undefined : "markdown",
    editorProps: {
      attributes: {
        class: "proposal-editor-content",
      },
    },
    onUpdate: ({ editor: nextEditor, transaction }) => {
      const next = nextEditor.getMarkdown();
      if (next !== value) {
        const syncMeta = transaction.getMeta(ySyncPluginKey) as { isChangeOrigin?: boolean } | undefined;
        onChange(next, { remote: Boolean(collabProvider && syncMeta?.isChangeOrigin) });
      }
    },
    onSelectionUpdate: ({ editor: nextEditor }) => {
      const { from, to } = nextEditor.state.selection;
      setHasSelection(from !== to);
    },
  }, [collabProvider, placeholder, currentUser?.display_name]);

  useEffect(() => {
    if (!editor || collabProvider) return;
    const current = editor.getMarkdown();
    if (current === value) return;
    editor.commands.setContent(value || "", { contentType: "markdown" });
  }, [editor, value, collabProvider]);

  useEffect(() => {
    if (!editor || !collabProvider) return;
    return collabProvider.onceSynced(() => {
      if (!collabSeededRef.current) {
        collabSeededRef.current = true;
        if (!hasCollabState && isCollabDocEmpty(collabProvider.doc) && value.trim()) {
          editor.commands.setContent(value, { contentType: "markdown" });
        }
      }
    });
  }, [collabProvider, editor, hasCollabState, value]);

  useEffect(() => {
    if (!anchoredFindings.length) {
      setActiveFindingId("");
      return;
    }
    if (!anchoredFindings.some((item) => item.id === activeFindingId)) {
      setActiveFindingId(anchoredFindings[0].id);
    }
  }, [anchoredFindings, activeFindingId]);

  useEffect(() => {
    if (!editor) return;
    editor.view.dispatch(editor.state.tr.setMeta("proposal-review-refresh", Date.now()));
  }, [editor, anchoredFindings, activeFindingId]);

  function jumpToFinding(finding: ProposalReviewFinding) {
    if (!editor) return;
    setActiveFindingId(finding.id);
    const { plainText, segments } = collectTextSegments(editor.state.doc);
    const range = locateFindingRange(plainText, segments, finding);
    if (range) {
      editor.commands.focus();
      editor.commands.setTextSelection(range);
      editor.commands.scrollIntoView();
      return;
    }
    editor.commands.focus();
  }

  function handleEditorStageClick(event: React.MouseEvent<HTMLDivElement>) {
    const target = event.target instanceof HTMLElement ? event.target : null;
    const findingId = target?.closest<HTMLElement>("[data-review-finding-id]")?.dataset.reviewFindingId;
    if (!findingId) return;
    setActiveFindingId(findingId);
  }

  function handleStartComment() {
    if (!editor || !onCreateComment) return;
    setCommentingActive(true);
    setCommentInput("");
  }

  function handleSubmitComment() {
    if (!editor || !onCreateComment || !commentInput.trim()) return;
    const { from, to } = editor.state.selection;
    if (from === to) return;
    const { plainText, segments } = collectTextSegments(editor.state.doc);

    // Map editor positions back to plain text offsets
    let plainFrom = 0;
    let plainTo = 0;
    for (const seg of segments) {
      if (from >= seg.pos && from < seg.pos + (seg.end - seg.start)) {
        plainFrom = seg.start + (from - seg.pos);
      }
      if (to >= seg.pos && to <= seg.pos + (seg.end - seg.start)) {
        plainTo = seg.start + (to - seg.pos);
      }
    }

    const anchorText = plainText.slice(plainFrom, plainTo);
    const anchorPrefix = plainText.slice(Math.max(0, plainFrom - 30), plainFrom);
    const anchorSuffix = plainText.slice(plainTo, plainTo + 30);

    onCreateComment(anchorText, anchorPrefix, anchorSuffix, commentInput.trim());
    setCommentingActive(false);
    setCommentInput("");
  }

  function handleSubmitReply() {
    if (!replyingToId || !replyInput.trim() || !onReplyToFinding) return;
    onReplyToFinding(replyingToId, replyInput.trim());
    setReplyingToId(null);
    setReplyInput("");
  }

  async function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !editor || !projectId) return;
    e.target.value = "";
    setImageUploading(true);
    try {
      const result = await api.uploadProposalImage(projectId, file);
      editor.chain().focus().setImage({ src: result.url, alt: file.name }).run();
    } catch (err) {
      console.error("Image upload failed:", err);
    } finally {
      setImageUploading(false);
    }
  }

  const modeTabs = (
    <div className="delivery-tabs proposal-editor-mode-tabs">
      <button
        type="button"
        className={`delivery-tab ${mode === "write" ? "active" : ""}`}
        onClick={() => setMode("write")}
      >
        Write
      </button>
      <button
        type="button"
        className={`delivery-tab ${mode === "markdown" ? "active" : ""}`}
        onClick={() => setMode("markdown")}
      >
        Markdown
      </button>
      <button
        type="button"
        className={`delivery-tab ${mode === "preview" ? "active" : ""}`}
        onClick={() => setMode("preview")}
      >
        Preview
      </button>
    </div>
  );

  return (
    <div className="proposal-editor-shell">
      <div className="proposal-editor-toolbar meetings-toolbar">
        <div className="meetings-filter-group">
          {modeTabs}
          {mode === "write" ? (
            <>
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
              <span className="toolbar-sep" />
              <button
                type="button"
                className={`ghost docs-action-btn ${editor?.isActive({ textAlign: "left" }) ? "active" : ""}`}
                onClick={() => editor?.chain().focus().setTextAlign("left").run()}
                title="Align Left"
              >
                <FontAwesomeIcon icon={faAlignLeft} />
              </button>
              <button
                type="button"
                className={`ghost docs-action-btn ${editor?.isActive({ textAlign: "center" }) ? "active" : ""}`}
                onClick={() => editor?.chain().focus().setTextAlign("center").run()}
                title="Align Center"
              >
                <FontAwesomeIcon icon={faAlignCenter} />
              </button>
              <button
                type="button"
                className={`ghost docs-action-btn ${editor?.isActive({ textAlign: "right" }) ? "active" : ""}`}
                onClick={() => editor?.chain().focus().setTextAlign("right").run()}
                title="Align Right"
              >
                <FontAwesomeIcon icon={faAlignRight} />
              </button>
              <button
                type="button"
                className={`ghost docs-action-btn ${editor?.isActive({ textAlign: "justify" }) ? "active" : ""}`}
                onClick={() => editor?.chain().focus().setTextAlign("justify").run()}
                title="Justify"
              >
                <FontAwesomeIcon icon={faAlignJustify} />
              </button>
              <span className="toolbar-sep" />
              {projectId ? (
                <>
                  <input
                    ref={imageInputRef}
                    type="file"
                    accept="image/*"
                    style={{ display: "none" }}
                    onChange={handleImageSelect}
                  />
                  <button
                    type="button"
                    className="ghost docs-action-btn"
                    onClick={() => imageInputRef.current?.click()}
                    title="Insert Image"
                    disabled={imageUploading}
                  >
                    <FontAwesomeIcon icon={faImage} />{imageUploading ? " ..." : ""}
                  </button>
                </>
              ) : null}
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
                          {tableGridHover[0] > 0
                            ? `${tableGridHover[0]} × ${tableGridHover[1]} table`
                            : "Select size"}
                        </div>
                        <div
                          className="proposal-table-grid"
                          onMouseLeave={() => setTableGridHover([0, 0])}
                        >
                          {Array.from({ length: 6 }, (_, row) =>
                            Array.from({ length: 6 }, (_, col) => (
                              <div
                                key={`${row}-${col}`}
                                className={`proposal-table-grid-cell ${
                                  row < tableGridHover[0] && col < tableGridHover[1] ? "active" : ""
                                }`}
                                onMouseEnter={() => setTableGridHover([row + 1, col + 1])}
                                onClick={() => {
                                  editor?.chain().focus().insertTable({
                                    rows: row + 2,
                                    cols: col + 1,
                                    withHeaderRow: true,
                                  }).run();
                                  setTableMenuOpen(false);
                                  setTableGridHover([0, 0]);
                                }}
                              />
                            ))
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => { editor?.chain().focus().addRowBefore().run(); setTableMenuOpen(false); }}>
                          Add Row Before
                        </button>
                        <button type="button" onClick={() => { editor?.chain().focus().addRowAfter().run(); setTableMenuOpen(false); }}>
                          Add Row After
                        </button>
                        <button type="button" onClick={() => { editor?.chain().focus().addColumnBefore().run(); setTableMenuOpen(false); }}>
                          Add Column Before
                        </button>
                        <button type="button" onClick={() => { editor?.chain().focus().addColumnAfter().run(); setTableMenuOpen(false); }}>
                          Add Column After
                        </button>
                        <button type="button" onClick={() => { editor?.chain().focus().deleteRow().run(); setTableMenuOpen(false); }}>
                          Delete Row
                        </button>
                        <button type="button" onClick={() => { editor?.chain().focus().deleteColumn().run(); setTableMenuOpen(false); }}>
                          Delete Column
                        </button>
                        <button type="button" className="danger" onClick={() => { editor?.chain().focus().deleteTable().run(); setTableMenuOpen(false); }}>
                          Delete Table
                        </button>
                      </>
                    )}
                  </div>
                ) : null}
              </div>
              {hasSelection && onCreateComment ? (
                <>
                  <span className="toolbar-sep" />
                  <button
                    type="button"
                    className="ghost docs-action-btn"
                    onClick={handleStartComment}
                    title="Add Comment"
                  >
                    <FontAwesomeIcon icon={faComment} /> Comment
                  </button>
                </>
              ) : null}
            </>
          ) : null}
        </div>
      </div>

      {commentingActive && mode === "write" ? (
        <div className="proposal-comment-input-bar">
          <input
            type="text"
            placeholder="Type your comment..."
            value={commentInput}
            onChange={(e) => setCommentInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmitComment();
              if (e.key === "Escape") { setCommentingActive(false); setCommentInput(""); }
            }}
            autoFocus
          />
          <button type="button" onClick={handleSubmitComment} disabled={!commentInput.trim()}>Add</button>
          <button type="button" className="ghost" onClick={() => { setCommentingActive(false); setCommentInput(""); }}>Cancel</button>
        </div>
      ) : null}

      {presenceUsers.length > 0 ? (
        <div className="proposal-collab-presence" aria-label="Editors">
          {presenceUsers.map((user) => (
            <div
              key={user.clientId}
              className={`proposal-collab-presence-user ${user.isCurrentUser ? "current" : ""}`}
              style={{ "--collab-color": user.color } as CSSProperties}
            >
              <span className="proposal-collab-presence-dot" />
              <span className="proposal-collab-presence-name">{user.isCurrentUser ? `${user.name} (you)` : user.name}</span>
            </div>
          ))}
        </div>
      ) : null}

      {mode === "write" ? (
        <div className="proposal-editor-write-layout">
          <div className="proposal-editor-main">
            <div className="proposal-editor-stage" onClickCapture={handleEditorStageClick}>
              <EditorContent editor={editor} />
            </div>
          </div>
          {anchoredFindings.length > 0 ? (
            <aside className="proposal-comment-rail">
              {anchoredFindings.map((finding) => (
                <div
                  key={finding.id}
                  className={`proposal-comment-balloon ${finding.finding_type} ${finding.id === activeFindingId ? "active" : ""}`}
                  onClick={() => jumpToFinding(finding)}
                >
                  <div className="proposal-comment-header">
                    <span className="proposal-comment-author">
                      {finding.created_by_display_name || (finding.source === "assistant" ? "AI Review" : "You")}
                    </span>
                    <span className="proposal-comment-time">{relativeTime(finding.created_at)}</span>
                  </div>
                  <strong>{finding.summary}</strong>
                  {finding.anchor_text ? <span>{finding.anchor_text}</span> : null}
                  {finding.replies && finding.replies.length > 0 ? (
                    <div className="proposal-comment-replies">
                      {finding.replies.map((reply) => (
                        <div key={reply.id} className="proposal-comment-reply">
                          <span className="proposal-comment-author">
                            {reply.created_by_display_name || "You"}
                          </span>
                          <span className="proposal-comment-time">{relativeTime(reply.created_at)}</span>
                          <span>{reply.summary}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {replyingToId === finding.id ? (
                    <div className="proposal-comment-reply-input">
                      <input
                        type="text"
                        placeholder="Reply..."
                        value={replyInput}
                        onChange={(e) => setReplyInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSubmitReply();
                          if (e.key === "Escape") { setReplyingToId(null); setReplyInput(""); }
                        }}
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                      />
                      <button type="button" onClick={(e) => { e.stopPropagation(); handleSubmitReply(); }} disabled={!replyInput.trim()}>Send</button>
                    </div>
                  ) : null}
                  <div className="proposal-comment-actions">
                    {onReplyToFinding ? (
                      <button
                        type="button"
                        className="ghost tiny"
                        onClick={(e) => { e.stopPropagation(); setReplyingToId(finding.id); setReplyInput(""); }}
                        title="Reply"
                      >
                        <FontAwesomeIcon icon={faReply} /> Reply
                      </button>
                    ) : null}
                    {finding.finding_type === "comment" && onDeleteFinding ? (
                      <button
                        type="button"
                        className="ghost tiny danger"
                        onClick={(e) => { e.stopPropagation(); onDeleteFinding(finding.id); }}
                        title="Dismiss"
                      >
                        <FontAwesomeIcon icon={faTrash} /> Dismiss
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
            </aside>
          ) : null}
        </div>
      ) : null}

      {mode === "markdown" ? (
        <div className="proposal-editor-stage">
          <textarea
            className="proposal-markdown-input"
            value={value}
            onChange={(event) => {
              const nextValue = event.target.value;
              onChange(nextValue, { remote: false });
              if (editor) {
                editor.commands.setContent(nextValue, { contentType: "markdown" });
              }
            }}
            placeholder={placeholder}
          />
        </div>
      ) : null}

      {mode === "preview" ? (
        <div className="proposal-editor-stage proposal-editor-preview chat-markdown">
          {value.trim() ? renderMarkdown(value) : <p>No content</p>}
        </div>
      ) : null}
    </div>
  );
}
