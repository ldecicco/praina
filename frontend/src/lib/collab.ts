import * as Y from "yjs";
import { Awareness, applyAwarenessUpdate, encodeAwarenessUpdate, removeAwarenessStates } from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";

const SYNC_MESSAGE = 0;
const AWARENESS_MESSAGE = 1;
const DEFAULT_FIELD = "default";

function wsBaseUrl(): string {
  const apiBase = import.meta.env.VITE_API_BASE as string;
  const resolved = new URL(apiBase, window.location.origin);
  resolved.protocol = resolved.protocol === "https:" ? "wss:" : "ws:";
  return resolved.toString().replace(/\/$/, "");
}

function frameMessage(type: number, payload: Uint8Array): Uint8Array {
  const framed = new Uint8Array(payload.length + 1);
  framed[0] = type;
  framed.set(payload, 1);
  return framed;
}

function colorFromId(userId: string): string {
  let hash = 0;
  for (let index = 0; index < userId.length; index += 1) {
    hash = ((hash << 5) - hash + userId.charCodeAt(index)) | 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 68% 58%)`;
}

type CollabUser = {
  id: string;
  name: string;
  color?: string;
};

export class ProposalCollabProvider {
  readonly doc = new Y.Doc();
  readonly awareness = new Awareness(this.doc);
  private readonly projectId: string;
  private readonly sectionId: string;
  private readonly token: string;
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private reconnectDelayMs = 1000;
  private destroyed = false;
  private synced = false;
  private syncedListeners = new Set<() => void>();

  constructor(projectId: string, sectionId: string, token: string, user: CollabUser) {
    this.projectId = projectId;
    this.sectionId = sectionId;
    this.token = token;
    this.awareness.setLocalStateField("user", {
      id: user.id,
      name: user.name,
      color: user.color || colorFromId(user.id),
    });
    this.doc.on("update", this.handleDocUpdate);
    this.awareness.on("update", this.handleAwarenessUpdate);
  }

  connect(): void {
    if (this.destroyed || this.ws) return;
    const socket = new WebSocket(
      `${wsBaseUrl()}/projects/${this.projectId}/proposal-sections/${this.sectionId}/ws?token=${encodeURIComponent(this.token)}`
    );
    socket.binaryType = "arraybuffer";
    this.ws = socket;

    socket.onopen = () => {
      this.reconnectDelayMs = 1000;
      const encoder = encoding.createEncoder();
      syncProtocol.writeSyncStep1(encoder, this.doc);
      this.send(frameMessage(SYNC_MESSAGE, encoding.toUint8Array(encoder)));
      const states = Array.from(this.awareness.getStates().keys());
      if (states.length > 0) {
        this.send(frameMessage(AWARENESS_MESSAGE, encodeAwarenessUpdate(this.awareness, states)));
      }
    };

    socket.onmessage = (event) => {
      const data = new Uint8Array(event.data as ArrayBuffer);
      if (data.length === 0) return;
      const messageType = data[0];
      const body = data.slice(1);

      if (messageType === SYNC_MESSAGE) {
        const decoder = decoding.createDecoder(body);
        const encoder = encoding.createEncoder();
        syncProtocol.readSyncMessage(decoder, encoder, this.doc, this);
        const reply = encoding.toUint8Array(encoder);
        if (reply.length > 0) {
          this.send(frameMessage(SYNC_MESSAGE, reply));
        }
        if (!this.synced) {
          this.synced = true;
          for (const listener of Array.from(this.syncedListeners)) listener();
        }
        return;
      }

      if (messageType === AWARENESS_MESSAGE) {
        applyAwarenessUpdate(this.awareness, body, this);
      }
    };

    socket.onclose = () => {
      this.ws = null;
      if (!this.destroyed) this.scheduleReconnect();
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  onceSynced(listener: () => void): () => void {
    if (this.synced) {
      listener();
      return () => undefined;
    }
    this.syncedListeners.add(listener);
    return () => {
      this.syncedListeners.delete(listener);
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (!this.ws) return;
    const localClientId = this.doc.clientID;
    removeAwarenessStates(this.awareness, [localClientId], this);
    this.send(frameMessage(AWARENESS_MESSAGE, encodeAwarenessUpdate(this.awareness, [localClientId])));
    const socket = this.ws;
    this.ws = null;
    if (socket.readyState === WebSocket.CONNECTING) {
      // Wait for the socket to open before closing it cleanly,
      // otherwise browsers log "closed before connection established".
      socket.onopen = () => socket.close();
      socket.onmessage = null;
      socket.onerror = () => socket.close();
    } else {
      socket.close();
    }
  }

  destroy(): void {
    this.destroyed = true;
    this.disconnect();
    this.doc.off("update", this.handleDocUpdate);
    this.awareness.off("update", this.handleAwarenessUpdate);
    this.awareness.destroy();
    this.doc.destroy();
  }

  private handleDocUpdate = (update: Uint8Array, origin: unknown) => {
    if (origin === this) return;
    const encoder = encoding.createEncoder();
    syncProtocol.writeUpdate(encoder, update);
    this.send(frameMessage(SYNC_MESSAGE, encoding.toUint8Array(encoder)));
  };

  private handleAwarenessUpdate = (
    changes: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown
  ) => {
    if (origin === this) return;
    const changedClients = changes.added.concat(changes.updated, changes.removed);
    if (changedClients.length === 0) return;
    this.send(frameMessage(AWARENESS_MESSAGE, encodeAwarenessUpdate(this.awareness, changedClients)));
  };

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectDelayMs);
    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, 10000);
  }

  private send(payload: Uint8Array): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(payload);
  }
}

export function collabFieldName(): string {
  return DEFAULT_FIELD;
}

export function isCollabDocEmpty(doc: Y.Doc): boolean {
  return doc.getXmlFragment(DEFAULT_FIELD).length === 0;
}
