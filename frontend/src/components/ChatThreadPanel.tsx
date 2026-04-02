import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faFaceSmile, faPaperPlane, faReply } from "@fortawesome/free-solid-svg-icons";
import { useEffect, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";

import type { AuthUser } from "../types";

type ChatReaction = {
  emoji: string;
  count: number;
  user_ids: string[];
};

type ChatReplyPreview = {
  id: string;
  sender_user_id: string;
  sender_display_name: string;
  content: string;
};

export type ChatThreadMessage = {
  id: string;
  sender_user_id: string;
  sender_display_name: string;
  content: string;
  reply_to_message: ChatReplyPreview | null;
  reactions: ChatReaction[];
  created_at: string;
};

export type ChatParticipant = {
  id: string;
  name: string;
  subtitle?: string | null;
  avatarUrl?: string | null;
};

export type ChatComposerSuggestion = {
  id: string;
  token: string;
  label: string;
  sublabel?: string;
  insertText: string;
  prefix?: string;
};

type ChatStreamMessage = {
  id: string;
  label: string;
  content: string;
};

type Props = {
  title?: string | null;
  showHeader?: boolean;
  hideParticipants?: boolean;
  headerActions?: ReactNode;
  error?: string;
  loading?: boolean;
  emptyMessage?: string;
  currentUser: AuthUser;
  currentUserMentionTokens: Set<string>;
  messages: ChatThreadMessage[];
  streamMessages?: ChatStreamMessage[];
  participants: ChatParticipant[];
  onlineUserIds: string[];
  draft: string;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  threadEndRef: RefObject<HTMLDivElement | null>;
  replyToMessage: ChatThreadMessage | null;
  reactionPickerMessageId: string | null;
  showEmojiPicker: boolean;
  assistOpen: boolean;
  assistSuggestions: ChatComposerSuggestion[];
  assistIndex: number;
  sendDisabled: boolean;
  messageDomIdPrefix: string;
  onDraftChange: (value: string, cursorPosition: number) => void;
  onDraftCursorActivity: (value: string, cursorPosition: number) => void;
  onDraftKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onDraftBlur: () => void;
  onSend: () => void | Promise<void>;
  onReply: (message: ChatThreadMessage) => void;
  onClearReply: () => void;
  onToggleReactionPicker: (messageId: string) => void;
  onToggleReaction: (messageId: string, emoji: string) => void | Promise<void>;
  onToggleEmojiPicker: () => void;
  onInsertEmoji: (emoji: string) => void;
  onApplySuggestion: (suggestion: ChatComposerSuggestion) => void;
};

const EMOJIS = [
  "😀", "😁", "😂", "🤣", "😊", "😍", "😘", "😎", "🤔", "🙌",
  "👍", "👎", "👏", "🙏", "💡", "🔥", "🎯", "✅", "❌", "⚠️",
  "📌", "📎", "📅", "📊", "🧪", "💬", "🧠", "🚀", "🎉", "💼",
];

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function initials(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "");
  const value = parts.join("");
  return value || "U";
}

function excerpt(text: string, max = 96): string {
  const normalized = (text || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1).trimEnd()}…`;
}

function extractMentionTokens(content: string): Set<string> {
  const tokens = new Set<string>();
  const pattern = /(^|[^A-Za-z0-9._:-])@([A-Za-z0-9._:-]+)/g;
  for (const match of content.matchAll(pattern)) {
    const token = match[2]?.trim().toLowerCase();
    if (token) tokens.add(token);
  }
  return tokens;
}

function renderMentionText(text: string, currentUserTokens: Set<string>): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(^|[^A-Za-z0-9._:-])(@[A-Za-z0-9._:-]+|https?:\/\/[^\s<]+)/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    const prefix = match[1] || "";
    const token = match[2] || "";
    const tokenStart = start + prefix.length;
    if (tokenStart > cursor) {
      nodes.push(text.slice(cursor, tokenStart));
    }
    if (token.startsWith("@")) {
      const mentionToken = token.slice(1).toLowerCase();
      nodes.push(
        <span
          key={`mention-${key++}`}
          className={`pm-mention ${currentUserTokens.has(mentionToken) ? "self" : ""}`}
        >
          {token}
        </span>
      );
    } else {
      nodes.push(
        <a key={`link-${key++}`} href={token} target="_blank" rel="noreferrer">
          {token}
        </a>
      );
    }
    cursor = tokenStart + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

function renderInlineMarkdown(text: string, currentUserTokens: Set<string>): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  let cursor = 0;
  let key = 0;

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(...renderMentionText(text.slice(cursor, start), currentUserTokens));
    }
    if (match[2] && match[3]) {
      nodes.push(
        <a key={`md-${key++}`} href={match[3]} target="_blank" rel="noreferrer">
          {match[2]}
        </a>
      );
    } else if (match[4]) {
      nodes.push(<strong key={`md-${key++}`}>{match[4]}</strong>);
    } else if (match[5]) {
      nodes.push(<em key={`md-${key++}`}>{match[5]}</em>);
    } else if (match[6]) {
      nodes.push(<code key={`md-${key++}`}>{match[6]}</code>);
    }
    cursor = start + match[0].length;
  }

  if (cursor < text.length) {
    nodes.push(...renderMentionText(text.slice(cursor), currentUserTokens));
  }
  return nodes;
}

function renderMarkdown(content: string, currentUserTokens: Set<string>): ReactNode[] {
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
        <pre key={`md-block-${key++}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      if (level === 1) output.push(<h1 key={`md-block-${key++}`}>{renderInlineMarkdown(text, currentUserTokens)}</h1>);
      else if (level === 2) output.push(<h2 key={`md-block-${key++}`}>{renderInlineMarkdown(text, currentUserTokens)}</h2>);
      else output.push(<h3 key={`md-block-${key++}`}>{renderInlineMarkdown(text, currentUserTokens)}</h3>);
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(<li key={`md-li-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^[-*]\s+/, ""), currentUserTokens)}</li>);
        i += 1;
      }
      output.push(<ul key={`md-block-${key++}`}>{items}</ul>);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(<li key={`md-oli-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^\d+\.\s+/, ""), currentUserTokens)}</li>);
        i += 1;
      }
      output.push(<ol key={`md-block-${key++}`}>{items}</ol>);
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
    output.push(<p key={`md-block-${key++}`}>{renderInlineMarkdown(paragraphLines.join(" "), currentUserTokens)}</p>);
  }

  return output;
}

function ChatAvatar({ name, avatarUrl, small = false }: { name: string; avatarUrl?: string | null; small?: boolean }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [avatarUrl]);

  return (
    <span className={`pm-avatar-badge${small ? " small" : ""}`}>
      {avatarUrl && !failed ? (
        <img src={avatarUrl} alt={name} onError={() => setFailed(true)} />
      ) : (
        initials(name)
      )}
    </span>
  );
}

export function ChatThreadPanel({
  title = "Chat",
  showHeader = true,
  hideParticipants = false,
  headerActions = null,
  error = "",
  loading = false,
  emptyMessage = "No messages yet.",
  currentUser,
  currentUserMentionTokens,
  messages,
  streamMessages = [],
  participants,
  onlineUserIds,
  draft,
  composerRef,
  threadEndRef,
  replyToMessage,
  reactionPickerMessageId,
  showEmojiPicker,
  assistOpen,
  assistSuggestions,
  assistIndex,
  sendDisabled,
  messageDomIdPrefix,
  onDraftChange,
  onDraftCursorActivity,
  onDraftKeyDown,
  onDraftBlur,
  onSend,
  onReply,
  onClearReply,
  onToggleReactionPicker,
  onToggleReaction,
  onToggleEmojiPicker,
  onInsertEmoji,
  onApplySuggestion,
}: Props) {
  const onlineSet = new Set(onlineUserIds);
  const onlineParticipants = participants.filter((item) => onlineSet.has(item.id));
  const offlineParticipants = participants.filter((item) => !onlineSet.has(item.id));

  return (
    <div className="pm-chat-layout study-chat-layout">
      <section className="card pm-thread study-chat-thread">
        {showHeader ? (
          <div className="workpane-head">
            <h3>{title}</h3>
            {headerActions}
          </div>
        ) : null}
        {error ? <p className="error">{error}</p> : null}

        <div className="pm-messages">
          {loading ? <p className="muted-small">Loading…</p> : null}
          {!loading && messages.length === 0 && streamMessages.length === 0 ? <p className="muted-small">{emptyMessage}</p> : null}
          {messages.map((message) => {
            const own = message.sender_user_id === currentUser.id;
            const mentionTokens = extractMentionTokens(message.content);
            const mentionsCurrentUser = Array.from(currentUserMentionTokens).some((token) => mentionTokens.has(token));
            const senderName = own ? "You" : message.sender_display_name;
            const sender = participants.find((item) => item.id === message.sender_user_id) ?? null;
            const replyPreview = message.reply_to_message;
            return (
              <article
                id={`${messageDomIdPrefix}-${message.id}`}
                key={message.id}
                className={`pm-message-row ${own ? "own" : "other"} ${mentionsCurrentUser ? "mentioned" : ""}`}
              >
                <ChatAvatar name={senderName} avatarUrl={sender?.avatarUrl} small />
                <div className={`pm-message-bubble ${own ? "own" : "other"} ${mentionsCurrentUser ? "mentioned" : ""}`}>
                  <div className="pm-message-head">
                    <strong>{senderName}</strong>
                    <span>{formatTimestamp(message.created_at)}</span>
                  </div>
                  {replyPreview ? (
                    <button
                      type="button"
                      className="pm-reply-preview"
                      onClick={() => {
                        const row = document.getElementById(`${messageDomIdPrefix}-${replyPreview.id}`);
                        row?.scrollIntoView({ behavior: "smooth", block: "center" });
                      }}
                    >
                      <strong>{replyPreview.sender_user_id === currentUser.id ? "You" : replyPreview.sender_display_name}</strong>
                      <span>{excerpt(replyPreview.content)}</span>
                    </button>
                  ) : null}
                  <div className="chat-markdown">{renderMarkdown(message.content, currentUserMentionTokens)}</div>
                  {message.reactions.length > 0 ? (
                    <div className="pm-reactions">
                      {message.reactions.map((reaction) => {
                        const mine = reaction.user_ids.includes(currentUser.id);
                        return (
                          <button
                            key={`${message.id}-${reaction.emoji}`}
                            type="button"
                            className={`pm-reaction-chip ${mine ? "mine" : ""}`}
                            onClick={() => void onToggleReaction(message.id, reaction.emoji)}
                          >
                            <span>{reaction.emoji}</span>
                            <strong>{reaction.count}</strong>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  <div className="pm-message-actions">
                    <button type="button" className="ghost icon-only" onClick={() => onReply(message)} aria-label="Reply">
                      <FontAwesomeIcon icon={faReply} />
                    </button>
                    <button
                      type="button"
                      className="ghost icon-only"
                      onClick={() => onToggleReactionPicker(message.id)}
                      aria-label="Add reaction"
                    >
                      <FontAwesomeIcon icon={faFaceSmile} />
                    </button>
                  </div>
                  {reactionPickerMessageId === message.id ? (
                    <div className="pm-reaction-picker">
                      {EMOJIS.slice(0, 16).map((emoji) => (
                        <button
                          key={`${message.id}-reaction-${emoji}`}
                          type="button"
                          onMouseDown={(event) => {
                            event.preventDefault();
                            void onToggleReaction(message.id, emoji);
                          }}
                        >
                          {emoji}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}

          {streamMessages.map((stream) => (
            <article key={stream.id} className="pm-message-row other">
              <ChatAvatar name="Project Bot" small />
              <div className="pm-message-bubble other bot-stream-message">
                <div className="pm-message-head">
                  <strong>{stream.label}</strong>
                  <span className="bot-thinking" aria-live="polite">
                    <span>Thinking</span>
                    <span className="bot-thinking-dots" aria-hidden="true">
                      <span>.</span>
                      <span>.</span>
                      <span>.</span>
                    </span>
                  </span>
                </div>
                <div className="chat-markdown">{renderMarkdown(stream.content || "Thinking", currentUserMentionTokens)}</div>
              </div>
            </article>
          ))}
          <div ref={threadEndRef as RefObject<HTMLDivElement>} />
        </div>

        <div className="pm-composer">
          <div className="pm-composer-main">
            <button
              type="button"
              className="ghost icon-only"
              aria-label="Add emoji"
              onClick={onToggleEmojiPicker}
            >
              <FontAwesomeIcon icon={faFaceSmile} />
            </button>

            <div className="composer-input-wrap">
              {replyToMessage ? (
                <div className="pm-composer-reply">
                  <div className="pm-composer-reply-meta">
                    <strong>Replying to {replyToMessage.sender_user_id === currentUser.id ? "you" : replyToMessage.sender_display_name}</strong>
                    <span>{excerpt(replyToMessage.content)}</span>
                  </div>
                  <button type="button" className="ghost icon-only" onClick={onClearReply} aria-label="Cancel reply">
                    ×
                  </button>
                </div>
              ) : null}
              <textarea
                ref={composerRef as RefObject<HTMLTextAreaElement>}
                value={draft}
                onChange={(event) => {
                  const nextText = event.target.value;
                  const cursor = event.target.selectionStart ?? nextText.length;
                  onDraftChange(nextText, cursor);
                }}
                onKeyDown={onDraftKeyDown}
                onClick={(event) => onDraftCursorActivity(event.currentTarget.value, event.currentTarget.selectionStart ?? event.currentTarget.value.length)}
                onKeyUp={(event) => onDraftCursorActivity(event.currentTarget.value, event.currentTarget.selectionStart ?? event.currentTarget.value.length)}
                onBlur={onDraftBlur}
                placeholder="Message"
              />

              {assistOpen && assistSuggestions.length > 0 ? (
                <div className="mention-autocomplete">
                  {assistSuggestions.map((item, index) => (
                    <button
                      key={`${item.prefix || "@"}-${item.id}-${item.token}`}
                      type="button"
                      className={index === assistIndex ? "active" : ""}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        onApplySuggestion(item);
                      }}
                    >
                      <strong>{item.prefix || "@"}{item.token}</strong>
                      <span>{item.label}</span>
                      {item.sublabel ? <small>{item.sublabel}</small> : null}
                    </button>
                  ))}
                </div>
              ) : null}

              {showEmojiPicker ? (
                <div className="pm-emoji-picker">
                  {EMOJIS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        onInsertEmoji(emoji);
                      }}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <button type="button" className="pm-send-button" disabled={sendDisabled} onClick={() => void onSend()}>
              <FontAwesomeIcon icon={faPaperPlane} />
            </button>
          </div>
        </div>
      </section>

      {!hideParticipants ? (
        <aside className="card pm-members study-chat-members">
          <div className="workpane-head">
            <h3>Participants</h3>
          </div>
          <div className="pm-member-list">
            <div className="pm-member-group">
              <h4>Online</h4>
              {onlineParticipants.map((participant) => (
                <div key={`online-${participant.id}`} className="pm-member-item">
                  <ChatAvatar name={participant.name} avatarUrl={participant.avatarUrl} small />
                  <div className="pm-member-meta">
                    <strong>{participant.id === currentUser.id ? `${participant.name} (You)` : participant.name}</strong>
                    <span>{participant.subtitle || ""}</span>
                  </div>
                  <span className="pm-presence-dot online" />
                </div>
              ))}
              {onlineParticipants.length === 0 ? <p className="muted-small">No users online.</p> : null}
            </div>
            <div className="pm-member-group">
              <h4>Offline</h4>
              {offlineParticipants.map((participant) => (
                <div key={`offline-${participant.id}`} className="pm-member-item">
                  <ChatAvatar name={participant.name} avatarUrl={participant.avatarUrl} small />
                  <div className="pm-member-meta">
                    <strong>{participant.id === currentUser.id ? `${participant.name} (You)` : participant.name}</strong>
                    <span>{participant.subtitle || ""}</span>
                  </div>
                  <span className="pm-presence-dot offline" />
                </div>
              ))}
              {offlineParticipants.length === 0 ? <p className="muted-small">No users offline.</p> : null}
            </div>
            {participants.length === 0 ? <p className="muted-small">No participants.</p> : null}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
