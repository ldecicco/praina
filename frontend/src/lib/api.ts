import type {
  AssignmentMatrixRow,
  AuditEvent,
  AuthTokens,
  CalendarImportBatch,
  CalendarIntegration,
  Course,
  CourseMaterial,
  AuthUser,
  ChatConversation,
  ChatMessage,
  ChatMessageExchange,
  CoherenceReport,
  DocumentListItem,
  DocumentVersion,
  DocumentVersionList,
  MeResponse,
  MeetingActionItem,
  MeetingRecord,
  Member,
  MembershipWithUser,
  MyWorkResponse,
  Paginated,
  Partner,
  ProjectChatMessage,
  ProjectChatRoom,
  ProjectBroadcast,
  ProjectActivationResult,
  ProjectProposalSection,
  ProjectRisk,
  ProjectValidationResult,
  ProjectMembership,
  Project,
  ProjectInboxItem,
  ProposalImage,
  ProposalCallAnswer,
  ProposalCallBrief,
  ProposalCallDocumentReindexResult,
  ProposalCallIngestJob,
  ProposalCallLibraryDocument,
  ProposalCallLibraryEntry,
  ProposalSubmissionItem,
  ProposalSubmissionRequirement,
  ProposalReviewFinding,
  ProjectTodo,
  ProposalTemplate,
  ReindexResult,
  ReviewFinding,
  TrashedWorkEntity,
  WorkEntity,
  AppNotification,
  DashboardHealth,
  DashboardHealthIssue,
  DashboardRecurringIssue,
  DashboardHealthSnapshot,
  DashboardScopeOptions,
  SearchResponse,
  BibliographyDuplicateMatch,
  BibliographyGraph,
  BibliographyNote,
  BibliographyReference,
  BibliographyCollection,
  BibliographyTag,
  BibliographyIdentifierImportResult,
  TelegramLinkState,
  TelegramDiscoveryStart,
  ResearchCollection,
  ResearchCollectionDetail,
  ResearchCollectionMember,
  ResearchResultComparison,
  ResearchSpace,
  ResearchStudyFile,
  ResearchReference,
  ResearchNote,
  Equipment,
  EquipmentMaterial,
  EquipmentBlocker,
  EquipmentBooking,
  EquipmentConflict,
  EquipmentDowntime,
  Lab,
  LabClosure,
  EquipmentRequirement,
  ProjectResourcesWorkspace,
  TeachingProjectArtifact,
  TeachingProjectAssessment,
  TeachingProjectBackgroundMaterial,
  TeachingProjectBlocker,
  TeachingProjectMilestone,
  TeachingProjectProfile,
  TeachingProjectStudent,
  TeachingProgressReport,
  TeachingWorkspace,
  UserSuggestion,
  StudyChatRoom,
  StudyChatMessage,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE;
if (!API_BASE) {
  throw new Error("VITE_API_BASE must be set in frontend .env.");
}

let authToken: string | null = null;
export const PROJECT_DATA_CHANGED_EVENT = "project-data-changed";
export const AUTH_EXPIRED_EVENT = "auth-expired";

function emitProjectChanged(projectId: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(PROJECT_DATA_CHANGED_EVENT, { detail: { projectId } }));
}

function emitAuthExpired(message: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { message } }));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const hasFormDataBody = init?.body instanceof FormData;
  const headers = new Headers(init?.headers ?? undefined);
  if (authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  if (!hasFormDataBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...init,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(errorBody);
    } catch {
      parsed = null;
    }
    const message = formatApiErrorResponse(parsed) || errorBody || `API request failed: ${response.status}`;
    if (response.status === 401 && authToken) {
      emitAuthExpired(message);
    }
    throw new Error(message);
  }

  const method = (init?.method || "GET").toUpperCase();
  const match = path.match(/^\/projects\/([^/?]+)/);
  if (method !== "GET" && match?.[1]) {
    emitProjectChanged(match[1]);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const headers = new Headers(init?.headers ?? undefined);
  if (authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...init,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(errorBody);
    } catch {
      parsed = null;
    }
    const message = formatApiErrorResponse(parsed) || errorBody || `API request failed: ${response.status}`;
    if (response.status === 401 && authToken) {
      emitAuthExpired(message);
    }
    throw new Error(message);
  }

  return response.blob();
}

function formatApiErrorResponse(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const detail = "detail" in payload ? (payload as { detail?: unknown }).detail : undefined;
  const message = "message" in payload ? (payload as { message?: unknown }).message : undefined;
  return formatApiErrorDetail(detail) || (typeof message === "string" ? message : "");
}

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg?: unknown }).msg || "") : ""))
      .filter((item) => item.length > 0);
    if (messages.length > 0) return messages.join(" | ");
  }
  return "";
}

export const api = {
  setAuthToken(token: string | null) {
    authToken = token;
  },

  getAuthToken() {
    return authToken;
  },

  register(payload: { email: string; password: string; display_name: string }): Promise<AuthUser> {
    return request("/auth/register", { method: "POST", body: JSON.stringify(payload) });
  },

  login(payload: { email: string; password: string }): Promise<AuthTokens> {
    return request("/auth/login", { method: "POST", body: JSON.stringify(payload) });
  },

  refresh(payload: { refresh_token: string }): Promise<AuthTokens> {
    return request("/auth/refresh", { method: "POST", body: JSON.stringify(payload) });
  },

  me(): Promise<MeResponse> {
    return request("/auth/me");
  },

  updateMyProfile(payload: {
    display_name?: string;
    job_title?: string | null;
    organization?: string | null;
    phone?: string | null;
  }): Promise<AuthUser> {
    return request("/auth/me", { method: "PATCH", body: JSON.stringify(payload) });
  },

  changeMyPassword(payload: { current_password: string; new_password: string }): Promise<{ ok: boolean }> {
    return request("/auth/me/password", { method: "POST", body: JSON.stringify(payload) });
  },

  createMySuggestion(payload: { content: string }): Promise<UserSuggestion> {
    return request("/auth/me/suggestions", { method: "POST", body: JSON.stringify(payload) });
  },

  listUserSuggestions(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    search?: string;
  }): Promise<Paginated<UserSuggestion>> {
    const search = new URLSearchParams();
    if (params?.page) search.set("page", String(params.page));
    if (params?.page_size) search.set("page_size", String(params.page_size));
    if (params?.status) search.set("status", params.status);
    if (params?.search) search.set("search", params.search);
    return request(`/auth/admin/suggestions${search.toString() ? `?${search.toString()}` : ""}`);
  },

  updateUserSuggestion(suggestionId: string, payload: { status: string }): Promise<UserSuggestion> {
    return request(`/auth/admin/suggestions/${suggestionId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  getMyTelegramState(): Promise<TelegramLinkState> {
    return request("/auth/me/telegram");
  },

  startMyTelegramDiscovery(): Promise<TelegramDiscoveryStart> {
    return request("/auth/me/telegram/discovery", { method: "POST" });
  },

  completeMyTelegramDiscovery(): Promise<TelegramLinkState> {
    return request("/auth/me/telegram/discovery/complete", { method: "POST" });
  },

  updateMyTelegramPreferences(payload: { notifications_enabled: boolean }): Promise<TelegramLinkState> {
    return request("/auth/me/telegram", { method: "PATCH", body: JSON.stringify(payload) });
  },

  disconnectMyTelegram(): Promise<TelegramLinkState> {
    return request("/auth/me/telegram", { method: "DELETE" });
  },

  sendMyTelegramTestNotification(): Promise<{ ok: boolean }> {
    return request("/auth/me/telegram/test", { method: "POST" });
  },

  uploadMyAvatar(file: File): Promise<{ avatar_url: string }> {
    const formData = new FormData();
    formData.append("file", file);
    return request("/auth/me/avatar", { method: "POST", body: formData });
  },

  listUserDiscovery(page = 1, pageSize = 100, search = ""): Promise<Paginated<AuthUser>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (search.trim()) query.set("search", search.trim());
    return request(`/auth/users/discovery?${query.toString()}`);
  },

  listUsers(page = 1, pageSize = 100, search = ""): Promise<Paginated<AuthUser>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (search.trim()) query.set("search", search.trim());
    return request(`/auth/users?${query.toString()}`);
  },

  updateUser(
    userId: string,
    payload: { display_name?: string; platform_role?: string; is_active?: boolean; can_access_research?: boolean; can_access_teaching?: boolean }
  ): Promise<AuthUser> {
    return request(`/auth/users/${userId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  createUser(
    payload: {
      email: string;
      display_name: string;
      password?: string;
      platform_role?: string;
      is_active?: boolean;
      can_access_research?: boolean;
      can_access_teaching?: boolean;
    }
  ): Promise<AuthUser> {
    return request("/auth/users", { method: "POST", body: JSON.stringify(payload) });
  },

  listProjectMembershipsWithUsers(projectId: string): Promise<Paginated<MembershipWithUser>> {
    return request(`/auth/projects/${projectId}/memberships?page=1&page_size=100`);
  },

  listProjects(page = 1, pageSize = 100): Promise<Paginated<Project>> {
    return request(`/projects?page=${page}&page_size=${pageSize}`);
  },

  listCourses(page = 1, pageSize = 200, search = "", activeOnly = false): Promise<Paginated<Course>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (search.trim()) query.set("search", search.trim());
    if (activeOnly) query.set("active_only", "true");
    return request(`/courses?${query.toString()}`);
  },

  createCourse(payload: { code: string; title: string; description?: string | null; is_active?: boolean; has_project_deadlines?: boolean; teacher_user_id?: string | null }): Promise<Course> {
    return request("/courses", { method: "POST", body: JSON.stringify(payload) });
  },

  updateCourse(courseId: string, payload: { code?: string; title?: string; description?: string | null; is_active?: boolean; has_project_deadlines?: boolean; teacher_user_id?: string | null }): Promise<Course> {
    return request(`/courses/${courseId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  addCourseTeachingAssistant(courseId: string, userId: string): Promise<Course> {
    return request(`/courses/${courseId}/teaching-assistants`, { method: "POST", body: JSON.stringify({ user_id: userId }) });
  },

  removeCourseTeachingAssistant(courseId: string, userId: string): Promise<Course> {
    return request(`/courses/${courseId}/teaching-assistants/${userId}`, { method: "DELETE" });
  },

  createCourseMaterial(courseId: string, payload: {
    material_type?: string;
    title: string;
    content_markdown?: string | null;
    external_url?: string | null;
    sort_order?: number;
  }): Promise<CourseMaterial> {
    return request(`/courses/${courseId}/materials`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateCourseMaterial(courseId: string, materialId: string, payload: {
    material_type?: string;
    title?: string;
    content_markdown?: string | null;
    external_url?: string | null;
    sort_order?: number;
  }): Promise<CourseMaterial> {
    return request(`/courses/${courseId}/materials/${materialId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteCourseMaterial(courseId: string, materialId: string): Promise<void> {
    return request(`/courses/${courseId}/materials/${materialId}`, { method: "DELETE" });
  },

  deleteCourse(courseId: string): Promise<void> {
    return request(`/courses/${courseId}`, { method: "DELETE" });
  },

  createProject(payload: {
    code: string;
    title: string;
    description?: string;
    start_date?: string;
    duration_months?: number;
    reporting_dates?: string[];
    language?: string;
    project_mode?: string;
    project_kind?: string;
    teaching_course_id?: string | null;
    teaching_academic_year?: string | null;
    teaching_term?: string | null;
    coordinator_partner_id?: string | null;
    principal_investigator_id?: string | null;
    proposal_template_id?: string | null;
  }): Promise<Project> {
    return request("/projects", { method: "POST", body: JSON.stringify(payload) });
  },

  markAsFunded(projectId: string, payload: {
    start_date: string;
    duration_months: number;
    reporting_dates?: string[];
  }): Promise<ProjectActivationResult> {
    return request(`/projects/${projectId}/mark-as-funded`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateProject(
    projectId: string,
    payload: {
      code?: string;
      title?: string;
      description?: string | null;
      start_date?: string;
      duration_months?: number;
      reporting_dates?: string[];
      language?: string;
      project_kind?: string;
      teaching_course_id?: string | null;
      teaching_academic_year?: string | null;
      teaching_term?: string | null;
      coordinator_partner_id?: string | null;
      principal_investigator_id?: string | null;
      proposal_template_id?: string | null;
    }
  ): Promise<Project> {
    return request(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  archiveProject(projectId: string): Promise<Project> {
    return request(`/projects/${projectId}/archive`, { method: "POST" });
  },

  deleteProject(projectId: string): Promise<void> {
    return request(`/projects/${projectId}`, { method: "DELETE" });
  },

  getTeachingWorkspace(projectId: string): Promise<TeachingWorkspace> {
    return request(`/projects/${projectId}/teaching`);
  },

  listEquipment(page = 1, pageSize = 100, search = "", category = "", status = ""): Promise<Paginated<Equipment>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (search.trim()) query.set("search", search.trim());
    if (category.trim()) query.set("category", category.trim());
    if (status.trim()) query.set("status", status.trim());
    return request(`/resources/equipment?${query.toString()}`);
  },

  listLabs(page = 1, pageSize = 100): Promise<Paginated<Lab>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    return request(`/resources/labs?${query.toString()}`);
  },

  createLab(payload: {
    name: string;
    building?: string | null;
    room?: string | null;
    notes?: string | null;
    responsible_user_id?: string | null;
    is_active?: boolean;
  }): Promise<Lab> {
    return request("/resources/labs", { method: "POST", body: JSON.stringify(payload) });
  },

  updateLab(
    labId: string,
    payload: {
      name?: string;
      building?: string | null;
      room?: string | null;
      notes?: string | null;
      responsible_user_id?: string | null;
      is_active?: boolean;
    }
  ): Promise<Lab> {
    return request(`/resources/labs/${labId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteLab(labId: string): Promise<void> {
    return request(`/resources/labs/${labId}`, { method: "DELETE" });
  },

  addLabStaff(labId: string, payload: { user_id: string; role?: string }): Promise<Lab> {
    return request(`/resources/labs/${labId}/staff`, { method: "POST", body: JSON.stringify(payload) });
  },

  removeLabStaff(labId: string, userId: string): Promise<Lab> {
    return request(`/resources/labs/${labId}/staff/${userId}`, { method: "DELETE" });
  },

  listLabClosures(page = 1, pageSize = 100, labId = ""): Promise<Paginated<LabClosure>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (labId) query.set("lab_id", labId);
    return request(`/resources/lab-closures?${query.toString()}`);
  },

  createLabClosure(payload: {
    lab_id: string;
    start_at: string;
    end_at: string;
    reason?: string;
    notes?: string | null;
  }): Promise<LabClosure> {
    return request("/resources/lab-closures", { method: "POST", body: JSON.stringify(payload) });
  },

  updateLabClosure(
    closureId: string,
    payload: {
      lab_id: string;
      start_at: string;
      end_at: string;
      reason?: string;
      notes?: string | null;
    }
  ): Promise<LabClosure> {
    return request(`/resources/lab-closures/${closureId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteLabClosure(closureId: string): Promise<void> {
    return request(`/resources/lab-closures/${closureId}`, { method: "DELETE" });
  },

  createEquipment(payload: {
    name: string;
    category?: string | null;
    model?: string | null;
    serial_number?: string | null;
    description?: string | null;
    location?: string | null;
    lab_id?: string | null;
    owner_user_id?: string | null;
    status?: string;
    usage_mode?: string;
    access_notes?: string | null;
    booking_notes?: string | null;
    maintenance_notes?: string | null;
    is_active?: boolean;
  }): Promise<Equipment> {
    return request("/resources/equipment", { method: "POST", body: JSON.stringify(payload) });
  },

  updateEquipment(
    equipmentId: string,
    payload: {
      name?: string;
      category?: string | null;
      model?: string | null;
      serial_number?: string | null;
      description?: string | null;
      location?: string | null;
      lab_id?: string | null;
      owner_user_id?: string | null;
      status?: string;
      usage_mode?: string;
      access_notes?: string | null;
      booking_notes?: string | null;
      maintenance_notes?: string | null;
      is_active?: boolean;
    }
  ): Promise<Equipment> {
    return request(`/resources/equipment/${equipmentId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteEquipment(equipmentId: string): Promise<void> {
    return request(`/resources/equipment/${equipmentId}`, { method: "DELETE" });
  },

  listEquipmentMaterials(page = 1, pageSize = 100, equipmentId = ""): Promise<Paginated<EquipmentMaterial>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (equipmentId) query.set("equipment_id", equipmentId);
    return request(`/resources/equipment-materials?${query.toString()}`);
  },

  createEquipmentMaterial(equipmentId: string, payload: {
    material_type?: string;
    title: string;
    external_url?: string | null;
    notes?: string | null;
  }): Promise<EquipmentMaterial> {
    return request(`/resources/equipment-materials?equipment_id=${encodeURIComponent(equipmentId)}`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateEquipmentMaterial(materialId: string, payload: {
    material_type?: string;
    title?: string;
    external_url?: string | null;
    notes?: string | null;
  }): Promise<EquipmentMaterial> {
    return request(`/resources/equipment-materials/${materialId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteEquipmentMaterial(materialId: string): Promise<void> {
    return request(`/resources/equipment-materials/${materialId}`, { method: "DELETE" });
  },

  uploadEquipmentMaterialAttachment(materialId: string, file: File): Promise<EquipmentMaterial> {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/resources/equipment-materials/${materialId}/attachment`, { method: "POST", body: formData });
  },

  listEquipmentBookings(page = 1, pageSize = 100, equipmentId = "", projectId = "", status = ""): Promise<Paginated<EquipmentBooking>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (equipmentId) query.set("equipment_id", equipmentId);
    if (projectId) query.set("project_id", projectId);
    if (status.trim()) query.set("status", status.trim());
    return request(`/resources/bookings?${query.toString()}`);
  },

  createEquipmentBooking(payload: {
    equipment_id: string;
    project_id: string;
    start_at: string;
    end_at: string;
    purpose: string;
    notes?: string | null;
  }): Promise<EquipmentBooking> {
    return request("/resources/bookings", { method: "POST", body: JSON.stringify(payload) });
  },

  updateEquipmentBooking(
    bookingId: string,
    payload: {
      start_at?: string;
      end_at?: string;
      purpose?: string;
      notes?: string | null;
      status?: string;
    }
  ): Promise<EquipmentBooking> {
    return request(`/resources/bookings/${bookingId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  approveEquipmentBooking(bookingId: string, notes?: string | null): Promise<EquipmentBooking> {
    return request(`/resources/bookings/${bookingId}/approve`, { method: "POST", body: JSON.stringify({ notes: notes || null }) });
  },

  rejectEquipmentBooking(bookingId: string, notes?: string | null): Promise<EquipmentBooking> {
    return request(`/resources/bookings/${bookingId}/reject`, { method: "POST", body: JSON.stringify({ notes: notes || null }) });
  },

  listEquipmentDowntime(page = 1, pageSize = 100, equipmentId = ""): Promise<Paginated<EquipmentDowntime>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (equipmentId) query.set("equipment_id", equipmentId);
    return request(`/resources/downtime?${query.toString()}`);
  },

  createEquipmentDowntime(payload: {
    equipment_id: string;
    start_at: string;
    end_at: string;
    reason?: string;
    notes?: string | null;
  }): Promise<EquipmentDowntime> {
    return request("/resources/downtime", { method: "POST", body: JSON.stringify(payload) });
  },

  updateEquipmentDowntime(
    downtimeId: string,
    payload: { start_at?: string; end_at?: string; reason?: string; notes?: string | null }
  ): Promise<EquipmentDowntime> {
    return request(`/resources/downtime/${downtimeId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteEquipmentDowntime(downtimeId: string): Promise<void> {
    return request(`/resources/downtime/${downtimeId}`, { method: "DELETE" });
  },

  listEquipmentConflicts(payload?: {
    equipment_id?: string;
    project_id?: string;
    start_at?: string;
    end_at?: string;
  }): Promise<EquipmentConflict[]> {
    const query = new URLSearchParams();
    if (payload?.equipment_id) query.set("equipment_id", payload.equipment_id);
    if (payload?.project_id) query.set("project_id", payload.project_id);
    if (payload?.start_at) query.set("start_at", payload.start_at);
    if (payload?.end_at) query.set("end_at", payload.end_at);
    return request(`/resources/conflicts${query.size ? `?${query.toString()}` : ""}`);
  },

  getProjectResources(projectId: string): Promise<ProjectResourcesWorkspace> {
    return request(`/projects/${projectId}/resources`);
  },

  listProjectEquipmentRequirements(projectId: string): Promise<Paginated<EquipmentRequirement>> {
    return request(`/projects/${projectId}/resources/requirements`);
  },

  createProjectEquipmentRequirement(
    projectId: string,
    payload: { equipment_id: string; priority?: string; purpose: string; notes?: string | null }
  ): Promise<EquipmentRequirement> {
    return request(`/projects/${projectId}/resources/requirements`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateProjectEquipmentRequirement(
    projectId: string,
    requirementId: string,
    payload: { priority?: string; purpose?: string; notes?: string | null }
  ): Promise<EquipmentRequirement> {
    return request(`/projects/${projectId}/resources/requirements/${requirementId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteProjectEquipmentRequirement(projectId: string, requirementId: string): Promise<void> {
    return request(`/projects/${projectId}/resources/requirements/${requirementId}`, { method: "DELETE" });
  },

  updateTeachingProfile(projectId: string, payload: {
    course_id?: string | null;
    academic_year?: string | null;
    term?: string | null;
    functional_objectives_markdown?: string | null;
    specifications_markdown?: string | null;
    responsible_user_id?: string | null;
    status?: string;
    health?: string;
    reporting_cadence_days?: number;
    final_grade?: number | null;
  }): Promise<TeachingProjectProfile> {
    return request(`/projects/${projectId}/teaching/profile`, { method: "PUT", body: JSON.stringify(payload) });
  },

  createTeachingStudent(projectId: string, payload: { full_name: string; email?: string | null }): Promise<TeachingProjectStudent> {
    return request(`/projects/${projectId}/teaching/students`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTeachingStudent(projectId: string, studentId: string, payload: { full_name?: string; email?: string | null }): Promise<TeachingProjectStudent> {
    return request(`/projects/${projectId}/teaching/students/${studentId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTeachingStudent(projectId: string, studentId: string): Promise<void> {
    return request(`/projects/${projectId}/teaching/students/${studentId}`, { method: "DELETE" });
  },

  createTeachingArtifact(projectId: string, payload: {
    artifact_type: string;
    label: string;
    required?: boolean;
    status?: string;
    document_key?: string | null;
    external_url?: string | null;
    notes?: string | null;
    submitted_at?: string | null;
  }): Promise<TeachingProjectArtifact> {
    return request(`/projects/${projectId}/teaching/artifacts`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTeachingArtifact(projectId: string, artifactId: string, payload: {
    artifact_type?: string;
    label?: string;
    required?: boolean;
    status?: string;
    document_key?: string | null;
    external_url?: string | null;
    notes?: string | null;
    submitted_at?: string | null;
  }): Promise<TeachingProjectArtifact> {
    return request(`/projects/${projectId}/teaching/artifacts/${artifactId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTeachingArtifact(projectId: string, artifactId: string): Promise<void> {
    return request(`/projects/${projectId}/teaching/artifacts/${artifactId}`, { method: "DELETE" });
  },

  createTeachingBackgroundMaterial(projectId: string, payload: {
    material_type?: string;
    title: string;
    bibliography_reference_id?: string | null;
    document_key?: string | null;
    external_url?: string | null;
    notes?: string | null;
  }): Promise<TeachingProjectBackgroundMaterial> {
    return request(`/projects/${projectId}/teaching/background-materials`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTeachingBackgroundMaterial(projectId: string, materialId: string, payload: {
    material_type?: string;
    title?: string;
    bibliography_reference_id?: string | null;
    document_key?: string | null;
    external_url?: string | null;
    notes?: string | null;
  }): Promise<TeachingProjectBackgroundMaterial> {
    return request(`/projects/${projectId}/teaching/background-materials/${materialId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTeachingBackgroundMaterial(projectId: string, materialId: string): Promise<void> {
    return request(`/projects/${projectId}/teaching/background-materials/${materialId}`, { method: "DELETE" });
  },

  createTeachingProgressReport(projectId: string, payload: {
    report_date?: string | null;
    meeting_date?: string | null;
    work_done_markdown?: string;
    next_steps_markdown?: string;
    blocker_updates?: Array<{ id?: string | null; title: string; description?: string | null; severity?: string; status?: string }>;
    supervisor_feedback_markdown?: string | null;
    attachment_document_keys?: string[];
    transcript_document_keys?: string[];
    submitted_at?: string | null;
  }): Promise<TeachingProgressReport> {
    return request(`/projects/${projectId}/teaching/progress-reports`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTeachingProgressReport(projectId: string, reportId: string, payload: {
    report_date?: string | null;
    meeting_date?: string | null;
    work_done_markdown?: string;
    next_steps_markdown?: string;
    blocker_updates?: Array<{ id?: string | null; title: string; description?: string | null; severity?: string; status?: string }>;
    supervisor_feedback_markdown?: string | null;
    attachment_document_keys?: string[];
    transcript_document_keys?: string[];
    submitted_at?: string | null;
  }): Promise<TeachingProgressReport> {
    return request(`/projects/${projectId}/teaching/progress-reports/${reportId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTeachingProgressReport(projectId: string, reportId: string): Promise<void> {
    return request(`/projects/${projectId}/teaching/progress-reports/${reportId}`, { method: "DELETE" });
  },

  createTeachingMilestone(projectId: string, payload: {
    kind: string;
    label: string;
    due_at?: string | null;
    completed_at?: string | null;
    status?: string;
  }): Promise<TeachingProjectMilestone> {
    return request(`/projects/${projectId}/teaching/milestones`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTeachingMilestone(projectId: string, milestoneId: string, payload: {
    kind?: string;
    label?: string;
    due_at?: string | null;
    completed_at?: string | null;
    status?: string;
  }): Promise<TeachingProjectMilestone> {
    return request(`/projects/${projectId}/teaching/milestones/${milestoneId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTeachingMilestone(projectId: string, milestoneId: string): Promise<void> {
    return request(`/projects/${projectId}/teaching/milestones/${milestoneId}`, { method: "DELETE" });
  },

  createTeachingBlocker(projectId: string, payload: {
    title: string;
    description?: string | null;
    severity?: string;
    status?: string;
    detected_from?: string | null;
    opened_at?: string | null;
    resolved_at?: string | null;
  }): Promise<TeachingProjectBlocker> {
    return request(`/projects/${projectId}/teaching/blockers`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTeachingBlocker(projectId: string, blockerId: string, payload: {
    title?: string;
    description?: string | null;
    severity?: string;
    status?: string;
    detected_from?: string | null;
    opened_at?: string | null;
    resolved_at?: string | null;
  }): Promise<TeachingProjectBlocker> {
    return request(`/projects/${projectId}/teaching/blockers/${blockerId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTeachingBlocker(projectId: string, blockerId: string): Promise<void> {
    return request(`/projects/${projectId}/teaching/blockers/${blockerId}`, { method: "DELETE" });
  },

  upsertTeachingAssessment(projectId: string, payload: {
    grade?: number | null;
    strengths_markdown?: string | null;
    weaknesses_markdown?: string | null;
    grading_rationale_markdown?: string | null;
    grader_user_id?: string | null;
    graded_at?: string | null;
  }): Promise<TeachingProjectAssessment> {
    return request(`/projects/${projectId}/teaching/assessment`, { method: "PUT", body: JSON.stringify(payload) });
  },

  createPartner(projectId: string, payload: { short_name: string; legal_name: string; partner_type?: string; country?: string; expertise?: string }): Promise<Partner> {
    return request(`/projects/${projectId}/partners`, { method: "POST", body: JSON.stringify(payload) });
  },

  updatePartner(projectId: string, partnerId: string, payload: { short_name: string; legal_name: string; partner_type?: string; country?: string; expertise?: string }): Promise<Partner> {
    return request(`/projects/${projectId}/partners/${partnerId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deletePartner(projectId: string, partnerId: string): Promise<void> {
    return request(`/projects/${projectId}/partners/${partnerId}`, { method: "DELETE" });
  },

  listPartners(projectId: string): Promise<Paginated<Partner>> {
    return request(`/projects/${projectId}/partners?page=1&page_size=100`);
  },

  createMember(
    projectId: string,
    payload: {
      partner_id: string;
      role: string;
      user_id?: string;
      full_name?: string;
      email?: string;
      create_user_if_missing?: boolean;
      temporary_password?: string;
    }
  ): Promise<Member> {
    return request(`/projects/${projectId}/members`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateMember(
    projectId: string,
    memberId: string,
    payload: {
      partner_id: string;
      role: string;
      user_id?: string;
      full_name?: string;
      email?: string;
      create_user_if_missing?: boolean;
      temporary_password?: string;
      is_active?: boolean;
    }
  ): Promise<Member> {
    return request(`/projects/${projectId}/members/${memberId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteMember(projectId: string, memberId: string): Promise<void> {
    return request(`/projects/${projectId}/members/${memberId}`, { method: "DELETE" });
  },

  listMembers(projectId: string): Promise<Paginated<Member>> {
    return request(`/projects/${projectId}/members?page=1&page_size=100`);
  },

  createWorkPackage(
    projectId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      start_month: number;
      end_month: number;
      execution_status?: string;
      completed_by_member_id?: string | null;
      completion_note?: string;
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/work-packages`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateWorkPackage(
    projectId: string,
    entityId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      start_month: number;
      end_month: number;
      execution_status?: string;
      completed_by_member_id?: string | null;
      completion_note?: string;
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/work-packages/${entityId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  createTask(
    projectId: string,
    payload: {
      wp_id: string;
      code: string;
      title: string;
      description?: string;
      start_month: number;
      end_month: number;
      execution_status?: string;
      completed_by_member_id?: string | null;
      completion_note?: string;
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/tasks`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTask(
    projectId: string,
    entityId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      start_month: number;
      end_month: number;
      execution_status?: string;
      completed_by_member_id?: string | null;
      completion_note?: string;
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/tasks/${entityId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  createMilestone(
    projectId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      due_month: number;
      wp_ids?: string[];
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/milestones`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateMilestone(
    projectId: string,
    entityId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      due_month: number;
      wp_ids: string[];
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/milestones/${entityId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  createDeliverable(
    projectId: string,
    payload: {
      wp_ids: string[];
      code: string;
      title: string;
      description?: string;
      due_month: number;
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/deliverables`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateDeliverable(
    projectId: string,
    entityId: string,
    payload: {
      wp_ids: string[];
      code: string;
      title: string;
      description?: string;
      due_month: number;
      workflow_status?: string;
      review_due_month?: number;
      review_owner_member_id?: string;
      assignment: {
        leader_organization_id: string;
        responsible_person_id: string;
        collaborating_partner_ids: string[];
      };
    }
  ): Promise<WorkEntity> {
    return request(`/projects/${projectId}/deliverables/${entityId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  listAssignmentMatrix(projectId: string, entityType?: string): Promise<Paginated<AssignmentMatrixRow>> {
    const query = entityType ? `?entity_type=${entityType}&page=1&page_size=100` : "?page=1&page_size=100";
    return request(`/projects/${projectId}/assignment-matrix${query}`);
  },

  updateAssignment(
    projectId: string,
    row: AssignmentMatrixRow,
    payload: {
      leader_organization_id: string;
      responsible_person_id: string;
      collaborating_partner_ids: string[];
    }
  ): Promise<WorkEntity> {
    const endpointByType: Record<AssignmentMatrixRow["entity_type"], string> = {
      work_package: "work-packages",
      task: "tasks",
      milestone: "milestones",
      deliverable: "deliverables",
    };
    const endpoint = endpointByType[row.entity_type];
    return request(`/projects/${projectId}/${endpoint}/${row.entity_id}/assignment`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  listWorkPackages(projectId: string): Promise<Paginated<WorkEntity>> {
    return request(`/projects/${projectId}/work-packages?page=1&page_size=100`);
  },

  listTasks(projectId: string): Promise<Paginated<WorkEntity>> {
    return request(`/projects/${projectId}/tasks?page=1&page_size=100`);
  },

  listMilestones(projectId: string): Promise<Paginated<WorkEntity>> {
    return request(`/projects/${projectId}/milestones?page=1&page_size=100`);
  },

  listDeliverables(projectId: string): Promise<Paginated<WorkEntity>> {
    return request(`/projects/${projectId}/deliverables?page=1&page_size=100`);
  },

  listTrashedWorkEntities(projectId: string, page = 1, pageSize = 200): Promise<Paginated<TrashedWorkEntity>> {
    return request(`/projects/${projectId}/trash?page=${page}&page_size=${pageSize}`);
  },

  trashWorkPackage(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/work-packages/${entityId}/trash`, { method: "POST" });
  },

  restoreWorkPackage(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/work-packages/${entityId}/restore`, { method: "POST" });
  },

  trashTask(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/tasks/${entityId}/trash`, { method: "POST" });
  },

  restoreTask(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/tasks/${entityId}/restore`, { method: "POST" });
  },

  trashMilestone(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/milestones/${entityId}/trash`, { method: "POST" });
  },

  restoreMilestone(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/milestones/${entityId}/restore`, { method: "POST" });
  },

  trashDeliverable(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/deliverables/${entityId}/trash`, { method: "POST" });
  },

  restoreDeliverable(projectId: string, entityId: string): Promise<WorkEntity> {
    return request(`/projects/${projectId}/deliverables/${entityId}/restore`, { method: "POST" });
  },

  validateProject(projectId: string, options?: { includeLlm?: boolean }): Promise<ProjectValidationResult> {
    const query = new URLSearchParams();
    if (typeof options?.includeLlm === "boolean") query.set("include_llm", String(options.includeLlm));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request(`/projects/${projectId}/validate${suffix}`, { method: "POST" });
  },

  activateProject(projectId: string): Promise<ProjectActivationResult> {
    return request(`/projects/${projectId}/activate`, { method: "POST" });
  },

  runCoherenceCheck(projectId: string, options?: { includeLlm?: boolean }): Promise<CoherenceReport> {
    const query = new URLSearchParams();
    if (typeof options?.includeLlm === "boolean") query.set("include_llm", String(options.includeLlm));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request(`/projects/${projectId}/coherence-check${suffix}`, { method: "POST" });
  },

  listActivity(projectId: string, page = 1, pageSize = 20, eventType = ""): Promise<Paginated<AuditEvent>> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (eventType.trim()) query.set("event_type", eventType.trim());
    return request(`/projects/${projectId}/activity?${query.toString()}`);
  },

  listRisks(
    projectId: string,
    params?: { status?: string; owner_partner_id?: string; search?: string },
  ): Promise<Paginated<ProjectRisk>> {
    const query = new URLSearchParams({ page: "1", page_size: "100" });
    if (params?.status) query.set("status", params.status);
    if (params?.owner_partner_id) query.set("owner_partner_id", params.owner_partner_id);
    if (params?.search) query.set("search", params.search);
    return request(`/projects/${projectId}/risks?${query.toString()}`);
  },

  createRisk(
    projectId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      mitigation_plan?: string;
      status: string;
      probability: string;
      impact: string;
      due_month?: number;
      owner_partner_id: string;
      owner_member_id: string;
    }
  ): Promise<ProjectRisk> {
    return request(`/projects/${projectId}/risks`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateRisk(
    projectId: string,
    riskId: string,
    payload: {
      code: string;
      title: string;
      description?: string;
      mitigation_plan?: string;
      status: string;
      probability: string;
      impact: string;
      due_month?: number;
      owner_partner_id: string;
      owner_member_id: string;
    }
  ): Promise<ProjectRisk> {
    return request(`/projects/${projectId}/risks/${riskId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  uploadDocument(projectId: string, payload: {
    file: File;
    scope: "project" | "wp" | "task" | "deliverable" | "milestone";
    title: string;
    metadata_json?: string;
    wp_id?: string;
    task_id?: string;
    deliverable_id?: string;
    milestone_id?: string;
    uploaded_by_member_id?: string;
    proposal_section_id?: string;
  }): Promise<DocumentVersion> {
    const form = new FormData();
    form.append("file", payload.file);
    form.append("scope", payload.scope);
    form.append("title", payload.title);
    if (payload.metadata_json) form.append("metadata_json", payload.metadata_json);
    if (payload.wp_id) form.append("wp_id", payload.wp_id);
    if (payload.task_id) form.append("task_id", payload.task_id);
    if (payload.deliverable_id) form.append("deliverable_id", payload.deliverable_id);
    if (payload.milestone_id) form.append("milestone_id", payload.milestone_id);
    if (payload.uploaded_by_member_id) form.append("uploaded_by_member_id", payload.uploaded_by_member_id);
    if (payload.proposal_section_id) form.append("proposal_section_id", payload.proposal_section_id);
    return request(`/projects/${projectId}/documents/upload`, { method: "POST", body: form });
  },

  uploadDocumentVersion(projectId: string, documentKey: string, payload: {
    file: File;
    title?: string;
    metadata_json?: string;
    uploaded_by_member_id?: string;
    proposal_section_id?: string;
  }): Promise<DocumentVersion> {
    const form = new FormData();
    form.append("file", payload.file);
    if (payload.title) form.append("title", payload.title);
    if (payload.metadata_json) form.append("metadata_json", payload.metadata_json);
    if (payload.uploaded_by_member_id) form.append("uploaded_by_member_id", payload.uploaded_by_member_id);
    if (payload.proposal_section_id) form.append("proposal_section_id", payload.proposal_section_id);
    return request(`/projects/${projectId}/documents/${documentKey}/versions/upload`, { method: "POST", body: form });
  },



  listReviewFindings(projectId: string, deliverableId: string): Promise<Paginated<ReviewFinding>> {
    return request(`/projects/${projectId}/deliverables/${deliverableId}/review-findings?page=1&page_size=100`);
  },

  createReviewFinding(
    projectId: string,
    deliverableId: string,
    payload: {
      document_id?: string | null;
      finding_type: string;
      status: string;
      source?: string;
      section_ref?: string;
      summary: string;
      details?: string;
      created_by_member_id?: string | null;
    }
  ): Promise<ReviewFinding> {
    return request(`/projects/${projectId}/deliverables/${deliverableId}/review-findings`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateReviewFinding(
    projectId: string,
    deliverableId: string,
    findingId: string,
    payload: {
      document_id?: string | null;
      finding_type: string;
      status: string;
      source?: string;
      section_ref?: string;
      summary: string;
      details?: string;
    }
  ): Promise<ReviewFinding> {
    return request(`/projects/${projectId}/deliverables/${deliverableId}/review-findings/${findingId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  listDocuments(projectId: string, params?: {
    scope?: string;
    status?: string;
    search?: string;
  }): Promise<Paginated<DocumentListItem>> {
    const query = new URLSearchParams({ page: "1", page_size: "100" });
    if (params?.scope) query.set("scope", params.scope);
    if (params?.status) query.set("status", params.status);
    if (params?.search) query.set("search", params.search);
    return request(`/projects/${projectId}/documents?${query.toString()}`);
  },

  getDocumentVersion(projectId: string, documentId: string): Promise<DocumentVersion> {
    return request(`/projects/${projectId}/documents/${documentId}`);
  },

  listDocumentVersions(projectId: string, documentKey: string): Promise<DocumentVersionList> {
    return request(`/projects/${projectId}/documents/by-key/${documentKey}/versions`);
  },

  reindexDocument(projectId: string, documentId: string, asyncJob = true): Promise<ReindexResult> {
    return request(`/projects/${projectId}/documents/${documentId}/reindex?async_job=${asyncJob ? "true" : "false"}`, {
      method: "POST",
    });
  },

  linkDocument(projectId: string, payload: {
    url: string;
    scope: string;
    title: string;
    metadata_json?: Record<string, unknown>;
    wp_id?: string;
    task_id?: string;
    deliverable_id?: string;
    milestone_id?: string;
    uploaded_by_member_id?: string;
    proposal_section_id?: string;
  }): Promise<DocumentVersion> {
    return request(`/projects/${projectId}/documents/link`, { method: "POST", body: JSON.stringify(payload) });
  },

  refreshDocument(projectId: string, documentId: string): Promise<DocumentVersion> {
    return request(`/projects/${projectId}/documents/${documentId}/refresh`, { method: "POST" });
  },

  listProposalTemplates(search = "", activeOnly = false, callLibraryEntryId?: string): Promise<Paginated<ProposalTemplate>> {
    const query = new URLSearchParams({ page: "1", page_size: "200" });
    if (search) query.set("search", search);
    if (activeOnly) query.set("active_only", "true");
    if (callLibraryEntryId) query.set("call_library_entry_id", callLibraryEntryId);
    return request(`/proposal-templates?${query.toString()}`);
  },

  getProposalTemplate(templateId: string): Promise<ProposalTemplate> {
    return request(`/proposal-templates/${templateId}`);
  },

  createProposalTemplate(payload: {
    call_library_entry_id?: string | null;
    name: string;
    funding_program: string;
    description?: string | null;
    is_active?: boolean;
    sections?: Array<{
      key: string;
      title: string;
      guidance?: string | null;
      position?: number;
      required?: boolean;
      scope_hint?: string;
    }>;
  }): Promise<ProposalTemplate> {
    return request("/proposal-templates", { method: "POST", body: JSON.stringify(payload) });
  },

  updateProposalTemplate(templateId: string, payload: {
    call_library_entry_id?: string | null;
    name?: string;
    funding_program?: string;
    description?: string | null;
    is_active?: boolean;
  }): Promise<ProposalTemplate> {
    return request(`/proposal-templates/${templateId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteProposalTemplate(templateId: string): Promise<void> {
    return request(`/proposal-templates/${templateId}`, { method: "DELETE" });
  },

  createProposalTemplateSection(templateId: string, payload: {
    key: string;
    title: string;
    guidance?: string | null;
    position?: number;
    required?: boolean;
    scope_hint?: string;
  }): Promise<ProposalTemplate> {
    return request(`/proposal-templates/${templateId}/sections`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateProposalTemplateSection(templateId: string, sectionId: string, payload: {
    key?: string;
    title?: string;
    guidance?: string | null;
    position?: number;
    required?: boolean;
    scope_hint?: string;
  }): Promise<ProposalTemplate> {
    return request(`/proposal-templates/${templateId}/sections/${sectionId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteProposalTemplateSection(templateId: string, sectionId: string): Promise<ProposalTemplate> {
    return request(`/proposal-templates/${templateId}/sections/${sectionId}`, { method: "DELETE" });
  },

  listProjectProposalSections(projectId: string): Promise<{ items: ProjectProposalSection[] }> {
    return request(`/projects/${projectId}/proposal-sections`);
  },

  getProposalCallBrief(projectId: string): Promise<ProposalCallBrief> {
    return request(`/projects/${projectId}/proposal-call-brief`);
  },

  listProposalCallLibrary(search = "", activeOnly = true): Promise<{ items: ProposalCallLibraryEntry[]; page: number; page_size: number; total: number }> {
    const query = new URLSearchParams({ page: "1", page_size: "50", active_only: String(activeOnly) });
    if (search.trim()) query.set("search", search.trim());
    return request(`/proposal-call-library?${query.toString()}`);
  },

  createProposalCallLibraryEntry(payload: {
    call_title: string;
    funder_name?: string | null;
    programme_name?: string | null;
    reference_code?: string | null;
    submission_deadline?: string | null;
    source_url?: string | null;
    summary?: string | null;
    eligibility_notes?: string | null;
    budget_notes?: string | null;
    scoring_notes?: string | null;
    requirements_text?: string | null;
    is_active?: boolean;
  }): Promise<ProposalCallLibraryEntry> {
    return request(`/proposal-call-library`, { method: "POST", body: JSON.stringify(payload) });
  },

  deleteProposalCallLibraryEntry(libraryEntryId: string): Promise<void> {
    return request(`/proposal-call-library/${libraryEntryId}`, { method: "DELETE" });
  },

  ingestProposalCallLibraryPdf(file: File, payload?: { library_entry_id?: string; source_url?: string | null; category?: string | null }): Promise<{ entry: ProposalCallLibraryEntry; document: ProposalCallLibraryDocument }> {
    const form = new FormData();
    form.append("file", file);
    if (payload?.library_entry_id) form.append("library_entry_id", payload.library_entry_id);
    if (payload?.source_url) form.append("source_url", payload.source_url);
    if (payload?.category) form.append("category", payload.category);
    return request(`/proposal-call-library/ingest-pdf`, { method: "POST", body: form });
  },

  startProposalCallLibraryIngestJob(file: File, payload?: { library_entry_id?: string; source_url?: string | null; category?: string | null }): Promise<ProposalCallIngestJob> {
    const form = new FormData();
    form.append("file", file);
    if (payload?.library_entry_id) form.append("library_entry_id", payload.library_entry_id);
    if (payload?.source_url) form.append("source_url", payload.source_url);
    if (payload?.category) form.append("category", payload.category);
    return request(`/proposal-call-library/ingest-pdf-jobs`, { method: "POST", body: form });
  },

  getProposalCallLibraryIngestJob(jobId: string): Promise<ProposalCallIngestJob> {
    return request(`/proposal-call-library/ingest-pdf-jobs/${jobId}`);
  },

  listProposalCallLibraryDocuments(libraryEntryId: string, includeSuperseded = true): Promise<{ items: ProposalCallLibraryDocument[] }> {
    const query = new URLSearchParams({ include_superseded: String(includeSuperseded) });
    return request(`/proposal-call-library/${libraryEntryId}/documents?${query.toString()}`);
  },

  updateProposalCallLibraryDocument(
    libraryEntryId: string,
    documentId: string,
    payload: { category?: string; status?: string },
  ): Promise<ProposalCallLibraryDocument> {
    return request(`/proposal-call-library/${libraryEntryId}/documents/${documentId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteProposalCallLibraryDocument(libraryEntryId: string, documentId: string): Promise<void> {
    return request(`/proposal-call-library/${libraryEntryId}/documents/${documentId}`, { method: "DELETE" });
  },

  reindexProposalCallLibraryDocument(libraryEntryId: string, documentId: string): Promise<ProposalCallDocumentReindexResult> {
    return request(`/proposal-call-library/${libraryEntryId}/documents/${documentId}/reindex`, { method: "POST" });
  },

  upsertProposalCallBrief(projectId: string, payload: {
    call_title?: string | null;
    funder_name?: string | null;
    programme_name?: string | null;
    reference_code?: string | null;
    submission_deadline?: string | null;
    source_url?: string | null;
    summary?: string | null;
    eligibility_notes?: string | null;
    budget_notes?: string | null;
    scoring_notes?: string | null;
    requirements_text?: string | null;
  }): Promise<ProposalCallBrief> {
    return request(`/projects/${projectId}/proposal-call-brief`, { method: "PUT", body: JSON.stringify(payload) });
  },

  importProposalCallBrief(projectId: string, libraryEntryId: string): Promise<ProposalCallBrief> {
    return request(`/projects/${projectId}/proposal-call-brief/import`, {
      method: "POST",
      body: JSON.stringify({ library_entry_id: libraryEntryId }),
    });
  },

  askProposalCallQuestion(projectId: string, question: string): Promise<ProposalCallAnswer> {
    return request(`/projects/${projectId}/proposal-call/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  },

  updateProjectProposalSection(projectId: string, sectionId: string, payload: {
    title?: string;
    guidance?: string | null;
    position?: number;
    required?: boolean;
    scope_hint?: string;
    status?: string;
    owner_member_id?: string | null;
    reviewer_member_id?: string | null;
    due_date?: string | null;
    notes?: string | null;
    content?: string | null;
    preserve_yjs_state?: boolean;
  }): Promise<ProjectProposalSection> {
    return request(`/projects/${projectId}/proposal-sections/${sectionId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  listProposalSubmissionRequirements(projectId: string): Promise<{ items: ProposalSubmissionRequirement[] }> {
    return request(`/projects/${projectId}/proposal-submission-requirements`);
  },

  createProposalSubmissionRequirement(projectId: string, payload: {
    title: string;
    description?: string | null;
    document_type: string;
    format_hint: string;
    required?: boolean;
    position?: number;
    template_id?: string | null;
  }): Promise<ProposalSubmissionRequirement> {
    return request(`/projects/${projectId}/proposal-submission-requirements`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateProposalSubmissionRequirement(projectId: string, requirementId: string, payload: {
    title?: string;
    description?: string | null;
    document_type?: string;
    format_hint?: string;
    required?: boolean;
    position?: number;
    template_id?: string | null;
  }): Promise<ProposalSubmissionRequirement> {
    return request(`/projects/${projectId}/proposal-submission-requirements/${requirementId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  updateProposalSubmissionItem(projectId: string, itemId: string, payload: {
    assignee_member_id?: string | null;
    status?: string;
    notes?: string | null;
    latest_uploaded_document_id?: string | null;
  }): Promise<ProposalSubmissionItem> {
    return request(`/projects/${projectId}/proposal-submission-items/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  listProposalReviewFindings(projectId: string, proposalSectionId?: string, reviewKind = "general"): Promise<{ items: ProposalReviewFinding[]; page: number; page_size: number; total: number }> {
    const query = new URLSearchParams();
    if (proposalSectionId) query.set("proposal_section_id", proposalSectionId);
    query.set("review_kind", reviewKind);
    query.set("page", "1");
    query.set("page_size", "200");
    return request(`/projects/${projectId}/proposal-review-findings?${query}`);
  },
  createProposalReviewFinding(projectId: string, payload: Record<string, unknown>): Promise<ProposalReviewFinding> {
    return request(`/projects/${projectId}/proposal-review-findings`, { method: "POST", body: JSON.stringify(payload) });
  },
  updateProposalReviewFinding(projectId: string, findingId: string, payload: Record<string, unknown>): Promise<ProposalReviewFinding> {
    return request(`/projects/${projectId}/proposal-review-findings/${findingId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },
  deleteProposalReviewFinding(projectId: string, findingId: string): Promise<void> {
    return request(`/projects/${projectId}/proposal-review-findings/${findingId}`, { method: "DELETE" });
  },
  async uploadProposalImage(projectId: string, file: File): Promise<ProposalImage> {
    const form = new FormData();
    form.append("file", file);
    const result = await request<ProposalImage>(`/projects/${projectId}/proposal-images/upload`, {
      method: "POST",
      body: form,
    });
    // The backend returns a relative path like /api/v1/projects/…/content.
    // Resolve it against the API base so the <img> src works from the browser.
    if (result.url && result.url.startsWith("/")) {
      const origin = new URL(API_BASE).origin;
      result.url = `${origin}${result.url}`;
    }
    return result;
  },

  runProposalReview(projectId: string, proposalSectionId?: string | null): Promise<{ created: ProposalReviewFinding[] }> {
    return request(`/projects/${projectId}/proposal-review/run`, {
      method: "POST",
      body: JSON.stringify({ proposal_section_id: proposalSectionId || null }),
    });
  },

  runProposalCallCompliance(projectId: string, proposalSectionId?: string | null): Promise<{ created: ProposalReviewFinding[] }> {
    return request(`/projects/${projectId}/proposal-call-compliance/run`, {
      method: "POST",
      body: JSON.stringify({ proposal_section_id: proposalSectionId || null }),
    });
  },

  async exportProposalPdf(projectId: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/proposal/export-pdf`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!res.ok) throw new Error(`Failed to export proposal PDF: ${res.status}`);
    return res.blob();
  },

  listProjectMemberships(projectId: string): Promise<Paginated<ProjectMembership>> {
    return request(`/projects/${projectId}/memberships?page=1&page_size=100`);
  },

  upsertProjectMembership(
    projectId: string,
    payload: { user_id: string; role: string }
  ): Promise<ProjectMembership> {
    return request(`/projects/${projectId}/memberships`, { method: "POST", body: JSON.stringify(payload) });
  },

  listProjectRooms(projectId: string): Promise<Paginated<ProjectChatRoom>> {
    return request(`/projects/${projectId}/rooms?page=1&page_size=100`);
  },

  createProjectRoom(
    projectId: string,
    payload: { name: string; description?: string; scope_type?: string; scope_ref_id?: string | null }
  ): Promise<ProjectChatRoom> {
    return request(`/projects/${projectId}/rooms`, { method: "POST", body: JSON.stringify(payload) });
  },

  addRoomMember(projectId: string, roomId: string, payload: { user_id: string }): Promise<ProjectChatRoom> {
    return request(`/projects/${projectId}/rooms/${roomId}/members`, { method: "POST", body: JSON.stringify(payload) });
  },

  removeRoomMember(projectId: string, roomId: string, userId: string): Promise<ProjectChatRoom> {
    return request(`/projects/${projectId}/rooms/${roomId}/members/${userId}`, { method: "DELETE" });
  },

  listRoomMessages(projectId: string, roomId: string, options?: { page?: number; pageSize?: number }): Promise<Paginated<ProjectChatMessage>> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 500;
    return request(`/projects/${projectId}/rooms/${roomId}/messages?page=${page}&page_size=${pageSize}`);
  },

  ensureResearchStudyChatRoom(projectId: string, collectionId: string, spaceId?: string | null): Promise<StudyChatRoom> {
    const query = new URLSearchParams();
    if (spaceId) query.set("space_id", spaceId);
    return request(`/projects/${projectId}/research/collections/${collectionId}/chat-room${query.size ? `?${query.toString()}` : ""}`, {
      method: "POST",
    });
  },

  listStudyChatMessages(
    projectId: string,
    collectionId: string,
    options?: { page?: number; pageSize?: number; spaceId?: string | null }
  ): Promise<Paginated<StudyChatMessage>> {
    const query = new URLSearchParams();
    query.set("page", String(options?.page ?? 1));
    query.set("page_size", String(options?.pageSize ?? 100));
    if (options?.spaceId) query.set("space_id", options.spaceId);
    return request(`/projects/${projectId}/research/collections/${collectionId}/chat/messages?${query.toString()}`);
  },

  createStudyChatMessage(
    projectId: string,
    collectionId: string,
    payload: { content: string; reply_to_message_id?: string | null },
    spaceId?: string | null
  ): Promise<StudyChatMessage> {
    const query = new URLSearchParams();
    if (spaceId) query.set("space_id", spaceId);
    return request(`/projects/${projectId}/research/collections/${collectionId}/chat/messages${query.size ? `?${query.toString()}` : ""}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  toggleStudyChatReaction(
    projectId: string,
    collectionId: string,
    messageId: string,
    payload: { emoji: string },
    spaceId?: string | null
  ): Promise<StudyChatMessage> {
    const query = new URLSearchParams();
    if (spaceId) query.set("space_id", spaceId);
    return request(`/projects/${projectId}/research/collections/${collectionId}/chat/messages/${messageId}/reactions${query.size ? `?${query.toString()}` : ""}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  createRoomMessage(
    projectId: string,
    roomId: string,
    payload: { content: string; reply_to_message_id?: string | null }
  ): Promise<ProjectChatMessage> {
    return request(`/projects/${projectId}/rooms/${roomId}/messages`, { method: "POST", body: JSON.stringify(payload) });
  },

  toggleRoomMessageReaction(
    projectId: string,
    roomId: string,
    messageId: string,
    payload: { emoji: string }
  ): Promise<ProjectChatMessage> {
    return request(`/projects/${projectId}/rooms/${roomId}/messages/${messageId}/reactions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listProjectBroadcasts(projectId: string, options?: { page?: number; pageSize?: number }): Promise<Paginated<ProjectBroadcast>> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    return request(`/projects/${projectId}/broadcasts?page=${page}&page_size=${pageSize}`);
  },

  createProjectBroadcast(
    projectId: string,
    payload: { title: string; body: string; severity: string; deliver_telegram: boolean }
  ): Promise<ProjectBroadcast> {
    return request(`/projects/${projectId}/broadcasts`, { method: "POST", body: JSON.stringify(payload) });
  },

  listLabBroadcasts(labId: string, options?: { page?: number; pageSize?: number }): Promise<Paginated<ProjectBroadcast>> {
    const page = options?.page ?? 1;
    const pageSize = options?.pageSize ?? 20;
    return request(`/resources/labs/${labId}/broadcasts?page=${page}&page_size=${pageSize}`);
  },

  createLabBroadcast(
    labId: string,
    payload: { title: string; body: string; severity: string; deliver_telegram: boolean }
  ): Promise<ProjectBroadcast> {
    return request(`/resources/labs/${labId}/broadcasts`, { method: "POST", body: JSON.stringify(payload) });
  },



  listMeetings(projectId: string, params?: { search?: string; source_type?: string }): Promise<Paginated<MeetingRecord>> {
    const query = new URLSearchParams({ page: "1", page_size: "100" });
    if (params?.search) query.set("search", params.search);
    if (params?.source_type) query.set("source_type", params.source_type);
    return request(`/projects/${projectId}/meetings?${query.toString()}`);
  },

  createMeeting(
    projectId: string,
    payload: {
      title: string;
      starts_at: string;
      source_type: string;
      source_url?: string;
      participants: string[];
      content_text: string;
      linked_document_id?: string | null;
      created_by_member_id?: string | null;
    }
  ): Promise<MeetingRecord> {
    return request(`/projects/${projectId}/meetings`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateMeeting(
    projectId: string,
    meetingId: string,
    payload: {
      title: string;
      starts_at: string;
      source_type: string;
      source_url?: string;
      participants: string[];
      content_text: string;
      linked_document_id?: string | null;
    }
  ): Promise<MeetingRecord> {
    return request(`/projects/${projectId}/meetings/${meetingId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  uploadMeetingTranscript(projectId: string, formData: FormData): Promise<MeetingRecord> {
    return request(`/projects/${projectId}/meetings/upload`, { method: "POST", body: formData });
  },

  deleteMeeting(projectId: string, meetingId: string): Promise<void> {
    return request(`/projects/${projectId}/meetings/${meetingId}`, { method: "DELETE" });
  },

  listActionItems(projectId: string, meetingId: string, status?: string): Promise<Paginated<MeetingActionItem>> {
    const query = new URLSearchParams({ page: "1", page_size: "100" });
    if (status) query.set("status", status);
    return request(`/projects/${projectId}/meetings/${meetingId}/action-items?${query.toString()}`);
  },

  createActionItem(
    projectId: string,
    meetingId: string,
    payload: {
      description: string;
      assignee_name?: string | null;
      assignee_member_id?: string | null;
      due_date?: string | null;
      priority?: string;
      source?: string;
    }
  ): Promise<MeetingActionItem> {
    return request(`/projects/${projectId}/meetings/${meetingId}/action-items`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateActionItem(
    projectId: string,
    meetingId: string,
    itemId: string,
    payload: {
      description?: string;
      assignee_name?: string | null;
      assignee_member_id?: string | null;
      due_date?: string | null;
      priority?: string;
      status?: string;
    }
  ): Promise<MeetingActionItem> {
    return request(`/projects/${projectId}/meetings/${meetingId}/action-items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  promoteActionItem(projectId: string, meetingId: string, itemId: string, wpId: string): Promise<MeetingActionItem> {
    return request(`/projects/${projectId}/meetings/${meetingId}/action-items/${itemId}/promote`, {
      method: "POST",
      body: JSON.stringify({ wp_id: wpId }),
    });
  },

  extractMeetingActions(
    projectId: string,
    meetingId: string
  ): Promise<{ summary: string | null; items: MeetingActionItem[] }> {
    return request(`/projects/${projectId}/meetings/${meetingId}/extract-actions`, { method: "POST" });
  },

  listCalendarIntegrations(projectId: string): Promise<Paginated<CalendarIntegration>> {
    return request(`/projects/${projectId}/calendar-integrations`);
  },

  listCalendarImports(projectId: string): Promise<Paginated<CalendarImportBatch>> {
    return request(`/projects/${projectId}/calendar-imports`);
  },

  connectMicrosoft365Calendar(projectId: string): Promise<{ auth_url: string }> {
    return request(`/projects/${projectId}/calendar-integrations/microsoft365/connect`, { method: "POST" });
  },

  syncMicrosoft365Calendar(
    projectId: string
  ): Promise<{ integration: CalendarIntegration; imported: number; updated: number }> {
    return request(`/projects/${projectId}/calendar-integrations/microsoft365/sync`, { method: "POST" });
  },

  importIcsCalendar(projectId: string, formData: FormData): Promise<{ imported: number; updated: number }> {
    return request(`/projects/${projectId}/calendar-integrations/ics/import`, { method: "POST", body: formData });
  },

  deleteCalendarImport(projectId: string, batchId: string): Promise<void> {
    return request(`/projects/${projectId}/calendar-imports/${batchId}`, { method: "DELETE" });
  },

  listChatConversations(projectId: string): Promise<Paginated<ChatConversation>> {
    return request(`/projects/${projectId}/chat/conversations?page=1&page_size=100`);
  },

  createChatConversation(
    projectId: string,
    payload: { title?: string; created_by_member_id?: string }
  ): Promise<ChatConversation> {
    return request(`/projects/${projectId}/chat/conversations`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateConversation(
    projectId: string,
    conversationId: string,
    payload: { title: string }
  ): Promise<ChatConversation> {
    return request(`/projects/${projectId}/chat/conversations/${conversationId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteConversation(projectId: string, conversationId: string): Promise<void> {
    return request(`/projects/${projectId}/chat/conversations/${conversationId}`, { method: "DELETE" });
  },

  listChatMessages(projectId: string, conversationId: string): Promise<Paginated<ChatMessage>> {
    return request(`/projects/${projectId}/chat/conversations/${conversationId}/messages?page=1&page_size=100`);
  },

  postChatMessage(
    projectId: string,
    conversationId: string,
    payload: { content: string; created_by_member_id?: string }
  ): Promise<ChatMessageExchange> {
    return request(`/projects/${projectId}/chat/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async postChatMessageStream(
    projectId: string,
    conversationId: string,
    payload: { content: string; created_by_member_id?: string },
    handlers: {
      onStart?: () => void;
      onToken?: (token: string) => void;
      onDone?: (exchange: ChatMessageExchange) => void;
      onError?: (detail: string) => void;
    }
  ): Promise<void> {
    const headers = new Headers({ "Content-Type": "application/json" });
    if (authToken) {
      headers.set("Authorization", `Bearer ${authToken}`);
    }
    const response = await fetch(`${API_BASE}/projects/${projectId}/chat/conversations/${conversationId}/messages/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) {
      const body = await response.text();
      try {
        const parsed = JSON.parse(body) as { detail?: unknown };
        throw new Error(formatApiErrorDetail(parsed.detail) || body || `API request failed: ${response.status}`);
      } catch {
        throw new Error(body || `API request failed: ${response.status}`);
      }
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const dispatchEvent = (eventName: string, dataRaw: string) => {
      let data: unknown = {};
      try {
        data = JSON.parse(dataRaw);
      } catch {
        data = {};
      }
      if (eventName === "start") {
        handlers.onStart?.();
        return;
      }
      if (eventName === "token") {
        const token = (data as { token?: unknown }).token;
        if (typeof token === "string") handlers.onToken?.(token);
        return;
      }
      if (eventName === "done") {
        handlers.onDone?.(data as ChatMessageExchange);
        return;
      }
      if (eventName === "error") {
        const detail = (data as { detail?: unknown }).detail;
        handlers.onError?.(typeof detail === "string" ? detail : "Streaming failed.");
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const lines = block.split("\n");
        let eventName = "";
        let dataRaw = "";
        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) dataRaw = line.slice(5).trim();
        }
        if (eventName) dispatchEvent(eventName, dataRaw);
        sep = buffer.indexOf("\n\n");
      }
    }
  },

  // --- My Work ---
  getMyWork(includeClosed = false): Promise<MyWorkResponse> {
    const query = new URLSearchParams();
    if (includeClosed) query.set("include_closed", "true");
    return request(`/my-work?${query.toString()}`);
  },

  // --- Dashboard ---
  getDashboardHealth(projectId: string, scopeType = "project", scopeRefId?: string | null): Promise<DashboardHealth> {
    const query = new URLSearchParams({ scope_type: scopeType });
    if (scopeRefId) query.set("scope_ref_id", scopeRefId);
    return request(`/projects/${projectId}/dashboard/health?${query.toString()}`);
  },

  getDashboardHealthLatest(projectId: string, scopeType = "project", scopeRefId?: string | null): Promise<DashboardHealth | null> {
    const query = new URLSearchParams({ scope_type: scopeType });
    if (scopeRefId) query.set("scope_ref_id", scopeRefId);
    return request(`/projects/${projectId}/dashboard/health-latest?${query.toString()}`);
  },

  getDashboardHealthHistory(projectId: string): Promise<DashboardHealthSnapshot[]> {
    return request(`/projects/${projectId}/dashboard/health-history`);
  },

  getDashboardHealthRecurring(projectId: string): Promise<DashboardRecurringIssue[]> {
    return request(`/projects/${projectId}/dashboard/health-recurring`);
  },

  getDashboardHealthScopeOptions(projectId: string): Promise<DashboardScopeOptions> {
    return request(`/projects/${projectId}/dashboard/health-scope-options`);
  },

  updateDashboardHealthIssueState(
    projectId: string,
    payload: {
      issue_key: string;
      source: string;
      category: string;
      entity_type?: string | null;
      entity_id?: string | null;
      status: string;
      rationale?: string | null;
      snooze_days?: number;
    }
  ): Promise<{ issue_key: string; status: string; rationale: string | null; snoozed_until: string | null }> {
    return request(`/projects/${projectId}/dashboard/health/issues/state`, { method: "POST", body: JSON.stringify(payload) });
  },

  createDashboardHealthIssueInbox(
    projectId: string,
    payload: DashboardHealthIssue
  ): Promise<{ id: string; title: string; status: string }> {
    return request(`/projects/${projectId}/dashboard/health/issues/inbox`, { method: "POST", body: JSON.stringify(payload) });
  },

  listProjectInbox(projectId: string, status = "", page = 1, pageSize = 20): Promise<{ items: ProjectInboxItem[]; page: number; page_size: number; total: number }> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) query.set("status", status);
    return request(`/projects/${projectId}/inbox?${query.toString()}`);
  },

  updateProjectInbox(projectId: string, itemId: string, payload: { status?: string }): Promise<ProjectInboxItem> {
    return request(`/projects/${projectId}/inbox/${itemId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  // --- Todos ---
  listTodos(
    projectId: string,
    params?: { status?: string; assignee_member_id?: string; wp_id?: string; task_id?: string; page?: number; page_size?: number }
  ): Promise<Paginated<ProjectTodo>> {
    const query = new URLSearchParams({ page: String(params?.page ?? 1), page_size: String(params?.page_size ?? 50) });
    if (params?.status) query.set("status", params.status);
    if (params?.assignee_member_id) query.set("assignee_member_id", params.assignee_member_id);
    if (params?.wp_id) query.set("wp_id", params.wp_id);
    if (params?.task_id) query.set("task_id", params.task_id);
    return request(`/projects/${projectId}/todos?${query.toString()}`);
  },

  createTodo(
    projectId: string,
    payload: {
      title: string;
      description?: string | null;
      priority?: string;
      assignee_member_id?: string | null;
      wp_id?: string | null;
      task_id?: string | null;
      due_date?: string | null;
      sort_order?: number;
    }
  ): Promise<ProjectTodo> {
    return request(`/projects/${projectId}/todos`, { method: "POST", body: JSON.stringify(payload) });
  },

  updateTodo(
    projectId: string,
    todoId: string,
    payload: {
      title?: string;
      description?: string | null;
      status?: string;
      priority?: string;
      assignee_member_id?: string | null;
      wp_id?: string | null;
      task_id?: string | null;
      due_date?: string | null;
      sort_order?: number;
    }
  ): Promise<ProjectTodo> {
    return request(`/projects/${projectId}/todos/${todoId}`, { method: "PATCH", body: JSON.stringify(payload) });
  },

  deleteTodo(projectId: string, todoId: string): Promise<void> {
    return request(`/projects/${projectId}/todos/${todoId}`, { method: "DELETE" });
  },

  // --- Reports ---
  async getStatusReport(projectId: string): Promise<string> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/reports/status`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!res.ok) throw new Error(`Failed to fetch status report: ${res.status}`);
    return res.text();
  },
  async getMeetingReport(projectId: string, meetingId: string): Promise<string> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/reports/meeting/${meetingId}`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!res.ok) throw new Error(`Failed to fetch meeting report: ${res.status}`);
    return res.text();
  },
  async getAuditLogCsv(projectId: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/reports/audit-log`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!res.ok) throw new Error(`Failed to fetch audit log: ${res.status}`);
    return res.blob();
  },

  // --- Notifications ---
  listNotifications(projectId?: string, unreadOnly = false, page = 1, pageSize = 20): Promise<{ items: AppNotification[]; page: number; page_size: number; total: number }> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (projectId) query.set("project_id", projectId);
    if (unreadOnly) query.set("unread_only", "true");
    return request(`/notifications?${query}`);
  },
  notificationUnreadCount(projectId?: string): Promise<{ count: number }> {
    const query = new URLSearchParams();
    if (projectId) query.set("project_id", projectId);
    return request(`/notifications/unread-count?${query}`);
  },
  markNotificationRead(notificationId: string): Promise<{ ok: boolean }> {
    return request(`/notifications/${notificationId}/read`, { method: "POST" });
  },
  markAllNotificationsRead(projectId?: string): Promise<{ marked_read: number }> {
    const query = new URLSearchParams();
    if (projectId) query.set("project_id", projectId);
    return request(`/notifications/read-all?${query}`, { method: "POST" });
  },

  // ── Search ──
  searchProject(projectId: string, q: string, opts?: { scope?: string; top_k?: number }): Promise<SearchResponse> {
    const query = new URLSearchParams({ q });
    if (opts?.scope) query.set("scope", opts.scope);
    if (opts?.top_k) query.set("top_k", String(opts.top_k));
    return request(`/projects/${projectId}/search?${query}`);
  },
  embedBackfill(projectId: string): Promise<{ documents: number; meetings: number; research?: number }> {
    return request(`/projects/${projectId}/search/embed-backfill`, { method: "POST" });
  },

  // ── Research Workspace ──

  listResearchCollections(projectId: string, opts?: { space_id?: string; status?: string; member_id?: string; page?: number; page_size?: number }): Promise<{ items: ResearchCollection[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.space_id) q.set("space_id", opts.space_id);
    if (opts?.status) q.set("status", opts.status);
    if (opts?.member_id) q.set("member_id", opts.member_id);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/projects/${projectId}/research/collections?${q}`);
  },
  listResearchSpaces(opts?: { page?: number; page_size?: number }): Promise<{ items: ResearchSpace[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/projects/research/spaces?${q}`);
  },
  createResearchSpace(payload: {
    title: string;
    focus?: string | null;
    linked_project_id?: string | null;
  }): Promise<ResearchSpace> {
    return request("/projects/research/spaces", { method: "POST", body: JSON.stringify(payload) });
  },
  updateResearchSpace(
    spaceId: string,
    payload: {
      title?: string;
      focus?: string | null;
      linked_project_id?: string | null;
    }
  ): Promise<ResearchSpace> {
    return request(`/projects/research/spaces/${spaceId}`, { method: "PUT", body: JSON.stringify(payload) });
  },
  createResearchCollection(projectId: string, data: {
    title: string;
    space_ids?: string[];
    description?: string;
    hypothesis?: string;
    open_questions?: string[];
    tags?: string[];
    overleaf_url?: string;
    target_output_title?: string;
    output_status?: string;
  }, spaceId?: string): Promise<ResearchCollection> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections${q}`, { method: "POST", body: JSON.stringify(data) });
  },
  getResearchCollection(projectId: string, collectionId: string, spaceId?: string): Promise<ResearchCollectionDetail> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}${q}`);
  },
  auditResearchPaperClaims(projectId: string, collectionId: string, spaceId?: string): Promise<ResearchCollectionDetail> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/paper/audit-claims${q}`, { method: "POST" });
  },
  buildResearchPaperOutline(projectId: string, collectionId: string, spaceId?: string): Promise<ResearchCollectionDetail> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/paper/build-outline${q}`, { method: "POST" });
  },
  draftResearchPaperFromGap(projectId: string, collectionId: string, spaceId?: string): Promise<ResearchCollectionDetail> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/paper/draft-from-gap${q}`, { method: "POST" });
  },
  reviewResearchIteration(projectId: string, collectionId: string, iterationId: string, spaceId?: string): Promise<ResearchCollectionDetail> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/iterations/${iterationId}/review${q}`, { method: "POST" });
  },
  compareResearchResults(projectId: string, collectionId: string, spaceId?: string): Promise<ResearchResultComparison> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/results/compare${q}`, { method: "POST" });
  },
  updateResearchCollection(projectId: string, collectionId: string, data: Record<string, unknown>, spaceId?: string): Promise<ResearchCollection> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}${q}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteResearchCollection(projectId: string, collectionId: string, spaceId?: string): Promise<void> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}${q}`, { method: "DELETE" });
  },

  listCollectionMembers(projectId: string, collectionId: string, spaceId?: string): Promise<ResearchCollectionMember[]> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/members${q}`);
  },
  addCollectionMember(projectId: string, collectionId: string, data: { member_id?: string; user_id?: string; role?: string }, spaceId?: string): Promise<ResearchCollectionMember> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/members${q}`, { method: "POST", body: JSON.stringify(data) });
  },
  updateCollectionMember(projectId: string, collectionId: string, collectionMemberId: string, data: { role: string }, spaceId?: string): Promise<ResearchCollectionMember> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/members/${collectionMemberId}${q}`, { method: "PUT", body: JSON.stringify(data) });
  },
  removeCollectionMember(projectId: string, collectionId: string, collectionMemberId: string, spaceId?: string): Promise<void> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/members/${collectionMemberId}${q}`, { method: "DELETE" });
  },

  setCollectionWbsLinks(projectId: string, collectionId: string, data: { wp_ids: string[]; task_ids: string[]; deliverable_ids: string[] }, spaceId?: string): Promise<{ wp_ids: string[]; task_ids: string[]; deliverable_ids: string[] }> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/wbs-links${q}`, { method: "PUT", body: JSON.stringify(data) });
  },
  setCollectionMeetings(projectId: string, collectionId: string, data: { meeting_ids: string[] }, spaceId?: string): Promise<ResearchCollectionDetail["meetings"]> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/meetings${q}`, { method: "PUT", body: JSON.stringify(data) });
  },

  listResearchReferences(projectId: string, opts?: { space_id?: string; collection_id?: string; reading_status?: string; tag?: string; q?: string; page?: number; page_size?: number }): Promise<{ items: ResearchReference[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.space_id) q.set("space_id", opts.space_id);
    if (opts?.collection_id) q.set("collection_id", opts.collection_id);
    if (opts?.reading_status) q.set("reading_status", opts.reading_status);
    if (opts?.tag) q.set("tag", opts.tag);
    if (opts?.q) q.set("q", opts.q);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/projects/${projectId}/research/references?${q}`);
  },
  createResearchReference(projectId: string, data: Record<string, unknown>, spaceId?: string): Promise<ResearchReference> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references${q}`, { method: "POST", body: JSON.stringify(data) });
  },
  importBibtexReferences(projectId: string, bibtex: string, collectionId?: string | null, spaceId?: string): Promise<{ created: ResearchReference[]; errors: string[] }> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/import-bibtex${q}`, {
      method: "POST",
      body: JSON.stringify({ bibtex, collection_id: collectionId || null }),
    });
  },
  getResearchReference(projectId: string, refId: string, spaceId?: string): Promise<ResearchReference> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/${refId}${q}`);
  },
  updateResearchReference(projectId: string, refId: string, data: Record<string, unknown>, spaceId?: string): Promise<ResearchReference> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/${refId}${q}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteResearchReference(projectId: string, refId: string, spaceId?: string): Promise<void> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/${refId}${q}`, { method: "DELETE" });
  },
  moveResearchReference(projectId: string, refId: string, collectionId: string | null, spaceId?: string): Promise<ResearchReference> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/${refId}/move${q}`, { method: "PUT", body: JSON.stringify({ collection_id: collectionId }) });
  },
  updateReferenceStatus(projectId: string, refId: string, readingStatus: string, spaceId?: string): Promise<ResearchReference> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/${refId}/status${q}`, { method: "PUT", body: JSON.stringify({ reading_status: readingStatus }) });
  },
  listBibliographyReferences(
    projectId: string,
    opts?: { q?: string; visibility?: string; page?: number; page_size?: number }
  ): Promise<{ items: BibliographyReference[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.q) q.set("q", opts.q);
    if (opts?.visibility) q.set("visibility", opts.visibility);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/projects/${projectId}/research/bibliography?${q}`);
  },
  createBibliographyReference(projectId: string, data: Record<string, unknown>): Promise<BibliographyReference> {
    return request(`/projects/${projectId}/research/bibliography`, { method: "POST", body: JSON.stringify(data) });
  },
  updateBibliographyReference(projectId: string, bibliographyReferenceId: string, data: Record<string, unknown>): Promise<BibliographyReference> {
    return request(`/projects/${projectId}/research/bibliography/${bibliographyReferenceId}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteBibliographyReference(projectId: string, bibliographyReferenceId: string): Promise<void> {
    return request(`/projects/${projectId}/research/bibliography/${bibliographyReferenceId}`, { method: "DELETE" });
  },
  importBibliographyBibtex(projectId: string, bibtex: string, visibility = "shared"): Promise<{ created: BibliographyReference[]; errors: string[] }> {
    return request(`/projects/${projectId}/research/bibliography/import-bibtex`, {
      method: "POST",
      body: JSON.stringify({ bibtex, visibility }),
    });
  },
  linkBibliographyReference(
    projectId: string,
    payload: { bibliography_reference_id: string; collection_id?: string | null; reading_status?: string },
    spaceId?: string,
  ): Promise<ResearchReference> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/bibliography/link${q}`, { method: "POST", body: JSON.stringify(payload) });
  },
  uploadBibliographyAttachment(projectId: string, bibliographyReferenceId: string, file: File): Promise<BibliographyReference> {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/projects/${projectId}/research/bibliography/${bibliographyReferenceId}/attachment`, { method: "POST", body: formData });
  },
  getBibliographyAttachment(projectId: string, bibliographyReferenceId: string): Promise<Blob> {
    return requestBlob(`/projects/${projectId}/research/bibliography/${bibliographyReferenceId}/file`);
  },
  listGlobalBibliography(
    opts?: { q?: string; visibility?: string; bibliography_collection_id?: string; page?: number; page_size?: number }
  ): Promise<{ items: BibliographyReference[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.q) q.set("q", opts.q);
    if (opts?.visibility) q.set("visibility", opts.visibility);
    if (opts?.bibliography_collection_id) q.set("bibliography_collection_id", opts.bibliography_collection_id);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/bibliography?${q}`);
  },
  searchGlobalBibliographySemantic(
    query: string,
    opts?: { visibility?: string; top_k?: number }
  ): Promise<{ items: BibliographyReference[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams({ q: query });
    if (opts?.visibility) q.set("visibility", opts.visibility);
    if (opts?.top_k) q.set("top_k", String(opts.top_k));
    return request(`/bibliography/search?${q}`);
  },
  backfillBibliographyEmbeddings(): Promise<{ embedded: number }> {
    return request("/bibliography/embed-backfill", { method: "POST" });
  },
  listBibliographyNotes(bibliographyReferenceId: string): Promise<{ items: BibliographyNote[] }> {
    return request(`/bibliography/${bibliographyReferenceId}/notes`);
  },
  createBibliographyNote(bibliographyReferenceId: string, data: { content: string; note_type?: string; visibility?: string }): Promise<BibliographyNote> {
    return request(`/bibliography/${bibliographyReferenceId}/notes`, { method: "POST", body: JSON.stringify(data) });
  },
  updateBibliographyNote(noteId: string, data: { content?: string; note_type?: string; visibility?: string }): Promise<BibliographyNote> {
    return request(`/bibliography/notes/${noteId}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteBibliographyNote(noteId: string): Promise<void> {
    return request(`/bibliography/notes/${noteId}`, { method: "DELETE" });
  },
  setBibliographyReadingStatus(bibliographyReferenceId: string, readingStatus: string): Promise<{ reading_status: string }> {
    return request(`/bibliography/${bibliographyReferenceId}/status`, { method: "PUT", body: JSON.stringify({ reading_status: readingStatus }) });
  },
  createGlobalBibliography(data: Record<string, unknown>): Promise<BibliographyReference> {
    return request("/bibliography", { method: "POST", body: JSON.stringify(data) });
  },
  updateGlobalBibliography(bibliographyReferenceId: string, data: Record<string, unknown>): Promise<BibliographyReference> {
    return request(`/bibliography/${bibliographyReferenceId}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteGlobalBibliography(bibliographyReferenceId: string): Promise<void> {
    return request(`/bibliography/${bibliographyReferenceId}`, { method: "DELETE" });
  },
  importGlobalBibliographyBibtex(bibtex: string, visibility = "shared"): Promise<{ created: BibliographyReference[]; errors: string[] }> {
    return request("/bibliography/import-bibtex", {
      method: "POST",
      body: JSON.stringify({ bibtex, visibility }),
    });
  },
  importGlobalBibliographyIdentifiers(
    data: { identifiers: string; visibility?: string; source_project_id?: string | null }
  ): Promise<BibliographyIdentifierImportResult> {
    return request("/bibliography/import-identifiers", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  checkGlobalBibliographyDuplicates(data: { title: string; doi?: string | null }): Promise<{ matches: BibliographyDuplicateMatch[] }> {
    return request("/bibliography/check-duplicates", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  buildBibliographyGraph(data: {
    reference_ids: string[];
    include_authors?: boolean;
    include_concepts?: boolean;
    include_tags?: boolean;
    include_semantic?: boolean;
    include_bibliography_collections?: boolean;
    include_research_links?: boolean;
    include_teaching_links?: boolean;
    semantic_threshold?: number;
    semantic_top_k?: number;
  }): Promise<BibliographyGraph> {
    return request("/bibliography/graph", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  uploadGlobalBibliographyAttachment(bibliographyReferenceId: string, sourceProjectId: string, file: File): Promise<BibliographyReference> {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/bibliography/${bibliographyReferenceId}/attachment?source_project_id=${sourceProjectId}`, { method: "POST", body: formData });
  },
  ingestGlobalBibliographyAttachment(
    bibliographyReferenceId: string,
    sourceProjectId?: string | null,
  ): Promise<BibliographyReference> {
    const query = new URLSearchParams();
    if (sourceProjectId) query.set("source_project_id", sourceProjectId);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request(`/bibliography/${bibliographyReferenceId}/ingest${suffix}`, { method: "POST" });
  },
  extractGlobalBibliographyAbstract(bibliographyReferenceId: string): Promise<BibliographyReference> {
    return request(`/bibliography/${bibliographyReferenceId}/extract-abstract`, { method: "POST" });
  },
  extractGlobalBibliographyConcepts(bibliographyReferenceId: string): Promise<BibliographyReference> {
    return request(`/bibliography/${bibliographyReferenceId}/extract-concepts`, { method: "POST" });
  },
  getGlobalBibliographyAttachment(bibliographyReferenceId: string): Promise<Blob> {
    return requestBlob(`/bibliography/${bibliographyReferenceId}/file`);
  },
  listBibliographyCollections(
    opts?: { visibility?: string; page?: number; page_size?: number }
  ): Promise<{ items: BibliographyCollection[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.visibility) q.set("visibility", opts.visibility);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/bibliography/collections?${q}`);
  },
  createBibliographyCollection(data: { title: string; description?: string | null; visibility?: string }): Promise<BibliographyCollection> {
    return request("/bibliography/collections", { method: "POST", body: JSON.stringify(data) });
  },
  updateBibliographyCollection(collectionId: string, data: { title?: string; description?: string | null; visibility?: string }): Promise<BibliographyCollection> {
    return request(`/bibliography/collections/${collectionId}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteBibliographyCollection(collectionId: string): Promise<void> {
    return request(`/bibliography/collections/${collectionId}`, { method: "DELETE" });
  },
  addPaperToBibliographyCollection(collectionId: string, bibliographyReferenceId: string): Promise<void> {
    return request(`/bibliography/collections/${collectionId}/papers`, {
      method: "POST",
      body: JSON.stringify({ bibliography_reference_id: bibliographyReferenceId }),
    });
  },
  removePaperFromBibliographyCollection(collectionId: string, bibliographyReferenceId: string): Promise<void> {
    return request(`/bibliography/collections/${collectionId}/papers/${bibliographyReferenceId}`, { method: "DELETE" });
  },
  listBibliographyCollectionPaperIds(collectionId: string): Promise<string[]> {
    return request(`/bibliography/collections/${collectionId}/paper-ids`);
  },
  bulkLinkBibliographyCollectionToResearch(collectionId: string, payload: { project_id: string; collection_id: string; reading_status?: string }): Promise<{ linked: number }> {
    return request(`/bibliography/collections/${collectionId}/link/research`, { method: "POST", body: JSON.stringify(payload) });
  },
  bulkLinkBibliographyCollectionToTeaching(collectionId: string, payload: { project_id: string }): Promise<{ linked: number }> {
    return request(`/bibliography/collections/${collectionId}/link/teaching`, { method: "POST", body: JSON.stringify(payload) });
  },
  listBibliographyTags(
    opts?: { q?: string; page?: number; page_size?: number }
  ): Promise<{ items: BibliographyTag[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.q) q.set("q", opts.q);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/bibliography/tags?${q}`);
  },

  listResearchNotes(projectId: string, opts?: { space_id?: string; collection_id?: string; lane?: string; note_type?: string; author_member_id?: string; page?: number; page_size?: number }): Promise<{ items: ResearchNote[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.space_id) q.set("space_id", opts.space_id);
    if (opts?.collection_id) q.set("collection_id", opts.collection_id);
    if (opts?.lane !== undefined) q.set("lane", opts.lane);
    if (opts?.note_type) q.set("note_type", opts.note_type);
    if (opts?.author_member_id) q.set("author_member_id", opts.author_member_id);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/projects/${projectId}/research/notes?${q}`);
  },
  createResearchNote(projectId: string, data: Record<string, unknown>, spaceId?: string): Promise<ResearchNote> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/notes${q}`, { method: "POST", body: JSON.stringify(data) });
  },
  getResearchNote(projectId: string, noteId: string, spaceId?: string): Promise<ResearchNote> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/notes/${noteId}${q}`);
  },
  updateResearchNote(projectId: string, noteId: string, data: Record<string, unknown>, spaceId?: string): Promise<ResearchNote> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/notes/${noteId}${q}`, { method: "PUT", body: JSON.stringify(data) });
  },
  deleteResearchNote(projectId: string, noteId: string, spaceId?: string): Promise<void> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/notes/${noteId}${q}`, { method: "DELETE" });
  },
  setNoteReferences(projectId: string, noteId: string, referenceIds: string[], spaceId?: string): Promise<ResearchNote> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/notes/${noteId}/references${q}`, { method: "PUT", body: JSON.stringify({ reference_ids: referenceIds }) });
  },
  listStudyFiles(projectId: string, collectionId: string, opts?: { space_id?: string; page?: number; page_size?: number }): Promise<{ items: ResearchStudyFile[]; page: number; page_size: number; total: number }> {
    const q = new URLSearchParams();
    if (opts?.space_id) q.set("space_id", opts.space_id);
    if (opts?.page) q.set("page", String(opts.page));
    if (opts?.page_size) q.set("page_size", String(opts.page_size));
    return request(`/projects/${projectId}/research/collections/${collectionId}/files?${q}`);
  },
  uploadStudyFile(projectId: string, collectionId: string, file: File, spaceId?: string): Promise<ResearchStudyFile> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    const form = new FormData();
    form.append("file", file);
    return request(`/projects/${projectId}/research/collections/${collectionId}/files${q}`, { method: "POST", body: form });
  },
  deleteStudyFile(projectId: string, collectionId: string, fileId: string, spaceId?: string): Promise<void> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/files/${fileId}${q}`, { method: "DELETE" });
  },
  getStudyFile(projectId: string, collectionId: string, fileId: string, spaceId?: string): Promise<Blob> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return requestBlob(`/projects/${projectId}/research/collections/${collectionId}/files/${fileId}/download${q}`);
  },

  summarizeReference(projectId: string, refId: string, spaceId?: string): Promise<{ ai_summary: string; ai_summary_at: string }> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/references/${refId}/summarize${q}`, { method: "POST" });
  },
  summarizeBibliographyReference(bibliographyReferenceId: string): Promise<{ ai_summary: string; ai_summary_at: string }> {
    return request(`/bibliography/${bibliographyReferenceId}/summarize`, { method: "POST" });
  },
  extractPdfMetadata(projectId: string, documentKey: string): Promise<{ title: string | null; authors: string[]; year: number | null; venue: string | null; abstract: string | null }> {
    return request(`/projects/${projectId}/research/references/extract-from-pdf?document_key=${documentKey}`, { method: "POST" });
  },
  synthesizeCollection(projectId: string, collectionId: string, spaceId?: string): Promise<{ ai_synthesis: string; ai_synthesis_at: string }> {
    const q = spaceId ? `?space_id=${spaceId}` : "";
    return request(`/projects/${projectId}/research/collections/${collectionId}/synthesize${q}`, { method: "POST" });
  },
};
