import { useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBoxArchive, faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { AuthUser, Course, MembershipWithUser, Project, ProposalCallLibraryEntry, UserSuggestion } from "../types";
import { useStatusToast } from "../lib/useStatusToast";

type Props = {
  selectedProjectId: string;
  currentUser: AuthUser;
};

const PLATFORM_ROLES = ["super_admin", "project_creator", "user", "student"];
const PROJECT_ROLES = ["project_owner", "project_manager", "partner_lead", "partner_member", "reviewer", "viewer"];
type AdminTab = "projects" | "courses" | "calls" | "users" | "memberships" | "suggestions";

export function AdminPanel({ selectedProjectId, currentUser }: Props) {
  const [tab, setTab] = useState<AdminTab>("projects");
  const [projects, setProjects] = useState<Project[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [calls, setCalls] = useState<ProposalCallLibraryEntry[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [suggestions, setSuggestions] = useState<UserSuggestion[]>([]);
  const [memberships, setMemberships] = useState<MembershipWithUser[]>([]);
  const [search, setSearch] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [courseSearch, setCourseSearch] = useState("");
  const [callSearch, setCallSearch] = useState("");
  const [suggestionSearch, setSuggestionSearch] = useState("");
  const [suggestionStatusFilter, setSuggestionStatusFilter] = useState("");
  const [assignUserId, setAssignUserId] = useState("");
  const [assignRole, setAssignRole] = useState("viewer");
  const [createUserOpen, setCreateUserOpen] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPlatformRole, setNewPlatformRole] = useState("user");
  const [newIsActive, setNewIsActive] = useState(true);
  const [newCanAccessResearch, setNewCanAccessResearch] = useState(true);
  const [newCanAccessTeaching, setNewCanAccessTeaching] = useState(true);
  const [courseEditorOpen, setCourseEditorOpen] = useState(false);
  const [editingCourseId, setEditingCourseId] = useState<string | null>(null);
  const [courseCode, setCourseCode] = useState("");
  const [courseTitle, setCourseTitle] = useState("");
  const [courseDescription, setCourseDescription] = useState("");
  const [courseIsActive, setCourseIsActive] = useState(true);
  const [courseHasProjectDeadlines, setCourseHasProjectDeadlines] = useState(true);
  const [courseTeacherUserId, setCourseTeacherUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const { error, setError, status, setStatus } = useStatusToast();
  const [projectAction, setProjectAction] = useState<{ mode: "archive" | "delete"; project: Project } | null>(null);
  const [callAction, setCallAction] = useState<ProposalCallLibraryEntry | null>(null);
  const [courseAction, setCourseAction] = useState<Course | null>(null);

  const isSuperAdmin = currentUser.platform_role === "super_admin";
  const usersById = useMemo(() => Object.fromEntries(users.map((user) => [user.id, user])), [users]);
  const selectedProject = useMemo(
    () => projects.find((item) => item.id === selectedProjectId) || null,
    [projects, selectedProjectId]
  );
  const activeCourses = useMemo(() => courses.filter((item) => item.is_active).length, [courses]);
  const inactiveCourses = courses.length - activeCourses;

  useEffect(() => {
    if (!isSuperAdmin) return;
    void loadProjects();
    void loadCourses();
    void loadCalls();
    void loadUsers();
    void loadSuggestions();
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

  async function loadCourses(currentSearch = "") {
    try {
      setBusy(true);
      setError("");
      const response = await api.listCourses(1, 200, currentSearch, false);
      setCourses(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load courses.");
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

  async function loadSuggestions(currentSearch = suggestionSearch, currentStatus = suggestionStatusFilter) {
    try {
      setBusy(true);
      setError("");
      const response = await api.listUserSuggestions({
        page: 1,
        page_size: 100,
        search: currentSearch || undefined,
        status: currentStatus || undefined,
      });
      setSuggestions(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUserPatch(
    userId: string,
    payload: { display_name?: string; platform_role?: string; is_active?: boolean; can_access_research?: boolean; can_access_teaching?: boolean }
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
        can_access_research: newCanAccessResearch,
        can_access_teaching: newCanAccessTeaching,
      });
      setUsers((prev) => [created, ...prev]);
      setCreateUserOpen(false);
      setNewEmail("");
      setNewDisplayName("");
      setNewPassword("");
      setNewPlatformRole("user");
      setNewIsActive(true);
      setNewCanAccessResearch(true);
      setNewCanAccessTeaching(true);
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

  function openCreateCourse() {
    setEditingCourseId(null);
    setCourseCode("");
    setCourseTitle("");
    setCourseDescription("");
    setCourseIsActive(true);
    setCourseHasProjectDeadlines(true);
    setCourseTeacherUserId("");
    setCourseEditorOpen(true);
  }

  function openEditCourse(course: Course) {
    setEditingCourseId(course.id);
    setCourseCode(course.code);
    setCourseTitle(course.title);
    setCourseDescription(course.description || "");
    setCourseIsActive(course.is_active);
    setCourseHasProjectDeadlines(course.has_project_deadlines);
    setCourseTeacherUserId(course.teacher?.user_id || "");
    setCourseEditorOpen(true);
  }

  async function handleSaveCourse() {
    try {
      setBusy(true);
      setError("");
      if (editingCourseId) {
        const updated = await api.updateCourse(editingCourseId, {
          code: courseCode,
          title: courseTitle,
          description: courseDescription || null,
          is_active: courseIsActive,
          has_project_deadlines: courseHasProjectDeadlines,
          teacher_user_id: courseTeacherUserId || null,
        });
        setCourses((prev) => prev.map((item) => item.id === updated.id ? updated : item));
        setStatus("Course saved.");
      } else {
        const created = await api.createCourse({
          code: courseCode,
          title: courseTitle,
          description: courseDescription || null,
          is_active: courseIsActive,
          has_project_deadlines: courseHasProjectDeadlines,
          teacher_user_id: courseTeacherUserId || null,
        });
        setCourses((prev) => [created, ...prev]);
        setStatus("Course created.");
      }
      setCourseEditorOpen(false);
      setEditingCourseId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save course.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteCourse(course: Course) {
    try {
      setBusy(true);
      setError("");
      await api.deleteCourse(course.id);
      setCourses((prev) => prev.filter((item) => item.id !== course.id));
      setCourseAction(null);
      setStatus("Course deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete course.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSuggestionStatus(suggestionId: string, status: string) {
    try {
      setError("");
      const updated = await api.updateUserSuggestion(suggestionId, { status });
      setSuggestions((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setStatus("Suggestion updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update suggestion.");
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
    <section className="panel admin-panel-shell">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      <div className="setup-summary-bar admin-summary-bar">
        <div className="setup-summary-stats">
          <span>{projects.length} projects</span>
          <span className="setup-summary-sep" />
          <span>{courses.length} courses</span>
          <span className="setup-summary-sep" />
          <span>{users.length} users</span>
          <span className="setup-summary-sep" />
          <span>{suggestions.length} suggestions</span>
          <span className="setup-summary-sep" />
          <span>{selectedProject ? selectedProject.code : "No project"}</span>
        </div>
      </div>

      <div className="delivery-tabs">
        <button type="button" className={`delivery-tab ${tab === "projects" ? "active" : ""}`} onClick={() => setTab("projects")}>
          Projects
          <span className="delivery-tab-count">{projects.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "courses" ? "active" : ""}`} onClick={() => setTab("courses")}>
          Courses
          <span className="delivery-tab-count">{courses.length}</span>
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
        <button type="button" className={`delivery-tab ${tab === "suggestions" ? "active" : ""}`} onClick={() => setTab("suggestions")}>
          Suggestions
          <span className="delivery-tab-count">{suggestions.length}</span>
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

        {tab === "courses" ? (
          <div className="admin-course-layout">
            <div className="admin-course-metrics">
              <div className="admin-metric-card">
                <span className="admin-metric-label">Courses</span>
                <strong>{courses.length}</strong>
              </div>
              <div className="admin-metric-card">
                <span className="admin-metric-label">Active</span>
                <strong>{activeCourses}</strong>
              </div>
              <div className="admin-metric-card">
                <span className="admin-metric-label">Inactive</span>
                <strong>{inactiveCourses}</strong>
              </div>
            </div>

            <div className="card admin-course-card">
              <div className="workpane-head">
                <h3>Courses</h3>
                <div className="workpane-actions">
                  <div className="admin-search">
                    <input value={courseSearch} onChange={(event) => setCourseSearch(event.target.value)} placeholder="Search course" />
                    <button type="button" className="ghost" disabled={busy} onClick={() => void loadCourses(courseSearch)}>
                      Search
                    </button>
                  </div>
                  <button type="button" onClick={openCreateCourse}>
                    <FontAwesomeIcon icon={faPlus} />
                    <span>New Course</span>
                  </button>
                </div>
              </div>

              <div className="simple-table-wrap">
                <table className="simple-table compact-table">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Title</th>
                      <th>Teacher</th>
                      <th>Deadlines</th>
                      <th>Active</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {courses.map((course) => (
                      <tr key={course.id}>
                        <td><strong>{course.code}</strong></td>
                        <td>{course.title}</td>
                        <td>{course.teacher?.display_name || "-"}</td>
                        <td><span className="chip small">{course.has_project_deadlines ? "enabled" : "disabled"}</span></td>
                        <td><span className="chip small">{course.is_active ? "active" : "inactive"}</span></td>
                        <td>
                          <div className="table-row-actions">
                            <button type="button" className="ghost small" onClick={() => openEditCourse(course)}>
                              Edit
                            </button>
                            <button type="button" className="ghost small danger" onClick={() => setCourseAction(course)}>
                              <FontAwesomeIcon icon={faTrash} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {courses.length === 0 ? (
                      <tr><td colSpan={6}>No courses found.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
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
                    <th>Research</th>
                    <th>Teaching</th>
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
                          checked={user.can_access_research}
                          onChange={(event) => void handleUserPatch(user.id, { can_access_research: event.target.checked })}
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={user.can_access_teaching}
                          onChange={(event) => void handleUserPatch(user.id, { can_access_teaching: event.target.checked })}
                        />
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
                      <td colSpan={6}>No users found.</td>
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

        {tab === "suggestions" ? (
          <div className="card">
            <div className="meetings-toolbar">
              <div className="meetings-filter-group">
                <select value={suggestionStatusFilter} onChange={(event) => setSuggestionStatusFilter(event.target.value)}>
                  <option value="">All statuses</option>
                  <option value="new">New</option>
                  <option value="doing">Doing</option>
                  <option value="done">Done</option>
                  <option value="rejected">Rejected</option>
                </select>
                <input value={suggestionSearch} onChange={(event) => setSuggestionSearch(event.target.value)} placeholder="Search suggestion" className="meetings-search" />
                <button type="button" className="ghost" disabled={busy} onClick={() => void loadSuggestions()}>
                  Search
                </button>
              </div>
            </div>

            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Type</th>
                    <th>Suggestion</th>
                    <th>Date</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {suggestions.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.user_display_name}</strong>
                        <span className="muted-small research-inline-meta">{item.user_email}</span>
                      </td>
                      <td><span className={`suggestion-category-badge ${item.category || "feature"}`}>{item.category || "feature"}</span></td>
                      <td>{item.content}</td>
                      <td>{new Date(item.created_at).toLocaleString()}</td>
                      <td>
                        <select value={item.status} onChange={(event) => void handleSuggestionStatus(item.id, event.target.value)}>
                          <option value="new">New</option>
                          <option value="doing">Doing</option>
                          <option value="done">Done</option>
                          <option value="rejected">Rejected</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                  {suggestions.length === 0 ? (
                    <tr><td colSpan={5}>No suggestions found.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
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
              <label className="checkbox-field">
                <input type="checkbox" checked={newCanAccessResearch} onChange={(event) => setNewCanAccessResearch(event.target.checked)} />
                <span>Research</span>
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={newCanAccessTeaching} onChange={(event) => setNewCanAccessTeaching(event.target.checked)} />
                <span>Teaching</span>
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
      {courseEditorOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
            <div className="modal-card admin-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !busy && courseCode.trim() && courseTitle.trim()) { e.preventDefault(); void handleSaveCourse(); } }}>
              <div className="modal-head">
                <h3>{editingCourseId ? "Edit Course" : "New Course"}</h3>
                <button type="button" className="ghost" onClick={() => setCourseEditorOpen(false)}>
                  Close
                </button>
              </div>
              <div className="form-grid">
                <label>
                  Code
                  <input value={courseCode} onChange={(event) => setCourseCode(event.target.value)} />
                </label>
                <label>
                  Title
                  <input value={courseTitle} onChange={(event) => setCourseTitle(event.target.value)} />
                </label>
                <label className="full-span">
                  Teacher
                  <select value={courseTeacherUserId} onChange={(event) => setCourseTeacherUserId(event.target.value)}>
                    <option value="">Select</option>
                    {users.map((user) => (
                      <option key={user.id} value={user.id}>{user.display_name} · {user.email}</option>
                    ))}
                  </select>
                </label>
                <label className="full-span">
                  Description
                  <textarea rows={4} value={courseDescription} onChange={(event) => setCourseDescription(event.target.value)} />
                </label>
                <label className="checkbox-field">
                  <input type="checkbox" checked={courseIsActive} onChange={(event) => setCourseIsActive(event.target.checked)} />
                  <span>Active</span>
                </label>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={courseHasProjectDeadlines}
                    onChange={(event) => setCourseHasProjectDeadlines(event.target.checked)}
                  />
                  <span>Projects Have Deadlines</span>
                </label>
              </div>
              <div className="row-actions">
                <button type="button" disabled={busy || !courseCode.trim() || !courseTitle.trim()} onClick={() => void handleSaveCourse()}>
                  {editingCourseId ? "Save Course" : "Create Course"}
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
      {courseAction ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setCourseAction(null); }}>
          <FocusLock returnFocus>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>Delete Course</h3>
                <button type="button" className="ghost" onClick={() => setCourseAction(null)}>
                  Close
                </button>
              </div>
              <div className="project-confirm-body">
                <strong>{courseAction.code}</strong>
                <span>{courseAction.title}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setCourseAction(null)} disabled={busy}>
                  Cancel
                </button>
                <button type="button" className="danger" disabled={busy} onClick={() => void handleDeleteCourse(courseAction)}>
                  Delete
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
