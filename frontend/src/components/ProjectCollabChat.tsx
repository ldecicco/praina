import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBullhorn, faFaceSmile, faPaperPlane, faPlus, faReply, faUsersGear } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type {
  AuthUser,
  DocumentListItem,
  MembershipWithUser,
  ProjectBroadcast,
  ProjectChatMessage,
  ProjectChatRoom,
} from "../types";

type Props = {
  selectedProjectId: string;
  currentUser: AuthUser;
  accessToken: string;
};

type ComposerSuggestion = {
  id: string;
  trigger: "@" | "#";
  token: string;
  label: string;
  sublabel?: string;
  insertText: string;
};

type AssistTrigger = "@" | "#" | null;

const EMOJIS = [
  "😀", "😁", "😂", "🤣", "😊", "😍", "😘", "😎", "🤔", "🙌",
  "👍", "👎", "👏", "🙏", "💡", "🔥", "🎯", "✅", "❌", "⚠️",
  "📌", "📎", "📅", "📊", "🧪", "💬", "🧠", "🚀", "🎉", "💼",
];

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

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
  return cleaned || "item";
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

function findAvatarUrl(
  senderUserId: string | null,
  memberships: MembershipWithUser[],
  currentUser: AuthUser,
): string | null {
  const rawUrl = senderUserId && senderUserId === currentUser.id
    ? currentUser.avatar_url
    : memberships.find((membership) => membership.user.id === senderUserId)?.user.avatar_url ?? null;
  return rawUrl ? `${import.meta.env.VITE_API_BASE || ""}${rawUrl}` : null;
}

function excerpt(text: string, max = 96): string {
  const normalized = (text || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1).trimEnd()}…`;
}

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
      if (level === 1) output.push(<h1 key={`md-block-${key++}`}>{renderInlineMarkdown(text)}</h1>);
      else if (level === 2) output.push(<h2 key={`md-block-${key++}`}>{renderInlineMarkdown(text)}</h2>);
      else output.push(<h3 key={`md-block-${key++}`}>{renderInlineMarkdown(text)}</h3>);
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(<li key={`md-li-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^[-*]\s+/, ""))}</li>);
        i += 1;
      }
      output.push(<ul key={`md-block-${key++}`}>{items}</ul>);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(<li key={`md-oli-${key++}`}>{renderInlineMarkdown(lines[i].replace(/^\d+\.\s+/, ""))}</li>);
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
    output.push(<p key={`md-block-${key++}`}>{renderInlineMarkdown(paragraphLines.join(" "))}</p>);
  }

  return output;
}

export function ProjectCollabChat({ selectedProjectId, currentUser, accessToken }: Props) {
  const [rooms, setRooms] = useState<ProjectChatRoom[]>([]);
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [messages, setMessages] = useState<ProjectChatMessage[]>([]);
  const [broadcasts, setBroadcasts] = useState<ProjectBroadcast[]>([]);
  const [lastMessageAtByRoom, setLastMessageAtByRoom] = useState<Record<string, string>>({});
  const [seenMessageAtByRoom, setSeenMessageAtByRoom] = useState<Record<string, string>>({});
  const [memberships, setMemberships] = useState<MembershipWithUser[]>([]);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [draft, setDraft] = useState("");
  const [newRoomName, setNewRoomName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [socketState, setSocketState] = useState<"disconnected" | "connecting" | "connected">("disconnected");
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [botStreams, setBotStreams] = useState<Record<string, string>>({});
  const [replyToMessage, setReplyToMessage] = useState<ProjectChatMessage | null>(null);
  const [reactionPickerMessageId, setReactionPickerMessageId] = useState<string | null>(null);
  const [onlineUserIds, setOnlineUserIds] = useState<string[]>([]);
  const [manageRoomOpen, setManageRoomOpen] = useState(false);
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [roomMemberUserId, setRoomMemberUserId] = useState("");
  const [broadcastTitle, setBroadcastTitle] = useState("");
  const [broadcastBody, setBroadcastBody] = useState("");
  const [broadcastSeverity, setBroadcastSeverity] = useState("important");
  const [broadcastTelegram, setBroadcastTelegram] = useState(true);

  const [assistOpen, setAssistOpen] = useState(false);
  const [assistTrigger, setAssistTrigger] = useState<AssistTrigger>(null);
  const [assistQuery, setAssistQuery] = useState("");
  const [assistStart, setAssistStart] = useState<number | null>(null);
  const [assistIndex, setAssistIndex] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const activeProjectIdRef = useRef(selectedProjectId);
  const contextRequestIdRef = useRef(0);
  const messageRequestKeyRef = useRef("");

  const roomSeenStorageKey = useMemo(
    () => `project-chat-room-seen:${selectedProjectId}:${currentUser.id}`,
    [selectedProjectId, currentUser.id]
  );

  const myRole = useMemo(
    () =>
      memberships.find(
        (item) => item.membership.user_id === currentUser.id && item.membership.project_id === selectedProjectId
      )?.membership.role ?? "",
    [memberships, currentUser.id, selectedProjectId]
  );
  const canManage = myRole === "project_owner" || myRole === "project_manager";

  const uniqueUsers = useMemo(() => {
    const byId = new Map<string, MembershipWithUser["user"]>();
    memberships.forEach((item) => {
      if (!byId.has(item.user.id)) byId.set(item.user.id, item.user);
    });
    return Array.from(byId.values()).sort((a, b) => a.display_name.localeCompare(b.display_name));
  }, [memberships]);

  const onlineUsers = useMemo(() => {
    const set = new Set(onlineUserIds);
    return uniqueUsers.filter((user) => set.has(user.id));
  }, [uniqueUsers, onlineUserIds]);

  const offlineUsers = useMemo(() => {
    const set = new Set(onlineUserIds);
    return uniqueUsers.filter((user) => !set.has(user.id));
  }, [uniqueUsers, onlineUserIds]);

  const userSuggestions = useMemo(() => {
    const suggestions: ComposerSuggestion[] = [
      { id: "bot", trigger: "@", token: "bot", label: "Project Bot", sublabel: "Assistant", insertText: "@bot " },
    ];
    const seenTokens = new Set<string>(["bot"]);
    uniqueUsers.forEach((user) => {
      const base = toSlug(user.display_name || user.email.split("@")[0] || "user");
      let token = base;
      let suffix = 2;
      while (seenTokens.has(token)) {
        token = `${base}${suffix}`;
        suffix += 1;
      }
      seenTokens.add(token);
      suggestions.push({
        id: user.id,
        trigger: "@",
        token,
        label: user.display_name,
        sublabel: user.email,
        insertText: `@${token} `,
      });
    });
    return suggestions;
  }, [uniqueUsers]);

  const documentSuggestions = useMemo(() => {
    const seenTokens = new Set<string>();
    return documents.map((doc, index) => {
      const codeMatch = doc.title.match(/\b([A-Za-z]{1,4}\d+(?:\.\d+)*)\b/);
      const seed = codeMatch ? codeMatch[1].toLowerCase() : toSlug(doc.title).split("_")[0] || `doc${index + 1}`;
      let token = seed.replace(/[^a-z0-9._-]/g, "") || `doc${index + 1}`;
      let suffix = 2;
      while (seenTokens.has(token)) {
        token = `${seed}${suffix}`;
        suffix += 1;
      }
      seenTokens.add(token);
      return {
        id: doc.latest_document_id,
        trigger: "#" as const,
        token,
        label: doc.title,
        sublabel: `${doc.scope} · v${doc.latest_version}`,
        insertText: `#${token} `,
      };
    });
  }, [documents]);

  const assistSuggestions = useMemo(() => {
    if (!assistOpen || !assistTrigger) return [];
    const source = assistTrigger === "@" ? userSuggestions : documentSuggestions;
    const query = assistQuery.trim().toLowerCase();
    const filtered = source.filter((item) => {
      if (!query) return true;
      return (
        item.token.toLowerCase().startsWith(query) ||
        item.label.toLowerCase().includes(query) ||
        (item.sublabel || "").toLowerCase().includes(query)
      );
    });
    return filtered.slice(0, 8);
  }, [assistOpen, assistTrigger, assistQuery, userSuggestions, documentSuggestions]);

  const selectedRoom = useMemo(
    () => rooms.find((item) => item.id === selectedRoomId) ?? null,
    [rooms, selectedRoomId]
  );

  const availableRoomMembers = useMemo(() => {
    if (!selectedRoom) return uniqueUsers;
    const allowed = new Set(selectedRoom.member_user_ids);
    if (allowed.size === 0) return uniqueUsers;
    return uniqueUsers.filter((user) => allowed.has(user.id));
  }, [selectedRoom, uniqueUsers]);

  const assignableRoomUsers = useMemo(() => {
    if (!selectedRoom) return [];
    const assigned = new Set(selectedRoom.member_user_ids);
    return uniqueUsers.filter((user) => !assigned.has(user.id));
  }, [selectedRoom, uniqueUsers]);

  useEffect(() => {
    activeProjectIdRef.current = selectedProjectId;
    if (!selectedProjectId) {
      setRooms([]);
      setSelectedRoomId("");
      setMessages([]);
      setLastMessageAtByRoom({});
      setBroadcasts([]);
      setSeenMessageAtByRoom({});
      setMemberships([]);
      setDocuments([]);
      setBotStreams({});
      setReplyToMessage(null);
      setReactionPickerMessageId(null);
      setOnlineUserIds([]);
      setError("");
      closeSocket();
      return;
    }
    setRooms([]);
    setSelectedRoomId("");
    setMessages([]);
    setBroadcasts([]);
    setBotStreams({});
    setLastMessageAtByRoom({});
    setMemberships([]);
    setDocuments([]);
    setReplyToMessage(null);
    setReactionPickerMessageId(null);
    setOnlineUserIds([]);
    setError("");
    closeSocket();
    void loadContext(selectedProjectId);
    return () => closeSocket();
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    try {
      const raw = window.localStorage.getItem(roomSeenStorageKey);
      setSeenMessageAtByRoom(raw ? JSON.parse(raw) as Record<string, string> : {});
    } catch {
      setSeenMessageAtByRoom({});
    }
  }, [selectedProjectId, roomSeenStorageKey]);

  useEffect(() => {
    if (!selectedProjectId || !selectedRoomId) {
      setMessages([]);
      setBotStreams({});
      setReplyToMessage(null);
      setReactionPickerMessageId(null);
      setOnlineUserIds([]);
      closeSocket();
      return;
    }
    void loadMessages(selectedProjectId, selectedRoomId);
    connectSocket(selectedProjectId, selectedRoomId);
    return () => closeSocket();
  }, [selectedProjectId, selectedRoomId, accessToken]);

  useEffect(() => {
    if (!selectedProjectId || !selectedRoomId || messages.length === 0) return;
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage?.created_at) return;
    setSeenMessageAtByRoom((prev) => {
      const next = { ...prev, [selectedRoomId]: lastMessage.created_at };
      try {
        window.localStorage.setItem(roomSeenStorageKey, JSON.stringify(next));
      } catch {}
      return next;
    });
    setLastMessageAtByRoom((prev) => {
      if (prev[selectedRoomId] === lastMessage.created_at) return prev;
      return { ...prev, [selectedRoomId]: lastMessage.created_at };
    });
  }, [selectedProjectId, selectedRoomId, messages, roomSeenStorageKey]);

  useEffect(() => {
    if (threadEndRef.current) {
      threadEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, botStreams]);

  async function loadContext(projectId: string) {
    const requestId = contextRequestIdRef.current + 1;
    contextRequestIdRef.current = requestId;
    try {
      setBusy(true);
      setError("");
      const [roomsRes, membershipsRes, docsRes, broadcastsRes] = await Promise.all([
        api.listProjectRooms(projectId),
        api.listProjectMembershipsWithUsers(projectId),
        api.listDocuments(projectId),
        api.listProjectBroadcasts(projectId, { page: 1, pageSize: 12 }),
      ]);
      setRooms(roomsRes.items);
      setMemberships(membershipsRes.items);
      setDocuments(docsRes.items);
      setBroadcasts(broadcastsRes.items);
      setRoomMemberUserId("");
      const latestEntries = await Promise.all(
        roomsRes.items.map(async (room) => {
          const response = await api.listRoomMessages(projectId, room.id, { page: 1, pageSize: 1 });
          return [room.id, response.items[0]?.created_at ?? ""] as const;
        })
      );
      if (activeProjectIdRef.current !== projectId || contextRequestIdRef.current !== requestId) return;
      setLastMessageAtByRoom(Object.fromEntries(latestEntries.filter(([, createdAt]) => createdAt)));
      setSelectedRoomId(roomsRes.items[0]?.id ?? "");
    } catch (err) {
      if (activeProjectIdRef.current !== projectId || contextRequestIdRef.current !== requestId) return;
      setError(err instanceof Error ? err.message : "Failed to load project chat.");
    } finally {
      if (activeProjectIdRef.current === projectId && contextRequestIdRef.current === requestId) {
        setBusy(false);
      }
    }
  }

  async function loadMessages(projectId: string, roomId: string) {
    const requestKey = `${projectId}:${roomId}`;
    messageRequestKeyRef.current = requestKey;
    try {
      const response = await api.listRoomMessages(projectId, roomId);
      if (messageRequestKeyRef.current !== requestKey || activeProjectIdRef.current !== projectId) return;
      setMessages(response.items);
    } catch (err) {
      if (messageRequestKeyRef.current !== requestKey || activeProjectIdRef.current !== projectId) return;
      setError(err instanceof Error ? err.message : "Failed to load room messages.");
    }
  }

  function closeSocket() {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    setSocketState("disconnected");
    setOnlineUserIds([]);
  }

  function connectSocket(projectId: string, roomId: string) {
    closeSocket();
    setSocketState("connecting");
    const socket = new WebSocket(`${wsBaseUrl()}/projects/${projectId}/rooms/${roomId}/ws?token=${encodeURIComponent(accessToken)}`);
    socketRef.current = socket;

    socket.onopen = () => setSocketState("connected");
    socket.onclose = () => {
      setSocketState("disconnected");
      setOnlineUserIds([]);
    };
    socket.onerror = () => {
      setSocketState("disconnected");
      setOnlineUserIds([]);
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          event?: string;
          message?: ProjectChatMessage;
          detail?: string;
          status?: string;
          stream_id?: string;
          chunk?: string;
          user_ids?: string[];
          user_id?: string;
        };

        if (payload.event === "error" && payload.detail) {
          setError(payload.detail);
          return;
        }

        if (payload.event === "bot_status" && payload.stream_id) {
          if (payload.status === "start") {
            setBotStreams((prev) => ({ ...prev, [payload.stream_id!]: "" }));
          }
          if (payload.status === "stop") {
            setBotStreams((prev) => {
              const next = { ...prev };
              delete next[payload.stream_id!];
              return next;
            });
          }
          return;
        }

        if (payload.event === "bot_stream" && payload.stream_id && typeof payload.chunk === "string") {
          setBotStreams((prev) => ({ ...prev, [payload.stream_id!]: (prev[payload.stream_id!] || "") + payload.chunk }));
          return;
        }

        if (payload.event === "presence_snapshot") {
          setOnlineUserIds(Array.isArray(payload.user_ids) ? payload.user_ids : []);
          return;
        }

        if (payload.event === "presence" && payload.user_id) {
          setOnlineUserIds((prev) => {
            if (payload.status === "joined") {
              if (prev.includes(payload.user_id!)) return prev;
              return [...prev, payload.user_id!];
            }
            if (payload.status === "left") {
              return prev.filter((id) => id !== payload.user_id);
            }
            return prev;
          });
          return;
        }

        if (payload.event === "message" && payload.message) {
          const incomingMessage = payload.message;
          setLastMessageAtByRoom((prev) => ({ ...prev, [incomingMessage.room_id]: incomingMessage.created_at }));
          setMessages((prev) => {
            if (prev.some((item) => item.id === incomingMessage.id)) return prev;
            return [...prev, incomingMessage];
          });
          return;
        }

        if (payload.event === "message_updated" && payload.message) {
          const incomingMessage = payload.message;
          setMessages((prev) =>
            prev.map((item) => (item.id === incomingMessage.id ? incomingMessage : item))
          );
        }
      } catch {
        setError("Invalid WebSocket payload.");
      }
    };
  }

  async function handleCreateRoom() {
    if (!selectedProjectId || !newRoomName.trim()) return;
    try {
      setBusy(true);
      setError("");
      const room = await api.createProjectRoom(selectedProjectId, { name: newRoomName.trim() });
      setRooms((prev) => [...prev, room]);
      setSelectedRoomId(room.id);
      setNewRoomName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create room.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddRoomMember() {
    if (!selectedProjectId || !selectedRoomId || !roomMemberUserId) return;
    try {
      setError("");
      const updated = await api.addRoomMember(selectedProjectId, selectedRoomId, { user_id: roomMemberUserId });
      setRooms((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setRoomMemberUserId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add room member.");
    }
  }

  async function handleRemoveRoomMember(userId: string) {
    if (!selectedProjectId || !selectedRoomId) return;
    try {
      setError("");
      const updated = await api.removeRoomMember(selectedProjectId, selectedRoomId, userId);
      setRooms((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove room member.");
    }
  }

  async function handleSendMessage() {
    const content = draft.trim();
    if (!selectedProjectId || !selectedRoomId || !content) return;
    const replyToMessageId = replyToMessage?.id ?? null;
    try {
      setError("");
      setDraft("");
      closeAssist();
      setShowEmojiPicker(false);
      setReactionPickerMessageId(null);
      setReplyToMessage(null);
      if (socketRef.current && socketState === "connected") {
        socketRef.current.send(JSON.stringify({ content, reply_to_message_id: replyToMessageId }));
        return;
      }
      const created = await api.createRoomMessage(selectedProjectId, selectedRoomId, {
        content,
        reply_to_message_id: replyToMessageId,
      });
      setMessages((prev) => [...prev, created]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    }
  }

  async function handleSendBroadcast() {
    if (!selectedProjectId || !broadcastTitle.trim() || !broadcastBody.trim()) return;
    try {
      setBusy(true);
      setError("");
      const created = await api.createProjectBroadcast(selectedProjectId, {
        title: broadcastTitle.trim(),
        body: broadcastBody.trim(),
        severity: broadcastSeverity,
        deliver_telegram: broadcastTelegram,
      });
      setBroadcasts((prev) => [created, ...prev].slice(0, 12));
      setBroadcastOpen(false);
      setBroadcastTitle("");
      setBroadcastBody("");
      setBroadcastSeverity("important");
      setBroadcastTelegram(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send broadcast.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleReaction(messageId: string, emoji: string) {
    if (!selectedProjectId || !selectedRoomId) return;
    try {
      setError("");
      const updated = await api.toggleRoomMessageReaction(selectedProjectId, selectedRoomId, messageId, { emoji });
      setMessages((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setReactionPickerMessageId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update reaction.");
    }
  }

  function closeAssist() {
    setAssistOpen(false);
    setAssistTrigger(null);
    setAssistQuery("");
    setAssistStart(null);
    setAssistIndex(0);
  }

  function updateAssistState(nextText: string, cursorPosition: number) {
    const left = nextText.slice(0, cursorPosition);
    const match = left.match(/(^|\s)([@#])([a-zA-Z0-9._:-]*)$/);
    if (!match) {
      closeAssist();
      return;
    }
    const trigger = match[2] as "@" | "#";
    const query = match[3] || "";
    setAssistOpen(true);
    setAssistTrigger(trigger);
    setAssistQuery(query);
    setAssistStart(cursorPosition - query.length - 1);
    setAssistIndex(0);
  }

  function applySuggestion(item: ComposerSuggestion) {
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
      void handleSendMessage();
    }
  }

  if (!selectedProjectId) {
    return (
      <section className="panel">
        <p className="muted-small">Select a project to start.</p>
      </section>
    );
  }

  const shownUsers = availableRoomMembers;
  const shownOnlineUsers = shownUsers.filter((user) => onlineUsers.some((item) => item.id === user.id));
  const shownOfflineUsers = shownUsers.filter((user) => !shownOnlineUsers.some((item) => item.id === user.id));

  const unreadByRoom = useMemo(() => {
    const output: Record<string, number> = {};
    rooms.forEach((room) => {
      const latest = lastMessageAtByRoom[room.id];
      if (!latest) {
        output[room.id] = 0;
        return;
      }
      const seen = seenMessageAtByRoom[room.id];
      output[room.id] = !seen || new Date(latest).getTime() > new Date(seen).getTime() ? 1 : 0;
    });
    return output;
  }, [lastMessageAtByRoom, rooms, seenMessageAtByRoom]);

  return (
    <section className="panel">
      {error ? <p className="error">{error}</p> : null}

      <div className="pm-chat-layout">
        <aside className="card pm-rooms">
          <div className="workpane-head">
            <h3>Rooms</h3>
            <span className={`socket-pill ${socketState}`}>{socketState}</span>
          </div>

          <div className="pm-room-list">
            {rooms.map((room) => (
              <button
                key={room.id}
                type="button"
                className={`pm-room-item ${room.id === selectedRoomId ? "active" : ""}`}
                onClick={() => setSelectedRoomId(room.id)}
              >
                <span className="pm-room-dot" />
                <span className="pm-room-copy">
                  <strong>{room.name}</strong>
                  <small>{room.member_user_ids.length > 0 ? `${room.member_user_ids.length} members` : "Project room"}</small>
                </span>
                {unreadByRoom[room.id] ? <span className="pm-room-unread">{unreadByRoom[room.id]}</span> : null}
              </button>
            ))}
            {rooms.length === 0 ? <p className="muted-small">No rooms.</p> : null}
          </div>

          {canManage ? (
            <div className="pm-room-create">
              <input
                value={newRoomName}
                onChange={(event) => setNewRoomName(event.target.value)}
                placeholder="New room"
              />
              <button type="button" disabled={busy || !newRoomName.trim()} onClick={() => void handleCreateRoom()}>
                <FontAwesomeIcon icon={faPlus} />
                <span>Add</span>
              </button>
            </div>
          ) : null}

          <div className="pm-broadcast-panel">
            <div className="pm-broadcast-head">
              <h4>Broadcasts</h4>
              {canManage ? (
                <button type="button" className="ghost icon-only" onClick={() => setBroadcastOpen(true)} aria-label="Broadcast">
                  <FontAwesomeIcon icon={faBullhorn} />
                </button>
              ) : null}
            </div>
            <div className="pm-broadcast-list">
              {broadcasts.map((item) => (
                <div key={item.id} className={`pm-broadcast-item ${item.severity}`}>
                  <div className="pm-broadcast-item-head">
                    <span className={`pm-broadcast-severity ${item.severity}`}>{item.severity}</span>
                    <span>{formatTimestamp(item.sent_at)}</span>
                  </div>
                  <strong>{item.title}</strong>
                  <p>{excerpt(item.body, 120)}</p>
                  <small>{item.author_display_name} · {item.recipient_count} recipients</small>
                </div>
              ))}
              {broadcasts.length === 0 ? <p className="muted-small">No broadcasts.</p> : null}
            </div>
          </div>
        </aside>

        <section className="card pm-thread">
          <div className="workpane-head">
            <h3>{selectedRoom?.name || "Room"}</h3>
            {canManage && selectedRoom ? (
              <button type="button" className="ghost icon-only" onClick={() => setManageRoomOpen(true)} aria-label="Manage room">
                <FontAwesomeIcon icon={faUsersGear} />
              </button>
            ) : null}
          </div>

          <div className="pm-messages">
            {messages.map((message) => {
              const own = message.sender_user_id === currentUser.id;
              const senderName = own ? "You" : message.sender_display_name;
              const senderAvatarUrl = findAvatarUrl(message.sender_user_id, memberships, currentUser);
              const replyPreview = message.reply_to_message;
              return (
                <article id={`pm-msg-${message.id}`} key={message.id} className={`pm-message-row ${own ? "own" : "other"}`}>
                  <span className="pm-avatar-badge small">
                    {senderAvatarUrl ? (
                      <img src={senderAvatarUrl} alt={senderName} />
                    ) : (
                      initials(senderName)
                    )}
                  </span>
                  <div className={`pm-message-bubble ${own ? "own" : "other"}`}>
                    <div className="pm-message-head">
                      <strong>{senderName}</strong>
                      <span>{formatTimestamp(message.created_at)}</span>
                    </div>
                    {replyPreview ? (
                      <button
                        type="button"
                        className="pm-reply-preview"
                        onClick={() => {
                          const index = messages.findIndex((item) => item.id === replyPreview.id);
                          if (index >= 0) {
                            const row = document.getElementById(`pm-msg-${replyPreview.id}`);
                            row?.scrollIntoView({ behavior: "smooth", block: "center" });
                          }
                        }}
                      >
                        <strong>{replyPreview.sender_user_id === currentUser.id ? "You" : replyPreview.sender_display_name}</strong>
                        <span>{excerpt(replyPreview.content)}</span>
                      </button>
                    ) : null}
                    <div className="chat-markdown">{renderMarkdown(message.content)}</div>
                    {message.reactions.length > 0 ? (
                      <div className="pm-reactions">
                        {message.reactions.map((reaction) => {
                          const mine = reaction.user_ids.includes(currentUser.id);
                          return (
                            <button
                              key={`${message.id}-${reaction.emoji}`}
                              type="button"
                              className={`pm-reaction-chip ${mine ? "mine" : ""}`}
                              onClick={() => void handleToggleReaction(message.id, reaction.emoji)}
                            >
                              <span>{reaction.emoji}</span>
                              <strong>{reaction.count}</strong>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    <div className="pm-message-actions">
                      <button type="button" className="ghost icon-only" onClick={() => setReplyToMessage(message)} aria-label="Reply">
                        <FontAwesomeIcon icon={faReply} />
                      </button>
                      <button
                        type="button"
                        className="ghost icon-only"
                        onClick={() =>
                          setReactionPickerMessageId((prev) => (prev === message.id ? null : message.id))
                        }
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
                              void handleToggleReaction(message.id, emoji);
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

            {Object.entries(botStreams).map(([streamId, text]) => (
              <article key={streamId} className="pm-message-row other">
                <span className="pm-avatar-badge small">PB</span>
                <div className="pm-message-bubble other bot-stream-message">
                  <div className="pm-message-head">
                    <strong>Project Bot</strong>
                    <span className="bot-thinking" aria-live="polite">
                      <span>Bot thinking</span>
                      <span className="bot-thinking-dots" aria-hidden="true">
                        <span>.</span>
                        <span>.</span>
                        <span>.</span>
                      </span>
                    </span>
                  </div>
                  <div className="chat-markdown">{renderMarkdown(text || "Thinking")}</div>
                </div>
              </article>
            ))}

            {messages.length === 0 ? <p className="muted-small">No messages yet.</p> : null}
            <div ref={threadEndRef} />
          </div>

          <div className="pm-composer">
            <div className="pm-composer-main">
              <button
                type="button"
                className="ghost icon-only"
                aria-label="Add emoji"
                onClick={() => setShowEmojiPicker((prev) => !prev)}
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
                    <button type="button" className="ghost icon-only" onClick={() => setReplyToMessage(null)} aria-label="Cancel reply">
                      ×
                    </button>
                  </div>
                ) : null}
                <textarea
                  ref={composerRef}
                  value={draft}
                  onChange={(event) => {
                    const nextText = event.target.value;
                    const cursor = event.target.selectionStart ?? nextText.length;
                    setDraft(nextText);
                    updateAssistState(nextText, cursor);
                  }}
                  onKeyDown={handleDraftKeyDown}
                  onClick={(event) =>
                    updateAssistState(
                      event.currentTarget.value,
                      event.currentTarget.selectionStart ?? event.currentTarget.value.length
                    )
                  }
                  onKeyUp={(event) =>
                    updateAssistState(
                      event.currentTarget.value,
                      event.currentTarget.selectionStart ?? event.currentTarget.value.length
                    )
                  }
                  onBlur={() => {
                    window.setTimeout(() => closeAssist(), 80);
                  }}
                  placeholder="Message"
                />

                {assistOpen && assistSuggestions.length > 0 ? (
                  <div className="mention-autocomplete">
                    {assistSuggestions.map((item, index) => (
                      <button
                        key={`${item.trigger}-${item.id}-${item.token}`}
                        type="button"
                        className={index === assistIndex ? "active" : ""}
                        onMouseDown={(event) => {
                          event.preventDefault();
                          applySuggestion(item);
                        }}
                      >
                        <strong>{item.trigger}{item.token}</strong>
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
                          insertEmoji(emoji);
                        }}
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <button type="button" className="pm-send-button" disabled={!draft.trim()} onClick={() => void handleSendMessage()}>
              <FontAwesomeIcon icon={faPaperPlane} />
            </button>
          </div>
        </section>

        <aside className="card pm-members">
          <div className="workpane-head">
            <h3>Participants</h3>
          </div>
          <div className="pm-member-list">
              <div className="pm-member-group">
              <h4>Online</h4>
              {shownOnlineUsers.map((user) => (
                <div key={user.id} className="pm-member-item">
                  <span className="pm-avatar-badge">{initials(user.display_name)}</span>
                  <div className="pm-member-meta">
                    <strong>{user.id === currentUser.id ? `${user.display_name} (You)` : user.display_name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <span className="pm-presence-dot online" />
                </div>
              ))}
              {shownOnlineUsers.length === 0 ? <p className="muted-small">No users online.</p> : null}
            </div>
            <div className="pm-member-group">
              <h4>Offline</h4>
              {shownOfflineUsers.map((user) => (
                <div key={user.id} className="pm-member-item">
                  <span className="pm-avatar-badge">{initials(user.display_name)}</span>
                  <div className="pm-member-meta">
                    <strong>{user.id === currentUser.id ? `${user.display_name} (You)` : user.display_name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <span className="pm-presence-dot offline" />
                </div>
              ))}
              {shownOfflineUsers.length === 0 ? <p className="muted-small">No users offline.</p> : null}
            </div>
            {shownUsers.length === 0 ? <p className="muted-small">No participants.</p> : null}
          </div>
        </aside>
      </div>

      {manageRoomOpen && selectedRoom ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card room-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && roomMemberUserId) { e.preventDefault(); void handleAddRoomMember(); } }}>
            <div className="modal-head">
              <h3>Manage Room</h3>
              <button type="button" className="ghost" onClick={() => setManageRoomOpen(false)}>
                Close
              </button>
            </div>
            <div className="settings-validation-list">
              <div className="settings-validation-item">
                <strong>{selectedRoom.name}</strong>
                <span>{selectedRoom.member_user_ids.length > 0 ? "Restricted room" : "Project-wide room"}</span>
              </div>
            </div>
            {assignableRoomUsers.length > 0 ? (
              <div className="admin-membership-form">
                <label>
                  User
                  <select value={roomMemberUserId} onChange={(event) => setRoomMemberUserId(event.target.value)}>
                    <option value="">Select user</option>
                    {assignableRoomUsers.map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.display_name} · {user.email}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" disabled={!roomMemberUserId} onClick={() => void handleAddRoomMember()}>
                  Add Member
                </button>
              </div>
            ) : null}
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedRoom.member_user_ids.length > 0
                    ? uniqueUsers.filter((user) => selectedRoom.member_user_ids.includes(user.id))
                    : []
                  ).map((user) => (
                    <tr key={user.id}>
                      <td>{user.display_name}</td>
                      <td>{user.email}</td>
                      <td>
                        <button type="button" className="ghost" onClick={() => void handleRemoveRoomMember(user.id)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                  {selectedRoom.member_user_ids.length === 0 ? (
                    <tr>
                      <td colSpan={3}>This room is open to all project members.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}

      {broadcastOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
            <div
              className="modal-card room-modal-card"
              onKeyDown={(e) => {
                if (e.key === "Escape") setBroadcastOpen(false);
              }}
            >
              <div className="modal-head">
                <h3>Broadcast</h3>
                <button type="button" className="ghost" onClick={() => setBroadcastOpen(false)}>
                  Close
                </button>
              </div>
              <div className="form-grid">
                <label className="full-span">
                  Title
                  <input value={broadcastTitle} onChange={(event) => setBroadcastTitle(event.target.value)} />
                </label>
                <label className="full-span">
                  Message
                  <textarea value={broadcastBody} onChange={(event) => setBroadcastBody(event.target.value)} />
                </label>
                <label>
                  Severity
                  <select value={broadcastSeverity} onChange={(event) => setBroadcastSeverity(event.target.value)}>
                    <option value="info">Info</option>
                    <option value="important">Important</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={broadcastTelegram}
                    onChange={(event) => setBroadcastTelegram(event.target.checked)}
                  />
                  Telegram
                </label>
              </div>
              <div className="modal-actions profile-modal-actions">
                <button type="button" className="ghost" onClick={() => setBroadcastOpen(false)}>Cancel</button>
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !broadcastTitle.trim() || !broadcastBody.trim()}
                  onClick={() => void handleSendBroadcast()}
                >
                  {busy ? "Sending..." : "Send"}
                </button>
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}
    </section>
  );
}
