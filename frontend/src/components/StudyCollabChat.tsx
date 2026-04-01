import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { api } from "../lib/api";
import type { AuthUser, ResearchCollectionMember, StudyChatMessage } from "../types";
import { ChatThreadPanel, type ChatComposerSuggestion, type ChatParticipant } from "./ChatThreadPanel";

type Props = {
  projectId: string;
  collectionId: string;
  researchSpaceId?: string | null;
  currentUser: AuthUser;
  members: ResearchCollectionMember[];
  threadTitle?: string | null;
};

function wsBaseUrl(): string {
  const apiBase = import.meta.env.VITE_API_BASE as string;
  if (apiBase.startsWith("https://")) return apiBase.replace("https://", "wss://");
  if (apiBase.startsWith("http://")) return apiBase.replace("http://", "ws://");
  return apiBase;
}

function toSlug(input: string): string {
  const cleaned = input
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned || "user";
}

function toMentionTokens(user: AuthUser): Set<string> {
  const tokens = new Set<string>();
  const emailLocal = user.email.split("@")[0]?.trim().toLowerCase();
  if (emailLocal) tokens.add(emailLocal);
  user.display_name
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => tokens.add(item));
  tokens.add(user.display_name.trim().toLowerCase().replace(/\s+/g, "."));
  tokens.add(user.display_name.trim().toLowerCase().replace(/\s+/g, "_"));
  return tokens;
}

function resolveAvatarUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${import.meta.env.VITE_API_BASE || ""}${path}`;
}

export function StudyCollabChat({
  projectId,
  collectionId,
  researchSpaceId = null,
  currentUser,
  members,
}: Props) {
  const [messages, setMessages] = useState<StudyChatMessage[]>([]);
  const [onlineUserIds, setOnlineUserIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [replyToMessage, setReplyToMessage] = useState<StudyChatMessage | null>(null);
  const [reactionPickerMessageId, setReactionPickerMessageId] = useState<string | null>(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [assistOpen, setAssistOpen] = useState(false);
  const [assistQuery, setAssistQuery] = useState("");
  const [assistStart, setAssistStart] = useState<number | null>(null);
  const [assistIndex, setAssistIndex] = useState(0);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const currentUserMentionTokens = useMemo(() => toMentionTokens(currentUser), [currentUser]);
  const memberDirectory = useMemo<ChatParticipant[]>(() => {
    const direct = members
      .map((item) => ({
        id: item.user_id || item.member_id,
        name: item.member_name || "Member",
        subtitle: item.role,
        avatarUrl: resolveAvatarUrl(item.avatar_url),
      }))
      .filter((item) => item.id);
    if (!direct.some((item) => item.id === currentUser.id)) {
      direct.unshift({
        id: currentUser.id,
        name: currentUser.display_name,
        subtitle: "contributor",
        avatarUrl: resolveAvatarUrl(currentUser.avatar_url),
      });
    }
    const seen = new Set<string>();
    return direct.filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }, [members, currentUser.avatar_url, currentUser.display_name, currentUser.id]);
  const userSuggestions = useMemo<ChatComposerSuggestion[]>(() => {
    const seen = new Set<string>();
    return memberDirectory.map((item) => {
      const base = toSlug(item.name);
      let token = base;
      let suffix = 2;
      while (seen.has(token)) {
        token = `${base}${suffix}`;
        suffix += 1;
      }
      seen.add(token);
      return {
        id: item.id,
        token,
        label: item.id === currentUser.id ? "You" : item.name,
        sublabel: item.subtitle || undefined,
        insertText: `@${token} `,
        prefix: "@",
      };
    });
  }, [memberDirectory, currentUser.id]);
  const assistSuggestions = useMemo(() => {
    if (!assistOpen) return [];
    const query = assistQuery.trim().toLowerCase();
    return userSuggestions
      .filter((item) =>
        !query ||
        item.token.toLowerCase().startsWith(query) ||
        item.label.toLowerCase().includes(query) ||
        (item.sublabel || "").toLowerCase().includes(query)
      )
      .slice(0, 8);
  }, [assistOpen, assistQuery, userSuggestions]);

  async function loadMessages(showLoading = false) {
    if (showLoading) setLoading(true);
    try {
      const response = await api.listStudyChatMessages(projectId, collectionId, {
        page: 1,
        pageSize: 100,
        spaceId: researchSpaceId,
      });
      setMessages(response.items);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    void loadMessages(true);
  }, [projectId, collectionId, researchSpaceId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadMessages(false);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [projectId, collectionId, researchSpaceId]);

  useEffect(() => {
    const token = api.getAuthToken();
    if (!token) return;
    const url = new URL(`${wsBaseUrl()}/projects/${projectId}/research/collections/${collectionId}/chat/ws`);
    url.searchParams.set("token", token);
    if (researchSpaceId) url.searchParams.set("space_id", researchSpaceId);
    const socket = new WebSocket(url.toString());
    socketRef.current = socket;
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          event?: string;
          user_ids?: string[];
          status?: string;
          user_id?: string;
          message?: StudyChatMessage;
        };
        if (payload.event === "presence_snapshot") {
          setOnlineUserIds(Array.isArray(payload.user_ids) ? payload.user_ids : []);
          return;
        }
        if (payload.event === "presence" && payload.user_id) {
          setOnlineUserIds((prev) =>
                    payload.status === "joined"
              ? Array.from(new Set([...prev, payload.user_id as string]))
              : prev.filter((item) => item !== payload.user_id),
          );
          return;
        }
        if (payload.event === "message" && payload.message) {
          setMessages((prev) => (prev.some((item) => item.id === payload.message!.id) ? prev : [...prev, payload.message!]));
          return;
        }
        if (payload.event === "message_update" && payload.message) {
          setMessages((prev) => prev.map((item) => (item.id === payload.message!.id ? payload.message! : item)));
        }
      } catch {
        // noop
      }
    };
    socket.onerror = () => {
      setOnlineUserIds([]);
    };
    socket.onclose = () => {
      setOnlineUserIds([]);
    };
    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [projectId, collectionId, researchSpaceId]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function closeAssist() {
    setAssistOpen(false);
    setAssistQuery("");
    setAssistStart(null);
    setAssistIndex(0);
  }

  function updateAssistState(nextText: string, cursorPosition: number) {
    const left = nextText.slice(0, cursorPosition);
    const match = left.match(/(^|\s)@([a-zA-Z0-9._:-]*)$/);
    if (!match) {
      closeAssist();
      return;
    }
    const query = match[2] || "";
    setAssistOpen(true);
    setAssistQuery(query);
    setAssistStart(cursorPosition - query.length - 1);
    setAssistIndex(0);
  }

  function applySuggestion(item: ChatComposerSuggestion) {
    const textarea = composerRef.current;
    if (!textarea || assistStart === null) return;
    const cursor = textarea.selectionStart ?? draft.length;
    const next = `${draft.slice(0, assistStart)}${item.insertText}${draft.slice(cursor)}`;
    setDraft(next);
    closeAssist();
    requestAnimationFrame(() => {
      textarea.focus();
      const nextCursor = assistStart + item.insertText.length;
      textarea.setSelectionRange(nextCursor, nextCursor);
    });
  }

  function insertEmoji(emoji: string) {
    const textarea = composerRef.current;
    if (!textarea) {
      setDraft((prev) => `${prev}${emoji}`);
      return;
    }
    const start = textarea.selectionStart ?? draft.length;
    const end = textarea.selectionEnd ?? start;
    const next = `${draft.slice(0, start)}${emoji}${draft.slice(end)}`;
    setDraft(next);
    requestAnimationFrame(() => {
      textarea.focus();
      const caret = start + emoji.length;
      textarea.setSelectionRange(caret, caret);
    });
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (assistOpen && assistSuggestions.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setAssistIndex((prev) => (prev + 1) % assistSuggestions.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setAssistIndex((prev) => (prev - 1 + assistSuggestions.length) % assistSuggestions.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        applySuggestion(assistSuggestions[Math.min(assistIndex, assistSuggestions.length - 1)]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeAssist();
        return;
      }
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (!content || busy) return;
    setBusy(true);
    try {
      const created = await api.createStudyChatMessage(
        projectId,
        collectionId,
        { content, reply_to_message_id: replyToMessage?.id ?? null },
        researchSpaceId,
      );
      setMessages((prev) => [...prev, created]);
      setDraft("");
      setReplyToMessage(null);
      setShowEmojiPicker(false);
      setError("");
      composerRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleReaction(messageId: string, emoji: string) {
    try {
      const updated = await api.toggleStudyChatReaction(projectId, collectionId, messageId, { emoji }, researchSpaceId);
      setMessages((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setReactionPickerMessageId((prev) => (prev === messageId ? null : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update reaction.");
    }
  }

  return (
    <ChatThreadPanel
      showHeader={false}
      error={error}
      loading={loading}
      emptyMessage="No messages yet."
      currentUser={currentUser}
      currentUserMentionTokens={currentUserMentionTokens}
      messages={messages}
      participants={memberDirectory}
      onlineUserIds={onlineUserIds}
      draft={draft}
      composerRef={composerRef}
      threadEndRef={threadEndRef}
      replyToMessage={replyToMessage}
      reactionPickerMessageId={reactionPickerMessageId}
      showEmojiPicker={showEmojiPicker}
      assistOpen={assistOpen}
      assistSuggestions={assistSuggestions}
      assistIndex={assistIndex}
      sendDisabled={busy || !draft.trim()}
      messageDomIdPrefix="study-msg"
      onDraftChange={(value, cursorPosition) => {
        setDraft(value);
        updateAssistState(value, cursorPosition);
      }}
      onDraftCursorActivity={updateAssistState}
      onDraftKeyDown={handleDraftKeyDown}
      onDraftBlur={() => {
        window.setTimeout(() => closeAssist(), 80);
      }}
      onSend={handleSend}
      onReply={(message) => setReplyToMessage(message as StudyChatMessage)}
      onClearReply={() => setReplyToMessage(null)}
      onToggleReactionPicker={(messageId) => setReactionPickerMessageId((prev) => (prev === messageId ? null : messageId))}
      onToggleReaction={handleToggleReaction}
      onToggleEmojiPicker={() => setShowEmojiPicker((prev) => !prev)}
      onInsertEmoji={(emoji) => {
        insertEmoji(emoji);
        setShowEmojiPicker(false);
      }}
      onApplySuggestion={applySuggestion}
    />
  );
}
