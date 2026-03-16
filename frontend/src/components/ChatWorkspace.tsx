import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowTrendUp,
  faBolt,
  faBookOpen,
  faCalendarCheck,
  faChartPie,
  faCheck,
  faClipboardList,
  faClockRotateLeft,
  faComments,
  faCopy,
  faMagnifyingGlass,
  faPaperPlane,
  faPen,
  faPlus,
  faRobot,
  faTrash,
  faTriangleExclamation,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { currentProjectMonth } from "../lib/utils";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type {
  AuditEvent,
  ChatConversation,
  ChatMessage,
  DocumentListItem,
  Project,
  ProjectRisk,
  ProjectValidationResult,
  WorkEntity,
} from "../types";

type Props = {
  selectedProjectId: string;
  project: Project | null;
  onNavigate?: (view: string, entityId?: string) => void;
};

const ASSISTANT_PENDING_PROMPT_KEY = "assistant_pending_prompt";

type FocusItem = {
  tone: "danger" | "warning" | "neutral";
  label: string;
};

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(text.slice(cursor, start));
    }
    if (match[2] && match[3]) {
      nodes.push(
        <a key={`assistant-md-${key++}`} href={match[3]} target="_blank" rel="noreferrer">
          {match[2]}
        </a>
      );
    } else if (match[4]) {
      nodes.push(<strong key={`assistant-md-${key++}`}>{match[4]}</strong>);
    } else if (match[5]) {
      nodes.push(<em key={`assistant-md-${key++}`}>{match[5]}</em>);
    } else if (match[6]) {
      nodes.push(<code key={`assistant-md-${key++}`}>{match[6]}</code>);
    }
    cursor = start + match[0].length;
  }
  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

function renderMarkdown(content: string): ReactNode[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const output: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (line.trim().startsWith("```")) {
      i += 1;
      const codeLines: string[] = [];
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      output.push(
        <pre key={`assistant-md-block-${key++}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      if (level === 1) output.push(<h1 key={`assistant-md-block-${key++}`}>{renderInlineMarkdown(text)}</h1>);
      else if (level === 2) output.push(<h2 key={`assistant-md-block-${key++}`}>{renderInlineMarkdown(text)}</h2>);
      else output.push(<h3 key={`assistant-md-block-${key++}`}>{renderInlineMarkdown(text)}</h3>);
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(<li key={`assistant-md-li-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^[-*]\s+/, ""))}</li>);
        i += 1;
      }
      output.push(<ul key={`assistant-md-block-${key++}`}>{items}</ul>);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(<li key={`assistant-md-oli-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^\d+\.\s+/, ""))}</li>);
        i += 1;
      }
      output.push(<ol key={`assistant-md-block-${key++}`}>{items}</ol>);
      continue;
    }

    const paragraphLines: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith("```")
    ) {
      paragraphLines.push(lines[i]);
      i += 1;
    }
    output.push(<p key={`assistant-md-block-${key++}`}>{renderInlineMarkdown(paragraphLines.join(" "))}</p>);
  }

  return output;
}

function relativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString([], { day: "2-digit", month: "short" });
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
}

export function ChatWorkspace({ selectedProjectId, project, onNavigate }: Props) {
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [validation, setValidation] = useState<ProjectValidationResult | null>(null);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);
  const [risks, setRisks] = useState<ProjectRisk[]>([]);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [activity, setActivity] = useState<AuditEvent[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingMessageId, setGeneratingMessageId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useAutoRefresh(() => {
    if (selectedProjectId) void loadConversations(selectedProjectId);
  });

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId]
  );
  const projectMonth = useMemo(() => currentProjectMonth(project?.start_date), [project?.start_date]);
  const indexedDocuments = useMemo(() => documents.filter((item) => item.status === "indexed").length, [documents]);
  const openRisks = useMemo(() => risks.filter((item) => item.status !== "closed"), [risks]);
  const highRisks = useMemo(
    () => risks.filter((item) => ["high", "critical"].includes(item.probability) || ["high", "critical"].includes(item.impact)),
    [risks]
  );
  const reviewGaps = useMemo(
    () =>
      deliverables.filter(
        (item) =>
          !item.review_owner_member_id ||
          !item.review_due_month ||
          (projectMonth !== null && item.review_due_month !== null && item.review_due_month < projectMonth)
      ),
    [deliverables, projectMonth]
  );
  const nextReportingDate = useMemo(() => {
    if (!project?.reporting_dates?.length) return "-";
    const dates = project.reporting_dates
      .map((item) => new Date(item))
      .filter((item) => !Number.isNaN(item.getTime()))
      .sort((a, b) => a.getTime() - b.getTime());
    const now = new Date();
    const next = dates.find((item) => item >= now) || dates[0];
    return next ? next.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" }) : "-";
  }, [project]);
  const focusItems = useMemo<FocusItem[]>(() => {
    const rows: FocusItem[] = [];
    (validation?.errors || []).slice(0, 2).forEach((item) => rows.push({ tone: "danger", label: item.message }));
    reviewGaps.slice(0, 2).forEach((item) => rows.push({ tone: "warning", label: `${item.code} review gap` }));
    highRisks.slice(0, 2).forEach((item) => rows.push({ tone: "danger", label: `${item.code} ${item.title}` }));
    activity.slice(0, 2).forEach((item) => {
      const code = String(item.after_json?.code || item.before_json?.code || item.entity_type);
      rows.push({ tone: "neutral", label: `${item.actor_name || "System"} · ${code}` });
    });
    return rows.slice(0, 6);
  }, [activity, highRisks, reviewGaps, validation]);

  const quickActions = useMemo(
    () => [
      {
        label: "Brief",
        description: "Project overview & status",
        icon: faClipboardList,
        prompt: "Prepare a project brief covering structure, open risks, review gaps, upcoming outputs, and the next reporting date.",
      },
      {
        label: "Reporting",
        description: "Reporting period snapshot",
        icon: faChartPie,
        prompt: "Prepare a reporting snapshot for the next reporting date using the current project structure, risks, activity, and indexed documents.",
      },
      {
        label: "Delays",
        description: "At-risk items & actions",
        icon: faCalendarCheck,
        prompt: "List delayed or at-risk deliverables, milestones, and reviews. Explain why and propose concrete actions.",
      },
      {
        label: "Review",
        description: "Review gaps & assignments",
        icon: faMagnifyingGlass,
        prompt: "Find deliverables with missing reviewers or weak review planning and propose assignments or due-month adjustments.",
      },
      {
        label: "Changes",
        description: "Recent activity impact",
        icon: faClockRotateLeft,
        prompt: "Summarize the most important recent project changes and explain their impact on delivery and reporting.",
      },
      {
        label: "Meeting",
        description: "Draft meeting agenda",
        icon: faBookOpen,
        prompt: "Draft a short project meeting agenda based on open risks, review gaps, upcoming outputs, and recent activity.",
      },
    ],
    []
  );

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  useEffect(() => {
    if (!selectedProjectId) {
      setConversations([]);
      setSelectedConversationId("");
      setMessages([]);
      setValidation(null);
      setDeliverables([]);
      setRisks([]);
      setDocuments([]);
      setActivity([]);
      setError("");
      return;
    }
    void loadConversations(selectedProjectId);
    void loadAssistantOverview(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || !selectedConversationId) {
      setMessages([]);
      return;
    }
    void loadMessages(selectedProjectId, selectedConversationId);
  }, [selectedProjectId, selectedConversationId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    if (typeof window === "undefined") return;
    const pending = window.sessionStorage.getItem(ASSISTANT_PENDING_PROMPT_KEY);
    if (!pending || sending || generating) return;
    window.sessionStorage.removeItem(ASSISTANT_PENDING_PROMPT_KEY);
    void handleSendMessage(pending);
  }, [selectedConversationId, selectedProjectId]);

  async function loadConversations(projectId: string) {
    try {
      setLoading(true);
      setError("");
      const response = await api.listChatConversations(projectId);
      setConversations(response.items);
      setSelectedConversationId((current) => {
        if (current && response.items.some((item) => item.id === current)) return current;
        return response.items[0]?.id ?? "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations.");
    } finally {
      setLoading(false);
    }
  }

  async function loadMessages(projectId: string, conversationId: string) {
    try {
      setLoading(true);
      setError("");
      const response = await api.listChatMessages(projectId, conversationId);
      setMessages(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages.");
    } finally {
      setLoading(false);
    }
  }

  async function loadAssistantOverview(projectId: string) {
    try {
      const [validationRes, deliverablesRes, risksRes, documentsRes, activityRes] = await Promise.all([
        api.validateProject(projectId),
        api.listDeliverables(projectId),
        api.listRisks(projectId),
        api.listDocuments(projectId),
        api.listActivity(projectId, 1, 8),
      ]);
      setValidation(validationRes);
      setDeliverables(deliverablesRes.items);
      setRisks(risksRes.items);
      setDocuments(documentsRes.items);
      setActivity(activityRes.items);
    } catch {
      // Sidebar data is non-blocking.
    }
  }

  async function handleNewConversation() {
    if (!selectedProjectId) return;
    try {
      setLoading(true);
      setError("");
      const created = await api.createChatConversation(selectedProjectId, { title: "New conversation" });
      setConversations((prev) => [created, ...prev]);
      setSelectedConversationId(created.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create conversation.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendMessage(overrideText?: string) {
    const prompt = (overrideText ?? draft).trim();
    if (!selectedProjectId || !prompt || sending) return;
    try {
      setSending(true);
      setError("");
      let conversationId = selectedConversationId;
      if (!conversationId) {
        const created = await api.createChatConversation(selectedProjectId, { title: "New conversation" });
        setConversations((prev) => [created, ...prev]);
        setSelectedConversationId(created.id);
        conversationId = created.id;
      }

      const tempUserId = `temp-user-${Date.now()}`;
      const tempAssistantId = `temp-assistant-${Date.now()}`;
      const nowIso = new Date().toISOString();
      const tempUserMessage: ChatMessage = {
        id: tempUserId,
        conversation_id: conversationId,
        project_id: selectedProjectId,
        role: "user",
        content: prompt,
        citations: [],
        cards: [],
        created_by_member_id: null,
        created_at: nowIso,
        updated_at: nowIso,
      };
      const tempAssistantMessage: ChatMessage = {
        id: tempAssistantId,
        conversation_id: conversationId,
        project_id: selectedProjectId,
        role: "assistant",
        content: "",
        citations: [],
        cards: [],
        created_by_member_id: null,
        created_at: nowIso,
        updated_at: nowIso,
      };
      setMessages((prev) => [...prev, tempUserMessage, tempAssistantMessage]);
      if (!overrideText) setDraft("");

      await api.postChatMessageStream(
        selectedProjectId,
        conversationId,
        { content: prompt },
        {
          onStart: () => {
            setGenerating(true);
            setGeneratingMessageId(tempAssistantId);
          },
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((item) => (item.id === tempAssistantId ? { ...item, content: `${item.content}${token}` } : item))
            );
          },
          onDone: (exchange) => {
            setMessages((prev) =>
              prev.map((item) => {
                if (item.id === tempUserId) return exchange.user_message;
                if (item.id === tempAssistantId) return exchange.assistant_message;
                return item;
              })
            );
            setGenerating(false);
            setGeneratingMessageId(null);
            void loadAssistantOverview(selectedProjectId);
          },
          onError: (detail) => {
            setGenerating(false);
            setGeneratingMessageId(null);
            setError(detail);
            setMessages((prev) =>
              prev.map((item) =>
                item.id === tempAssistantId ? { ...item, content: "Failed to generate response." } : item
              )
            );
          },
        }
      );
      await loadConversations(selectedProjectId);
    } catch (err) {
      setGenerating(false);
      setGeneratingMessageId(null);
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSendMessage();
    }
  }

  async function handleCopyMessage(messageId: string, content: string) {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 1500);
    } catch { /* ignore */ }
  }

  async function handleRenameConversation(conversationId: string, newTitle: string) {
    if (!selectedProjectId || !newTitle.trim()) return;
    try {
      await api.updateConversation(selectedProjectId, conversationId, { title: newTitle.trim() });
      setConversations((prev) => prev.map((item) => item.id === conversationId ? { ...item, title: newTitle.trim() } : item));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rename conversation.");
    } finally {
      setRenamingConversationId(null);
    }
  }

  async function handleDeleteConversation(conversationId: string) {
    if (!selectedProjectId) return;
    try {
      await api.deleteConversation(selectedProjectId, conversationId);
      setConversations((prev) => prev.filter((item) => item.id !== conversationId));
      if (selectedConversationId === conversationId) {
        const remaining = conversations.filter((item) => item.id !== conversationId);
        setSelectedConversationId(remaining[0]?.id ?? "");
        setMessages([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete conversation.");
    }
  }

  const hasMessages = messages.length > 0;
  const isBusy = sending || generating;

  if (!selectedProjectId) {
    return (
      <section className="panel chat-panel">
        <p className="muted-small">Select a project to start.</p>
      </section>
    );
  }

  return (
    <section className="panel chat-panel">
      {error ? <p className="error">{error}</p> : null}

      <div className="chat-layout assistant-layout">
        {/* ─── Thread Sidebar ─── */}
        <aside className="card chat-conversations">
          <div className="workpane-head">
            <h3>Threads</h3>
            <button type="button" className="ghost icon-only" onClick={() => void handleNewConversation()} disabled={loading} title="New thread">
              <FontAwesomeIcon icon={faPlus} />
            </button>
          </div>
          <div className="chat-conversation-list">
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={`chat-conversation-item ${conversation.id === selectedConversationId ? "active" : ""}`}
              >
                {renamingConversationId === conversation.id ? (
                  <input
                    className="chat-rename-input"
                    value={renameTitle}
                    onChange={(e) => setRenameTitle(e.target.value)}
                    onBlur={() => void handleRenameConversation(conversation.id, renameTitle)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void handleRenameConversation(conversation.id, renameTitle);
                      if (e.key === "Escape") setRenamingConversationId(null);
                    }}
                    autoFocus
                  />
                ) : (
                  <button
                    type="button"
                    className="chat-conversation-btn"
                    onClick={() => setSelectedConversationId(conversation.id)}
                    onDoubleClick={() => {
                      setRenamingConversationId(conversation.id);
                      setRenameTitle(conversation.title);
                    }}
                  >
                    <strong>{conversation.title}</strong>
                    <span>{relativeTime(conversation.updated_at)}</span>
                  </button>
                )}
                <button
                  type="button"
                  className="ghost icon-only chat-thread-delete"
                  title="Delete thread"
                  onClick={(e) => { e.stopPropagation(); void handleDeleteConversation(conversation.id); }}
                >
                  <FontAwesomeIcon icon={faTrash} />
                </button>
              </div>
            ))}
            {conversations.length === 0 ? (
              <div className="chat-empty-threads">
                <FontAwesomeIcon icon={faComments} />
                <span>No threads yet</span>
              </div>
            ) : null}
          </div>
        </aside>

        {/* ─── Main Chat Area ─── */}
        <section className="card chat-thread">
          {hasMessages ? (
            <div className="chat-thread-head">
              <span className="chat-thread-title">{selectedConversation?.title || "New conversation"}</span>
              <span className="chat-thread-meta">{messages.length} messages</span>
            </div>
          ) : null}

          <div className="chat-messages">
            {hasMessages ? (
              <>
                {messages.map((message) => (
                  <article key={message.id} className={`chat-message ${message.role}`}>
                    {message.role === "assistant" ? (
                      <div className="chat-message-avatar">
                        <FontAwesomeIcon icon={faRobot} />
                      </div>
                    ) : null}
                    <div className="chat-message-body">
                      {message.role === "assistant" ? (
                        <div className="chat-markdown">
                          {renderMarkdown(message.content)}
                          {message.content ? (
                            <button
                              type="button"
                              className="chat-copy-btn"
                              title="Copy"
                              onClick={() => void handleCopyMessage(message.id, message.content)}
                            >
                              <FontAwesomeIcon icon={copiedMessageId === message.id ? faCheck : faCopy} />
                            </button>
                          ) : null}
                        </div>
                      ) : (
                        <p>{message.content}</p>
                      )}
                      {message.id === generatingMessageId && !message.content ? (
                        <div className="chat-typing-indicator">
                          <span /><span /><span />
                        </div>
                      ) : null}
                      {message.id === generatingMessageId && message.content ? (
                        <div className="chat-generating">
                          <span className="chat-generating-dot" />
                          Generating...
                        </div>
                      ) : null}
                      {message.role === "assistant" && message.content ? (
                        <ProposalActions content={message.content} onCommand={(command) => void handleSendMessage(command)} busy={isBusy} />
                      ) : null}
                      {message.role === "assistant" && message.cards.length > 0 ? (
                        <div className="chat-card-grid">
                          {message.cards.map((card, index) => (
                            <button
                              key={`${message.id}-card-${index}`}
                              type="button"
                              className="chat-result-card"
                              disabled={isBusy || !card.action_prompt}
                              onClick={() => card.action_prompt && void handleSendMessage(card.action_prompt)}
                            >
                              <strong>{card.title}</strong>
                              <span>{card.body}</span>
                              {card.action_label ? <em>{card.action_label}</em> : null}
                            </button>
                          ))}
                        </div>
                      ) : null}
                      {message.role !== "user" && message.citations.length > 0 ? (
                        <ul className="chat-citations">
                          {message.citations.map((citation) => (
                            <li key={`${message.id}-${citation.document_id}-${citation.chunk_index}`}>
                              <button
                                type="button"
                                className="chat-citation-link"
                                onClick={() => {
                                  if (onNavigate) {
                                    if (citation.source_type === "meeting") {
                                      onNavigate("meetings", citation.document_id);
                                    } else {
                                      onNavigate("documents", citation.document_key);
                                    }
                                  }
                                }}
                              >
                                <strong>
                                  {citation.title}{citation.source_type === "meeting" ? " · meeting" : ` · v${citation.version} · chunk ${citation.chunk_index}`}
                                </strong>
                              </button>
                              <span>{citation.snippet}</span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <span className="chat-message-time" title={formatTimestamp(message.created_at)}>
                        {relativeTime(message.created_at)}
                      </span>
                    </div>
                  </article>
                ))}
                <div ref={messagesEndRef} />
              </>
            ) : (
              <div className="chat-welcome">
                <div className="chat-welcome-header">
                  <div className="chat-welcome-icon">
                    <FontAwesomeIcon icon={faBolt} />
                  </div>
                  <h3>Project Assistant</h3>
                  <p>Ask questions about your project, generate reports, or get actionable insights.</p>
                </div>
                <div className="chat-welcome-actions">
                  {quickActions.map((item) => (
                    <button
                      key={item.label}
                      type="button"
                      className="chat-welcome-action"
                      disabled={isBusy}
                      onClick={() => void handleSendMessage(item.prompt)}
                    >
                      <span className="chat-welcome-action-icon">
                        <FontAwesomeIcon icon={item.icon} />
                      </span>
                      <div className="chat-welcome-action-text">
                        <strong>{item.label}</strong>
                        <span>{item.description}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="chat-composer">
            <div className="chat-composer-inner">
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleDraftKeyDown}
                placeholder="Ask about reporting, delays, risks, documents..."
                disabled={isBusy}
                rows={1}
              />
              <button
                type="button"
                className="chat-send-btn"
                onClick={() => void handleSendMessage()}
                disabled={!draft.trim() || isBusy}
                title="Send message (Enter)"
              >
                <FontAwesomeIcon icon={faPaperPlane} />
              </button>
            </div>
            <span className="chat-composer-hint">Enter to send · Shift+Enter for new line</span>
          </div>
        </section>

        {/* ─── Context Sidebar ─── */}
        <aside className="card assistant-sidebar">
          <div className="assistant-side-section">
            <h4 className="assistant-section-title">Brief</h4>
            <div className="assistant-brief-grid">
              <div className="assistant-brief-cell">
                <span>Month</span>
                <strong>{projectMonth ? `M${projectMonth}` : "-"}</strong>
              </div>
              <div className="assistant-brief-cell">
                <span>Next Report</span>
                <strong>{nextReportingDate}</strong>
              </div>
              <div className="assistant-brief-cell">
                <span>Open Risks</span>
                <strong className={openRisks.length > 0 ? "has-issues" : ""}>{openRisks.length}</strong>
              </div>
              <div className="assistant-brief-cell">
                <span>Review Gaps</span>
                <strong className={reviewGaps.length > 0 ? "has-issues" : ""}>{reviewGaps.length}</strong>
              </div>
              <div className="assistant-brief-cell">
                <span>Indexed Docs</span>
                <strong>{indexedDocuments}</strong>
              </div>
              <div className="assistant-brief-cell">
                <span>Deliverables</span>
                <strong>{deliverables.length}</strong>
              </div>
            </div>
          </div>

          {hasMessages ? (
            <div className="assistant-side-section">
              <h4 className="assistant-section-title">Quick Actions</h4>
              <div className="assistant-action-grid">
                {quickActions.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    className="assistant-action-card"
                    disabled={isBusy}
                    onClick={() => void handleSendMessage(item.prompt)}
                    title={item.description}
                  >
                    <span className="assistant-action-icon"><FontAwesomeIcon icon={item.icon} /></span>
                    <strong>{item.label}</strong>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {focusItems.length > 0 ? (
            <div className="assistant-side-section">
              <h4 className="assistant-section-title">Focus</h4>
              <div className="assistant-focus-list">
                {focusItems.map((item, index) => (
                  <div key={`${item.label}-${index}`} className={`assistant-focus-item ${item.tone}`}>
                    <span className="assistant-focus-icon">
                      <FontAwesomeIcon icon={item.tone === "neutral" ? faArrowTrendUp : faTriangleExclamation} />
                    </span>
                    <strong>{item.label}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function ProposalActions({
  content,
  onCommand,
  busy,
}: {
  content: string;
  onCommand: (command: string) => void;
  busy: boolean;
}) {
  const match = content.match(/proposal id:\s*([0-9a-f-]{36})/i);
  if (!match) return null;
  const proposalId = match[1];
  return (
    <div className="chat-proposal-actions">
      <button type="button" className="ghost" disabled={busy} onClick={() => onCommand(`confirm ${proposalId}`)}>
        Confirm
      </button>
      <button type="button" className="ghost" disabled={busy} onClick={() => onCommand(`cancel ${proposalId}`)}>
        Cancel
      </button>
    </div>
  );
}
