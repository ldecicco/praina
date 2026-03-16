import { useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBoxArchive,
  faClipboardCheck,
  faFlagCheckered,
  faLayerGroup,
  faRotateLeft,
  faShieldHalved,
  faUserCheck,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { AuditEvent } from "../types";

type Props = {
  projectId: string;
  limit?: number;
};

function eventLabel(eventType: string): string {
  return eventType.split(".").join(" ").split("_").join(" ");
}

function eventIcon(eventType: string) {
  if (eventType.includes("deliverable")) return faFlagCheckered;
  if (eventType.includes("risk")) return faShieldHalved;
  if (eventType.includes("assignment")) return faUserCheck;
  if (eventType.includes("restore")) return faRotateLeft;
  if (eventType.includes("trash")) return faBoxArchive;
  return faLayerGroup;
}

function entityCode(event: AuditEvent): string {
  const afterCode = event.after_json && typeof event.after_json.code === "string" ? event.after_json.code : "";
  const beforeCode = event.before_json && typeof event.before_json.code === "string" ? event.before_json.code : "";
  return afterCode || beforeCode || event.entity_type;
}

function entityTitle(event: AuditEvent): string {
  const afterTitle = event.after_json && typeof event.after_json.title === "string" ? event.after_json.title : "";
  const beforeTitle = event.before_json && typeof event.before_json.title === "string" ? event.before_json.title : "";
  return afterTitle || beforeTitle || event.reason || "";
}

function actorLabel(event: AuditEvent): string {
  return event.actor_name || "System";
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function ProjectActivityFeed({ projectId, limit = 12 }: Props) {
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId) {
      setItems([]);
      return;
    }
    api
      .listActivity(projectId, 1, limit)
      .then((response) => {
        setItems(response.items);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load activity."));
  }, [limit, projectId]);

  const rows = useMemo(() => items.slice(0, limit), [items, limit]);

  return (
    <div className="activity-feed">
      {error ? <p className="error">{error}</p> : null}
      {rows.map((item) => (
        <div key={item.id} className="activity-row">
          <span className="activity-icon">
            <FontAwesomeIcon icon={eventIcon(item.event_type)} />
          </span>
          <div className="activity-body">
            <div className="activity-topline">
              <strong>{entityCode(item)}</strong>
              <span>{eventLabel(item.event_type)}</span>
            </div>
            {entityTitle(item) ? <div className="activity-title">{entityTitle(item)}</div> : null}
            <div className="activity-meta">{actorLabel(item)}</div>
          </div>
          <time className="activity-time">{formatTime(item.created_at)}</time>
        </div>
      ))}
      {rows.length === 0 ? <div className="dashboard-empty-row">No activity</div> : null}
    </div>
  );
}
