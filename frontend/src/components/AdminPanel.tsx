import { useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBoxArchive, faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { AuthUser, MembershipWithUser, Project, ProposalCallLibraryEntry } from "../types";

type Props = {
  selectedProjectId: string;
  currentUser: AuthUser;
};

const PLATFORM_ROLES = ["super_admin", "project_creator", "user"];
const PROJECT_ROLES = ["project_owner", "project_manager", "partner_lead", "partner_member", "reviewer", "viewer"];
type AdminTab = "projects" | "calls" | "users" | "memberships";

export function AdminPanel({ selectedProjectId, currentUser }: Props) {
  const [tab, setTab] = useState<AdminTab>("projects");
  const [projects, setProjects] = useState<Project[]>([]);
  const [calls, setCalls] = useState<ProposalCallLibraryEntry[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [memberships, setMemberships] = useState<MembershipWithUser[]>([]);
  const [search, setSearch] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [callSearch, setCallSearch] = useState("");
  const [assignUserId, setAssignUserId] = useState("");
  const [assignRole, setAssignRole] = useState("viewer");
  const [createUserOpen, setCreateUserOpen] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPlatformRole, setNewPlatformRole] = useState("user");
  const [newIsActive, setNewIsActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [projectAction, setProjectAction] = useState<{ mode: "archive" | "delete"; project: Project } | null>(null);
  const [callAction, setCallAction] = useState<ProposalCallLibraryEntry | null>(null);

  const isSuperAdmin = currentUser.platform_role === "super_admin";
  const usersById = useMemo(() => Object.fromEntries(users.map((user) => [user.id, user])), [users]);
  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedProjectId) || null,
    [projects, selectedProjectId]
  );

  useEffect(() => {
    if (!isSuperAdmin) return;
    void loadProjects();
    void loadCalls();
    void loadUsers();
  }, [isSuperAdmin]);

  useEffect(() => {
    if (!isSuperAdmin || !selectedProjectId) {
      setMemberships([]);
      return;
    }
    void loadProjectMemberships(selectedProjectId);
  }, [isSuperAdmin, selectedProjectId]);

  async function loadUsers(currentSearch = "") {
    try {
      setBusy(true);
      setError("");
      const response = await api.listUsers(1, 200, currentSearch);
      setUsers(response.items);
      setAssignUserId((current) => current || response.items[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setBusy(false);
    }
  }

  async function loadProjects(currentSearch = "") {
    try {
      setBusy(true);
      setError("");
      const response = await api.listProjects(1, 100);
      const filtered = currentSearch.trim()
        ? response.items.filter((item) =>
            [item.code, item.title, item.status, item.project_mode].some((value) =>
              String(value || "").toLowerCase().includes(currentSearch.trim().toLowerCase())
            )
          )
        : response.items;
      setProjects(filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects.");
    } finally {
      setBusy(false);
    }
  }

  async function loadCalls(currentSearch = "") {
    try {
      setBusy(true);
      setError("");
      const response = await api.listProposalCallLibrary(currentSearch, false);
      setCalls(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calls.");
    } finally {
      setBusy(false);
    }
  }

  async function loadProjectMemberships(projectId: string) {
    try {
      setBusy(true);
      setError("");
      const response = await api.listProjectMembershipsWithUsers(projectId);
      setMemberships(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project memberships.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUserPatch(
    userId: string,
    payload: { display_name?: string; platform_role?: string; is_active?: boolean }
  ) {
    try {
      setError("");
      const updated = await api.updateUser(userId, payload);
      setUsers((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user.");
    }
  }

  async function handleAssignMembership(userId = assignUserId, role = assignRole) {
    if (!selectedProjectId || !userId || !role) return;
    try {
      setError("");
      const updated = await api.upsertProjectMembership(selectedProjectId, { user_id: userId, role });
      setMemberships((prev) => {
        const user = usersById[updated.user_id];
        if (!user) return prev;
        const idx = prev.findIndex((item) => item.membership.user_id === updated.user_id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...next[idx], membership: updated };
          return next;
        }
        return [...prev, { membership: updated, user }];
      });
      setStatus("Membership saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign membership.");
    }
  }

  async function handleCreateUser() {
    try {
      setBusy(true);
      setError("");
      const created = await api.createUser({
        email: newEmail,
        display_name: newDisplayName,
        password: newPassword || undefined,
        platform_role: newPlatformRole,
        is_active: newIsActive,
      });
      setUsers((prev) => [created, ...prev]);
      setCreateUserOpen(false);
      setNewEmail("");
      setNewDisplayName("");
      setNewPassword("");
      setNewPlatformRole("user");
      setNewIsActive(true);
      setAssignUserId(created.id);
      setStatus(
        created.temporary_password
          ? `User created. Temporary password: ${created.temporary_password}`
          : "User created."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user.");
    } finally {
      setBusy(false);
    }
  }

  async function handleArchiveProject(project: Project) {
    try {
      setBusy(true);
      setError("");
      const archived = await api.archiveProject(project.id);
      setProjects((prev) => prev.map((item) => (item.id === archived.id ? archived : item)));
      setProjectAction(null);
      setStatus("Project archived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive project.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteProject(project: Project) {
    try {
      setBusy(true);
      setError("");
      await api.deleteProject(project.id);
      setProjects((prev) => prev.filter((item) => item.id !== project.id));
      setMemberships((prev) => prev.filter((item) => item.membership.project_id !== project.id));
      setProjectAction(null);
      setStatus("Project deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete project.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteCall(call: ProposalCallLibraryEntry) {
    try {
      setBusy(true);
      setError("");
      await api.deleteProposalCallLibraryEntry(call.id);
      setCalls((prev) => prev.filter((item) => item.id !== call.id));
      setCallAction(null);
      setStatus("Call deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete call.");
    } finally {
      setBusy(false);
    }
  }

  if (!isSuperAdmin) {
    return (
      <section className="panel">
        <p className="muted-small">Restricted to administrators.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span>{projects.length} projects</span>
          <span className="setup-summary-sep" />
          <span>{users.length} users</span>
          <span className="setup-summary-sep" />
          <span>{selectedProject ? selectedProject.code : "No project"}</span>
        </div>
      </div>

      <div className="delivery-tabs">
        <button type="button" className={`delivery-tab ${tab === "projects" ? "active" : ""}`} onClick={() => setTab("projects")}>
          Projects
          <span className="delivery-tab-count">{projects.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>
          Users
          <span className="delivery-tab-count">{users.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "calls" ? "active" : ""}`} onClick={() => setTab("calls")}>
          Calls
          <span className="delivery-tab-count">{calls.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "memberships" ? "active" : ""}`} onClick={() => setTab("memberships")}>
          Memberships
          <span className="delivery-tab-count">{memberships.length}</span>
        </button>
      </div>

      <div className="setup-section-content">
        {tab === "projects" ? (
          <div className="card">
            <div className="meetings-toolbar">
              <div className="meetings-filter-group">
                <input value={projectSearch} onChange={(event) => setProjectSearch(event.target.value)} placeholder="Search project" className="meetings-search" />
                <button type="button" className="ghost" disabled={busy} onClick={() => void loadProjects(projectSearch)}>
                  Search
                </button>
              </div>
            </div>

            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Title</th>
                    <th>Mode</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project) => (
                    <tr key={project.id}>
                      <td><strong>{project.code}</strong></td>
                      <td>{project.title}</td>
                      <td><span className="chip small">{project.project_mode}</span></td>
                      <td><span className="chip small">{project.status}</span></td>
                      <td>
                        <div className="table-row-actions">
                          <button type="button" className="ghost small" onClick={() => setProjectAction({ mode: "archive", project })}>
                            <FontAwesomeIcon icon={faBoxArchive} />
                          </button>
                          <button type="button" className="ghost small danger" onClick={() => setProjectAction({ mode: "delete", project })}>
                            <FontAwesomeIcon icon={faTrash} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {projects.length === 0 ? (
                    <tr><td colSpan={5}>No projects found.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {tab === "calls" ? (
          <div className="card">
            <div className="meetings-toolbar">
              <div className="meetings-filter-group">
                <input value={callSearch} onChange={(event) => setCallSearch(event.target.value)} placeholder="Search call" className="meetings-search" />
                <button type="button" className="ghost" disabled={busy} onClick={() => void loadCalls(callSearch)}>
                  Search
                </button>
              </div>
            </div>

            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Reference</th>
                    <th>Programme</th>
                    <th>Deadline</th>
                    <th>Version</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {calls.map((call) => (
                    <tr key={call.id}>
                      <td><strong>{call.call_title}</strong></td>
                      <td>{call.reference_code || "-"}</td>
                      <td>{call.programme_name || "-"}</td>
                      <td>{call.submission_deadline || "-"}</td>
                      <td>v{call.version}</td>
                      <td>
                        <div className="table-row-actions">
                          <button type="button" className="ghost small danger" onClick={() => setCallAction(call)}>
                            <FontAwesomeIcon icon={faTrash} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {calls.length === 0 ? (
                    <tr><td colSpan={6}>No calls found.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {tab === "users" ? (
          <div className="card">
            <div className="workpane-head">
              <h3>Users</h3>
              <div className="workpane-actions">
                <div className="admin-search">
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search user" />
                  <button type="button" className="ghost" disabled={busy} onClick={() => void loadUsers(search)}>
                    Search
                  </button>
                </div>
                <button type="button" onClick={() => setCreateUserOpen(true)}>
                  <FontAwesomeIcon icon={faPlus} />
                  <span>New User</span>
                </button>
              </div>
            </div>

            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Name</th>
                    <th>Platform Role</th>
                    <th>Active</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.email}</td>
                      <td>
                        <input
                          value={user.display_name}
                          onChange={(event) =>
                            setUsers((prev) =>
                              prev.map((item) => (item.id === user.id ? { ...item, display_name: event.target.value } : item))
                            )
                          }
                          onBlur={() => void handleUserPatch(user.id, { display_name: user.display_name })}
                        />
                      </td>
                      <td>
                        <select
                          value={user.platform_role}
                          onChange={(event) => void handleUserPatch(user.id, { platform_role: event.target.value })}
                        >
                          {PLATFORM_ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={user.is_active}
                          onChange={(event) => void handleUserPatch(user.id, { is_active: event.target.checked })}
                        />
                      </td>
                    </tr>
                  ))}
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={4}>No users found.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {tab === "memberships" ? (
          <div className="card">
            <div className="workpane-head">
              <h3>Memberships</h3>
            </div>

            {selectedProjectId ? (
              <>
                <div className="admin-membership-form">
                  <label>
                    User
                    <select value={assignUserId} onChange={(event) => setAssignUserId(event.target.value)}>
                      {users.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.display_name} · {user.email}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Role
                    <select value={assignRole} onChange={(event) => setAssignRole(event.target.value)}>
                      {PROJECT_ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" disabled={!assignUserId || !assignRole} onClick={() => void handleAssignMembership()}>
                    Save Membership
                  </button>
                </div>

                <div className="simple-table-wrap">
                  <table className="simple-table compact-table">
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Email</th>
                        <th>Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {memberships.map((item) => (
                        <tr key={item.membership.id}>
                          <td>{item.user.display_name}</td>
                          <td>{item.user.email}</td>
                          <td>
                            <select
                              value={item.membership.role}
                              onChange={(event) => void handleAssignMembership(item.user.id, event.target.value)}
                            >
                              {PROJECT_ROLES.map((role) => (
                                <option key={role} value={role}>
                                  {role}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      ))}
                      {memberships.length === 0 ? (
                        <tr>
                          <td colSpan={3}>No memberships for this project.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="card-slab">Select a project.</div>
            )}
          </div>
        ) : null}
      </div>

      {createUserOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card admin-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !busy && newEmail.trim() && newDisplayName.trim()) { e.preventDefault(); void handleCreateUser(); } }}>
            <div className="modal-head">
              <h3>New User</h3>
              <button type="button" className="ghost" onClick={() => setCreateUserOpen(false)}>
                Close
              </button>
            </div>
            <div className="form-grid">
              <label>
                Email
                <input value={newEmail} onChange={(event) => setNewEmail(event.target.value)} />
              </label>
              <label>
                Name
                <input value={newDisplayName} onChange={(event) => setNewDisplayName(event.target.value)} />
              </label>
              <label>
                Password
                <input value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
              </label>
              <label>
                Platform Role
                <select value={newPlatformRole} onChange={(event) => setNewPlatformRole(event.target.value)}>
                  {PLATFORM_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={newIsActive} onChange={(event) => setNewIsActive(event.target.checked)} />
                <span>Active</span>
              </label>
            </div>
            <div className="row-actions">
              <button
                type="button"
                disabled={busy || !newEmail.trim() || !newDisplayName.trim()}
                onClick={() => void handleCreateUser()}
              >
                Create User
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}
      {projectAction ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setProjectAction(null); }}>
          <FocusLock returnFocus>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>{projectAction.mode === "archive" ? "Archive Project" : "Delete Project"}</h3>
                <button type="button" className="ghost" onClick={() => setProjectAction(null)}>
                  Close
                </button>
              </div>
              <div className="project-confirm-body">
                <strong>{projectAction.project.code}</strong>
                <span>{projectAction.project.title}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setProjectAction(null)} disabled={busy}>
                  Cancel
                </button>
                <button
                  type="button"
                  className={projectAction.mode === "delete" ? "danger" : ""}
                  disabled={busy}
                  onClick={() => void (projectAction.mode === "archive"
                    ? handleArchiveProject(projectAction.project)
                    : handleDeleteProject(projectAction.project))}
                >
                  {projectAction.mode === "archive" ? "Archive" : "Delete"}
                </button>
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}
      {callAction ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setCallAction(null); }}>
          <FocusLock returnFocus>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>Delete Call</h3>
                <button type="button" className="ghost" onClick={() => setCallAction(null)}>
                  Close
                </button>
              </div>
              <div className="project-confirm-body">
                <strong>{callAction.call_title}</strong>
                <span>{callAction.reference_code || callAction.programme_name || "Repository call"}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setCallAction(null)} disabled={busy}>
                  Cancel
                </button>
                <button type="button" className="danger" disabled={busy} onClick={() => void handleDeleteCall(callAction)}>
                  Delete
                </button>
              </div>
            </div>
          </FocusLock>
        </div>
      ) : null}
    </section>
  );
}
