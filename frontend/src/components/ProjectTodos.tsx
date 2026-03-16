import { useEffect, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheck,
  faPlus,
  faTrash,
  faUndo,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type { Member, ProjectTodo } from "../types";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "In Progress" },
  { value: "done", label: "Done" },
  { value: "dismissed", label: "Dismissed" },
];

const PRIORITY_OPTIONS = ["low", "normal", "high", "urgent"];

export function ProjectTodos({ selectedProjectId }: { selectedProjectId: string }) {
  const [todos, setTodos] = useState<ProjectTodo[]>([]);
  const [total, setTotal] = useState(0);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newAssignee, setNewAssignee] = useState("");
  const [newPriority, setNewPriority] = useState("normal");
  const [newDueDate, setNewDueDate] = useState("");
  const [creating, setCreating] = useState(false);

  const memberMap = new Map(members.map((m) => [m.id, m]));
  const doneCount = todos.filter((t) => t.status === "done").length;
  const pendingCount = todos.filter((t) => t.status === "pending" || t.status === "in_progress").length;

  async function loadMembers() {
    if (!selectedProjectId) return;
    try {
      const res = await api.listMembers(selectedProjectId);
      setMembers(res.items.filter((m) => m.is_active));
    } catch { /* non-fatal */ }
  }

  async function load() {
    if (!selectedProjectId) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.listTodos(selectedProjectId, {
        status: statusFilter || undefined,
        page_size: 100,
      });
      setTodos(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load todos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadMembers(); }, [selectedProjectId]);
  useEffect(() => { void load(); }, [selectedProjectId, statusFilter]);
  useAutoRefresh(() => { void load(); });

  function openModal() {
    setNewTitle("");
    setNewDescription("");
    setNewAssignee("");
    setNewPriority("normal");
    setNewDueDate("");
    setModalOpen(true);
  }

  async function handleCreate() {
    const title = newTitle.trim();
    if (!title || !selectedProjectId) return;
    setCreating(true);
    try {
      await api.createTodo(selectedProjectId, {
        title,
        description: newDescription.trim() || null,
        assignee_member_id: newAssignee || null,
        priority: newPriority,
        due_date: newDueDate || null,
      });
      setModalOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create todo.");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggle(todo: ProjectTodo) {
    const nextStatus = todo.status === "done" || todo.status === "dismissed" ? "pending" : "done";
    try {
      await api.updateTodo(selectedProjectId, todo.id, { status: nextStatus });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update todo.");
    }
  }

  async function handleAssign(todo: ProjectTodo, memberId: string) {
    try {
      await api.updateTodo(selectedProjectId, todo.id, { assignee_member_id: memberId || null });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign todo.");
    }
  }

  async function handleDelete(todo: ProjectTodo) {
    try {
      await api.deleteTodo(selectedProjectId, todo.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete todo.");
    }
  }

  if (!selectedProjectId) {
    return <p className="empty-message">Select a project to manage todos.</p>;
  }

  return (
    <>
      {error ? <p className="error">{error}</p> : null}

      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span>{total} todos</span>
          <span className="setup-summary-sep" />
          <span>{pendingCount} open</span>
          <span className="setup-summary-sep" />
          <span>{doneCount} done</span>
        </div>
        <button type="button" className="meetings-new-btn" onClick={openModal}>
          <FontAwesomeIcon icon={faPlus} /> New Todo
        </button>
      </div>

      {/* Toolbar */}
      <div className="meetings-toolbar">
        <div className="meetings-filter-group">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      {loading ? <p className="muted-small">Loading...</p> : null}

      {!loading && todos.length === 0 ? (
        <p className="muted-small empty-message">No todos yet.</p>
      ) : null}

      {!loading && todos.length > 0 ? (
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th className="col-icon"></th>
                <th>Title</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Assignee</th>
                <th>Due</th>
                <th className="col-icon"></th>
              </tr>
            </thead>
            <tbody>
              {todos.map((todo) => {
                const isDone = todo.status === "done" || todo.status === "dismissed";
                const overdue = !isDone && todo.due_date && new Date(todo.due_date) < new Date(new Date().toISOString().slice(0, 10));
                const member = todo.assignee_member_id ? memberMap.get(todo.assignee_member_id) : null;
                return (
                  <tr key={todo.id} className={isDone ? "todo-row-done" : ""}>
                    <td>
                      <button
                        type="button"
                        className="ghost docs-action-btn"
                        title={isDone ? "Restore" : "Mark done"}
                        onClick={() => handleToggle(todo)}
                      >
                        <FontAwesomeIcon icon={isDone ? faUndo : faCheck} />
                      </button>
                    </td>
                    <td>
                      <strong className={isDone ? "todo-title-done" : ""}>
                        {todo.title}
                      </strong>
                      {todo.description ? (
                        <span className="muted-small todo-desc">{todo.description}</span>
                      ) : null}
                    </td>
                    <td>
                      <span className={`chip small ${todo.priority === "urgent" ? "status-danger" : todo.priority === "high" ? "status-warning" : ""}`}>
                        {todo.priority}
                      </span>
                    </td>
                    <td>
                      <span className={`chip small ${todo.status === "done" ? "status-ok" : todo.status === "in_progress" ? "status-active" : ""}`}>
                        {todo.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td>
                      <select
                        value={todo.assignee_member_id ?? ""}
                        onChange={(e) => handleAssign(todo, e.target.value)}
                      >
                        <option value="">Unassigned</option>
                        {members.map((m) => (
                          <option key={m.id} value={m.id}>{m.full_name}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {todo.due_date ? (
                        <span className={overdue ? "todo-due-overdue" : ""}>
                          {todo.due_date}
                        </span>
                      ) : (
                        <span className="muted-small">—</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="ghost docs-action-btn"
                        title="Delete"
                        onClick={() => handleDelete(todo)}
                      >
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* Create modal */}
      {modalOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setModalOpen(false); }}>
          <FocusLock returnFocus>
          <div className="modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !creating && newTitle.trim()) { e.preventDefault(); void handleCreate(); } }}>
            <div className="modal-head">
              <h3>New Todo</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setModalOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label className="full-span">
                Title
                <input
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="What needs to be done?"
                  autoFocus
                />
              </label>
              <label className="full-span">
                Description
                <textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Optional details..."
                  rows={3}
                />
              </label>
              <label>
                Assignee
                <select value={newAssignee} onChange={(e) => setNewAssignee(e.target.value)}>
                  <option value="">Unassigned</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>{m.full_name}</option>
                  ))}
                </select>
              </label>
              <label>
                Priority
                <select value={newPriority} onChange={(e) => setNewPriority(e.target.value)}>
                  {PRIORITY_OPTIONS.map((p) => (
                    <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                  ))}
                </select>
              </label>
              <label>
                Due date
                <input type="date" value={newDueDate} onChange={(e) => setNewDueDate(e.target.value)} />
              </label>
            </div>
            <div className="row-actions">
              <button type="button" disabled={creating || !newTitle.trim()} onClick={() => void handleCreate()}>
                {creating ? "Creating..." : "Create Todo"}
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}
    </>
  );
}
