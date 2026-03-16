import { useEffect, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBox,
  faCheckCircle,
  faClipboardList,
  faExclamationTriangle,
  faFileAlt,
  faFlag,
  faInbox,
  faListCheck,
  faChevronDown,
  faChevronRight,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type { MyWorkItem, MyWorkProjectGroup, MyWorkResponse } from "../types";

const ITEM_TYPE_ICONS: Record<string, typeof faBox> = {
  work_package: faBox,
  task: faListCheck,
  milestone: faFlag,
  deliverable: faFileAlt,
  action_item: faClipboardList,
  inbox_item: faInbox,
  review_deliverable: faCheckCircle,
  review_proposal_section: faFileAlt,
  todo: faListCheck,
};

const ITEM_TYPE_LABELS: Record<string, string> = {
  work_package: "WP",
  task: "Task",
  milestone: "Milestone",
  deliverable: "Deliverable",
  action_item: "Action Item",
  inbox_item: "Inbox",
  review_deliverable: "Review",
  review_proposal_section: "Review",
  todo: "Todo",
};

function isOverdue(dueDate: string | null): boolean {
  if (!dueDate) return false;
  return new Date(dueDate) < new Date(new Date().toISOString().slice(0, 10));
}

function statusChipClass(status: string): string {
  if (status === "closed" || status === "done" || status === "approved" || status === "submitted") return "status-ok";
  if (status === "blocked" || status === "changes_requested") return "status-danger";
  if (status === "in_progress" || status === "in_review") return "status-active";
  return "";
}

function ItemRow({ item }: { item: MyWorkItem }) {
  const icon = ITEM_TYPE_ICONS[item.item_type] ?? faBox;
  const typeLabel = ITEM_TYPE_LABELS[item.item_type] ?? item.item_type;
  const overdue = isOverdue(item.due_date);

  return (
    <div className="mw-item">
      <FontAwesomeIcon icon={icon} className="mw-item-icon" title={typeLabel} />
      <span className="mw-item-type">{typeLabel}</span>
      {item.code ? <span className="mw-item-code">{item.code}</span> : null}
      <span className="mw-item-title">{item.title}</span>
      <span className={`chip small ${statusChipClass(item.status)}`}>
        {item.status.replace(/_/g, " ")}
      </span>
      <span className={`mw-role-badge ${item.role}`}>{item.role}</span>
      {item.due_date ? (
        <span className={`mw-item-due ${overdue ? "overdue" : ""}`}>
          {overdue ? "Overdue " : ""}
          {item.due_date}
        </span>
      ) : (
        <span className="mw-item-due-spacer" />
      )}
    </div>
  );
}

function ProjectGroup({ group }: { group: MyWorkProjectGroup }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="mw-group">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="mw-group-header"
      >
        <FontAwesomeIcon icon={expanded ? faChevronDown : faChevronRight} className="mw-group-chevron" />
        <strong>{group.project_code}</strong>
        <span>{group.project_title}</span>
        <span className="mw-group-count">{group.items.length}</span>
        <span className={`mw-group-mode ${group.project_mode}`}>{group.project_mode}</span>
      </button>
      {expanded ? (
        <div>
          {group.items.map((item) => (
            <ItemRow key={`${item.item_type}-${item.entity_id}`} item={item} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function MyWork() {
  const [data, setData] = useState<MyWorkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [includeClosed, setIncludeClosed] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await api.getMyWork(includeClosed);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load My Work.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [includeClosed]);

  useAutoRefresh(() => { void load(); });

  return (
    <div className="mw-container">
      <div className="mw-toolbar">
        <div className="mw-toolbar-left">
          {data ? (
            <span className="mw-count">
              {data.total_items} item{data.total_items !== 1 ? "s" : ""}
            </span>
          ) : null}
        </div>
        <label className="mw-toggle">
          <input
            type="checkbox"
            checked={includeClosed}
            onChange={(e) => setIncludeClosed(e.target.checked)}
          />
          Show closed
        </label>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {loading ? <p className="muted-small">Loading...</p> : null}

      {!loading && data && data.groups.length === 0 ? (
        <div className="mw-empty">
          <FontAwesomeIcon icon={faExclamationTriangle} />
          No items assigned to you
        </div>
      ) : null}

      {!loading && data
        ? data.groups.map((group) => (
            <ProjectGroup key={group.project_id} group={group} />
          ))
        : null}
    </div>
  );
}
