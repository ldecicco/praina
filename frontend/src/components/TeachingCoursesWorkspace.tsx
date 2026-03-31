import { useCallback, useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRight,
  faArrowUpRightFromSquare,
  faChevronDown,
  faChevronUp,
  faPenToSquare,
  faPlus,
  faTrash,
  faTriangleExclamation,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { renderMarkdown } from "../lib/renderMarkdown";
import { ProposalRichEditor } from "./ProposalRichEditor";
import { renderHealthIndicator } from "./TeachingHealthIndicator";
import type { AuthUser, Course, CourseMaterial, Project, TeachingWorkspace } from "../types";
import { useStatusToast } from "../lib/useStatusToast";

type Props = {
  currentUser: AuthUser;
  onOpenProject: (projectId: string) => void;
};

type CourseProjectRow = {
  project: Project;
  workspace: TeachingWorkspace;
};

type CourseMaterialModal = "create" | "edit" | null;

const BATCH_SIZE = 6;

const MATERIAL_TYPE_ORDER = ["instructions", "rubric", "template", "schedule", "resource", "other"];

export function TeachingCoursesWorkspace({ currentUser, onOpenProject }: Props) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [courseProjects, setCourseProjects] = useState<CourseProjectRow[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [taUserId, setTaUserId] = useState("");
  const [materialModal, setMaterialModal] = useState<CourseMaterialModal>(null);
  const [editingMaterialId, setEditingMaterialId] = useState<string | null>(null);
  const [materialType, setMaterialType] = useState("instructions");
  const [materialTitle, setMaterialTitle] = useState("");
  const [materialContent, setMaterialContent] = useState("");
  const [materialUrl, setMaterialUrl] = useState("");
  const [materialSortOrder, setMaterialSortOrder] = useState("0");
  const [courseModal, setCourseModal] = useState(false);
  const [courseCode, setCourseCode] = useState("");
  const [courseTitle, setCourseTitle] = useState("");
  const [courseDescription, setCourseDescription] = useState("");
  const [courseIsActive, setCourseIsActive] = useState(true);
  const [courseHasDeadlines, setCourseHasDeadlines] = useState(false);
  const [courseTeacherUserId, setCourseTeacherUserId] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const { error, setError, status, setStatus } = useStatusToast();
  const [projectSearch, setProjectSearch] = useState("");
  const [expandedMaterials, setExpandedMaterials] = useState<Set<string>>(new Set());
  const [materialTypeFilter, setMaterialTypeFilter] = useState("");

  const loadWorkspace = useCallback(async () => {
    try {
      setLoading(true);
      const [courseResponse, projectResponse] = await Promise.all([
        api.listCourses(1, 200, "", false),
        api.listProjects(1, 100),
      ]);
      const teachingProjects = projectResponse.items.filter((item) => item.project_kind === "teaching");

      const workspaces: CourseProjectRow[] = [];
      for (let i = 0; i < teachingProjects.length; i += BATCH_SIZE) {
        const batch = teachingProjects.slice(i, i + BATCH_SIZE);
        const results = await Promise.all(
          batch.map(async (project) => ({
            project,
            workspace: await api.getTeachingWorkspace(project.id),
          }))
        );
        workspaces.push(...results);
      }

      setCourses(courseResponse.items);
      setCourseProjects(workspaces);
      setSelectedCourseId((current) => current || courseResponse.items[0]?.id || "");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load courses.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const response = await api.listUserDiscovery(1, 200, "");
      setUsers(response.items.filter((item) => item.is_active));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    }
  }, []);

  useEffect(() => {
    void loadWorkspace();
    void loadUsers();
  }, [loadWorkspace, loadUsers]);

  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(""), 3000);
    return () => clearTimeout(timer);
  }, [status]);

  function resetMaterialForm() {
    setEditingMaterialId(null);
    setMaterialType("instructions");
    setMaterialTitle("");
    setMaterialContent("");
    setMaterialUrl("");
    setMaterialSortOrder("0");
  }

  function openMaterialModal(mode: CourseMaterialModal, material?: CourseMaterial) {
    resetMaterialForm();
    setStatus("");
    setError("");
    setMaterialModal(mode);
    if (mode === "edit" && material) {
      setEditingMaterialId(material.id);
      setMaterialType(material.material_type);
      setMaterialTitle(material.title);
      setMaterialContent(material.content_markdown || "");
      setMaterialUrl(material.external_url || "");
      setMaterialSortOrder(String(material.sort_order));
    }
  }

  function openCourseModal() {
    if (!selectedCourse) return;
    setCourseCode(selectedCourse.code);
    setCourseTitle(selectedCourse.title);
    setCourseDescription(selectedCourse.description || "");
    setCourseIsActive(selectedCourse.is_active);
    setCourseHasDeadlines(selectedCourse.has_project_deadlines);
    setCourseTeacherUserId(selectedCourse.teacher?.user_id || "");
    setCourseModal(true);
  }

  async function handleSaveCourse() {
    if (!selectedCourseId || !courseCode.trim() || !courseTitle.trim()) return;
    try {
      setBusy(true);
      const updated = await api.updateCourse(selectedCourseId, {
        code: courseCode.trim(),
        title: courseTitle.trim(),
        description: courseDescription.trim() || null,
        is_active: courseIsActive,
        has_project_deadlines: courseHasDeadlines,
        teacher_user_id: courseTeacherUserId || null,
      });
      setCourses((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setCourseModal(false);
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save course.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddTeachingAssistant() {
    if (!selectedCourseId || !taUserId) return;
    try {
      setBusy(true);
      const updated = await api.addCourseTeachingAssistant(selectedCourseId, taUserId);
      setCourses((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setTaUserId("");
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add teaching assistant.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveTeachingAssistant(userId: string) {
    if (!selectedCourseId) return;
    if (!window.confirm("Remove this teaching assistant?")) return;
    try {
      setBusy(true);
      const updated = await api.removeCourseTeachingAssistant(selectedCourseId, userId);
      setCourses((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove teaching assistant.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveMaterial() {
    if (!selectedCourseId || !materialTitle.trim()) return;
    try {
      setBusy(true);
      const payload = {
        material_type: materialType,
        title: materialTitle.trim(),
        content_markdown: materialContent.trim() || null,
        external_url: materialUrl.trim() || null,
        sort_order: Number(materialSortOrder) || 0,
      };
      let materials: CourseMaterial[] = [];
      if (materialModal === "edit" && editingMaterialId) {
        const updated = await api.updateCourseMaterial(selectedCourseId, editingMaterialId, payload);
        materials = selectedCourseMaterials.map((item) => (item.id === updated.id ? updated : item));
      } else {
        const created = await api.createCourseMaterial(selectedCourseId, payload);
        materials = [...selectedCourseMaterials, created];
      }
      setCourses((current) =>
        current.map((item) =>
          item.id === selectedCourseId
            ? {
                ...item,
                materials: materials
                  .slice()
                  .sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title)),
              }
            : item
        )
      );
      setMaterialModal(null);
      resetMaterialForm();
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save course material.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteMaterial(materialId: string) {
    if (!selectedCourseId) return;
    if (!window.confirm("Delete this material? This cannot be undone.")) return;
    try {
      setBusy(true);
      await api.deleteCourseMaterial(selectedCourseId, materialId);
      setCourses((current) =>
        current.map((item) =>
          item.id === selectedCourseId
            ? { ...item, materials: item.materials.filter((material) => material.id !== materialId) }
            : item
        )
      );
      setStatus("Deleted.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete course material.");
    } finally {
      setBusy(false);
    }
  }

  function toggleMaterialExpanded(materialId: string) {
    setExpandedMaterials((current) => {
      const next = new Set(current);
      if (next.has(materialId)) next.delete(materialId);
      else next.add(materialId);
      return next;
    });
  }

  const selectedCourse = courses.find((item) => item.id === selectedCourseId) || null;
  const selectedCourseProjects = useMemo(
    () => courseProjects.filter((item) => item.workspace.profile.course_id === selectedCourseId),
    [courseProjects, selectedCourseId]
  );
  const selectedCourseMaterials = useMemo(
    () => (selectedCourse?.materials || []).slice().sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title)),
    [selectedCourse]
  );
  const materialTypes = useMemo(() => {
    const types = new Set(selectedCourseMaterials.map((item) => item.material_type));
    return MATERIAL_TYPE_ORDER.filter((type) => types.has(type));
  }, [selectedCourseMaterials]);
  const filteredMaterials = useMemo(
    () => materialTypeFilter ? selectedCourseMaterials.filter((item) => item.material_type === materialTypeFilter) : selectedCourseMaterials,
    [selectedCourseMaterials, materialTypeFilter]
  );
  const groupedMaterials = useMemo(() => {
    const groups: { type: string; items: CourseMaterial[] }[] = [];
    for (const material of filteredMaterials) {
      const last = groups[groups.length - 1];
      if (last && last.type === material.material_type) {
        last.items.push(material);
      } else {
        groups.push({ type: material.material_type, items: [material] });
      }
    }
    return groups;
  }, [filteredMaterials]);
  const openBlockers = selectedCourseProjects.reduce(
    (total, item) => total + item.workspace.blockers.filter((entry) => entry.status !== "resolved").length,
    0
  );
  const missingArtifacts = selectedCourseProjects.reduce(
    (total, item) => total + item.workspace.artifacts.filter((entry) => entry.required && entry.status === "missing").length,
    0
  );
  const atRiskProjects = selectedCourseProjects.filter((item) => item.workspace.profile.health !== "green").length;
  const activeCourses = courses.filter((item) => item.is_active).length;
  const canManageSelectedCourse = Boolean(
    selectedCourse &&
      (currentUser.platform_role === "super_admin" || selectedCourse.teacher?.user_id === currentUser.id)
  );
  const availableTaUsers = users
    .filter((item) => item.id !== selectedCourse?.teacher?.user_id)
    .filter((item) => !selectedCourse?.teaching_assistants.some((entry) => entry.user_id === item.id));
  const searchLower = projectSearch.toLowerCase();
  const filteredProjects = useMemo(
    () =>
      searchLower
        ? selectedCourseProjects.filter(
            (entry) =>
              entry.project.code.toLowerCase().includes(searchLower) ||
              entry.project.title.toLowerCase().includes(searchLower) ||
              (entry.workspace.profile.responsible_user?.display_name || "").toLowerCase().includes(searchLower)
          )
        : selectedCourseProjects,
    [selectedCourseProjects, searchLower]
  );

  if (loading) {
    return (
      <div className="teaching-workspace">
        <div className="setup-summary-bar">
          <div className="teaching-course-summary-left">
            <div className="setup-summary-stats"><span>Loading courses...</span></div>
          </div>
        </div>
      </div>
    );
  }

  if (!loading && courses.length === 0) {
    return (
      <div className="teaching-workspace">
        <div className="setup-summary-bar">
          <div className="teaching-course-summary-left">
            <div className="setup-summary-stats">
              <span>0 courses</span>
            </div>
          </div>
        </div>
        {error ? <p className="error">{error}</p> : null}
        <div className="card teaching-card teaching-empty-state">
          <strong>No courses yet</strong>
          <span>Courses can be created from the Admin panel. Once a course exists, it will appear here along with its linked teaching projects.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="teaching-workspace">
      <div className="setup-summary-bar">
        <div className="teaching-course-summary-left">
          <select
            className="teaching-course-select"
            value={selectedCourseId}
            onChange={(event) => setSelectedCourseId(event.target.value)}
          >
            <option value="">Select course</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.code} · {course.title}
              </option>
            ))}
          </select>
          <div className="setup-summary-stats">
            <span>{courses.length} courses</span>
            <span className="setup-summary-sep" />
            <span>{activeCourses} active</span>
            {selectedCourse ? (
              <>
                <span className="setup-summary-sep" />
                <span>Teacher: {selectedCourse.teacher?.display_name || "-"}</span>
                <span className="setup-summary-sep" />
                <span>{selectedCourseProjects.length} projects</span>
                <span className="setup-summary-sep" />
                <span>{atRiskProjects} at risk</span>
                <span className="setup-summary-sep" />
                <span>{openBlockers} blockers</span>
                <span className="setup-summary-sep" />
                <span>{missingArtifacts} missing</span>
                <span className="setup-summary-sep" />
                <span>Deadlines: {selectedCourse.has_project_deadlines ? "on" : "off"}</span>
              </>
            ) : null}
          </div>
        </div>
        {selectedCourse && canManageSelectedCourse ? (
          <button type="button" className="ghost docs-action-btn" title="Edit Course" onClick={openCourseModal}>
            <FontAwesomeIcon icon={faPenToSquare} />
          </button>
        ) : null}
      </div>

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success-message">{status}</p> : null}

      <div className="teaching-course-main">
        {/* Staff Management (managers only) */}
        {selectedCourse && canManageSelectedCourse ? (
          <div className="card teaching-card">
            <div className="proposal-card-head">
              <strong>Teaching Assistants</strong>
            </div>
            <div className="teaching-staff-strip">
              {selectedCourse.teaching_assistants.map((assistant) => (
                <div key={assistant.user_id} className="teaching-staff-chip">
                  <span>{assistant.display_name}</span>
                  <button
                    type="button"
                    className="ghost docs-action-btn danger-text"
                    title="Remove"
                    disabled={busy}
                    onClick={() => void handleRemoveTeachingAssistant(assistant.user_id)}
                  >
                    <FontAwesomeIcon icon={faXmark} />
                  </button>
                </div>
              ))}
              {selectedCourse.teaching_assistants.length === 0 ? <span className="teaching-empty">None</span> : null}
              <div className="teaching-staff-add">
                <select value={taUserId} onChange={(event) => setTaUserId(event.target.value)}>
                  <option value="">Add assistant...</option>
                  {availableTaUsers.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.display_name} · {user.email}
                    </option>
                  ))}
                </select>
                <button type="button" className="meetings-new-btn" disabled={busy || !taUserId} onClick={() => void handleAddTeachingAssistant()}>
                  <FontAwesomeIcon icon={faPlus} /> Add
                </button>
              </div>
            </div>
          </div>
        ) : null}

        <div className="card teaching-card">
          <div className="proposal-card-head">
            <strong>Materials</strong>
            <div className="teaching-row-actions">
              {materialTypes.length > 1 ? (
                <select
                  className="teaching-material-type-filter"
                  value={materialTypeFilter}
                  onChange={(event) => setMaterialTypeFilter(event.target.value)}
                >
                  <option value="">All types</option>
                  {materialTypes.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              ) : null}
              {selectedCourse && canManageSelectedCourse ? (
                <button type="button" className="meetings-new-btn" onClick={() => openMaterialModal("create")}>
                  <FontAwesomeIcon icon={faPlus} /> Add
                </button>
              ) : null}
            </div>
          </div>
          {selectedCourse ? (
            <div className="teaching-materials-list">
              {groupedMaterials.map((group) => (
                <div key={group.type} className="teaching-material-group">
                  <div className="teaching-material-group-label">{group.type}</div>
                  {group.items.map((material) => (
                    <div key={material.id} className="teaching-material-card">
                      <div className="proposal-card-head">
                        <div className="teaching-material-head">
                          <strong>{material.title}</strong>
                          {material.external_url ? (
                            <a href={material.external_url} target="_blank" rel="noreferrer" className="teaching-material-link" title={material.external_url}>
                              <FontAwesomeIcon icon={faArrowUpRightFromSquare} />
                            </a>
                          ) : null}
                        </div>
                        <div className="teaching-row-actions">
                          {material.content_markdown ? (
                            <button
                              type="button"
                              className="ghost docs-action-btn"
                              title={expandedMaterials.has(material.id) ? "Collapse" : "Expand"}
                              onClick={() => toggleMaterialExpanded(material.id)}
                            >
                              <FontAwesomeIcon icon={expandedMaterials.has(material.id) ? faChevronUp : faChevronDown} />
                            </button>
                          ) : null}
                          {canManageSelectedCourse ? (
                            <>
                              <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openMaterialModal("edit", material)}>
                                <FontAwesomeIcon icon={faPenToSquare} />
                              </button>
                              <button type="button" className="ghost docs-action-btn danger-text" title="Delete" onClick={() => void handleDeleteMaterial(material.id)}>
                                <FontAwesomeIcon icon={faTrash} />
                              </button>
                            </>
                          ) : null}
                        </div>
                      </div>
                      {material.content_markdown && expandedMaterials.has(material.id) ? (
                        <div className="chat-markdown teaching-markdown teaching-material-content">{renderMarkdown(material.content_markdown)}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ))}
              {selectedCourseMaterials.length === 0 ? <div className="teaching-empty">No materials</div> : null}
            </div>
          ) : (
            <div className="teaching-empty">Select a course</div>
          )}
        </div>

        <div className="card teaching-card">
          <div className="proposal-card-head">
            <strong>Projects</strong>
            <input
              className="meetings-search"
              placeholder="Search projects..."
              value={projectSearch}
              onChange={(event) => setProjectSearch(event.target.value)}
            />
          </div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Health</th>
                  <th>Responsible</th>
                  <th>Blockers</th>
                  <th>Artifacts</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredProjects.map((entry) => {
                  const blockers = entry.workspace.blockers.filter((item) => item.status !== "resolved").length;
                  const missing = entry.workspace.artifacts.filter((item) => item.required && item.status === "missing").length;
                  const health = entry.workspace.profile.health;
                  const needsAttention = health !== "green" || blockers > 0 || missing > 0;
                  return (
                    <tr key={entry.project.id} className={needsAttention ? `teaching-row-attention ${health}` : ""}>
                      <td><strong>{entry.project.code}</strong></td>
                      <td>{entry.project.title}</td>
                      <td><span className="chip small">{entry.workspace.profile.status}</span></td>
                      <td>{renderHealthIndicator(entry.workspace.profile.health)}</td>
                      <td>{entry.workspace.profile.responsible_user?.display_name || "-"}</td>
                      <td>{blockers > 0 ? <span className="teaching-alert-inline"><FontAwesomeIcon icon={faTriangleExclamation} /> {blockers}</span> : "0"}</td>
                      <td>{missing}</td>
                      <td>
                        <button type="button" className="ghost docs-action-btn" title="Open" onClick={() => onOpenProject(entry.project.id)}>
                          <FontAwesomeIcon icon={faArrowRight} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {filteredProjects.length === 0 ? (
                  <tr><td colSpan={8}>{projectSearch ? "No matching projects" : "No projects"}</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {materialModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card settings-modal-card teaching-editor-modal">
            <div className="modal-head">
              <h3>{materialModal === "edit" ? "Edit Material" : "Add Material"}</h3>
              <div className="modal-head-actions">
                <button type="button" className="meetings-new-btn" onClick={() => void handleSaveMaterial()} disabled={busy}>
                  {busy ? "Saving..." : "Save"}
                </button>
                <button type="button" className="ghost docs-action-btn" onClick={() => setMaterialModal(null)} title="Close">
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>
            <div className="teaching-report-editor-stack">
              <div className="form-grid">
                <label>
                  Type
                  <select value={materialType} onChange={(event) => setMaterialType(event.target.value)}>
                    <option value="instructions">instructions</option>
                    <option value="rubric">rubric</option>
                    <option value="template">template</option>
                    <option value="schedule">schedule</option>
                    <option value="resource">resource</option>
                    <option value="other">other</option>
                  </select>
                </label>
                <label>
                  Order
                  <input type="number" min={0} value={materialSortOrder} onChange={(event) => setMaterialSortOrder(event.target.value)} />
                </label>
                <label className="full-span">
                  Title
                  <input value={materialTitle} onChange={(event) => setMaterialTitle(event.target.value)} />
                </label>
                <label className="full-span">
                  URL
                  <input value={materialUrl} onChange={(event) => setMaterialUrl(event.target.value)} />
                </label>
              </div>
              <div className="card teaching-editor-card">
                <ProposalRichEditor value={materialContent} onChange={setMaterialContent} placeholder="Content" />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {courseModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card settings-modal-card">
            <div className="modal-head">
              <h3>Edit Course</h3>
              <div className="modal-head-actions">
                <button type="button" className="meetings-new-btn" onClick={() => void handleSaveCourse()} disabled={busy}>
                  {busy ? "Saving..." : "Save"}
                </button>
                <button type="button" className="ghost docs-action-btn" onClick={() => setCourseModal(false)} title="Close">
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
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
              <label>
                Teacher
                <select value={courseTeacherUserId} onChange={(event) => setCourseTeacherUserId(event.target.value)}>
                  <option value="">Unassigned</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>{user.display_name}</option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select value={courseIsActive ? "active" : "inactive"} onChange={(event) => setCourseIsActive(event.target.value === "active")}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>
              <label>
                Deadlines
                <select value={courseHasDeadlines ? "enabled" : "disabled"} onChange={(event) => setCourseHasDeadlines(event.target.value === "enabled")}>
                  <option value="enabled">Enabled</option>
                  <option value="disabled">Disabled</option>
                </select>
              </label>
              <label className="full-span">
                Description
                <textarea rows={3} value={courseDescription} onChange={(event) => setCourseDescription(event.target.value)} />
              </label>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
