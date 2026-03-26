import { Fragment, useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBan,
  faCheck,
  faCheckDouble,
  faChevronRight,
  faCircleExclamation,
  faHourglass,
  faPen,
  faPlay,
  faPlus,
  faRotateLeft,
  faTrash,
  faUserPlus,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type {
  AuthUser,
  Member,
  Partner,
  Project,
  ProjectValidationResult,
  TrashedWorkEntity,
  WorkEntity,
} from "../types";

type Props = {
  projects: Project[];
  selectedProjectId: string;
  canCreateProjects: boolean;
  onProjectCreated: (project: Project) => void;
  onProjectUpdated: (project: Project) => void;
};

type SetupSection = "project" | "consortium" | "workplan" | "review";
type EditorKind = "partner" | "member" | "wp" | "task" | "milestone" | "deliverable";
type SelectionKind = "wp" | "task" | "milestone" | "deliverable";
type MemberSourceMode = "existing_user" | "new_user";
type WorkplanTab = "wps" | "deliverables" | "milestones" | "trash";
const WORK_EXECUTION_STATUS_OPTIONS = ["planned", "in_progress", "blocked", "ready_for_closure", "closed"] as const;

const EXEC_STATUS_ICON = {
  planned: { icon: faHourglass, cls: "exec-planned", label: "Planned" },
  in_progress: { icon: faPlay, cls: "exec-progress", label: "In Progress" },
  blocked: { icon: faBan, cls: "exec-blocked", label: "Blocked" },
  ready_for_closure: { icon: faCheckDouble, cls: "exec-ready", label: "Ready for Closure" },
  closed: { icon: faCheck, cls: "exec-closed", label: "Closed" },
} as const;

type WorkSelection = {
  kind: SelectionKind;
  id: string;
};

function filterMembersByPartner(members: Member[], partnerId: string): Member[] {
  return members.filter((member) => member.partner_id === partnerId);
}

function parseReportingDates(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function monthWindowLabel(start: number | null, end: number | null): string {
  if (!start || !end) return "-";
  return `M${start}-M${end}`;
}

function dueMonthLabel(value: number | null): string {
  if (!value) return "-";
  return `M${value}`;
}

export function OnboardingWizard({ projects, selectedProjectId, canCreateProjects, onProjectCreated, onProjectUpdated }: Props) {
  const [activeSection, setActiveSection] = useState<SetupSection>("project");
  const [workplanTab, setWorkplanTab] = useState<WorkplanTab>("wps");
  const [editorKind, setEditorKind] = useState<EditorKind>("partner");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingPartnerId, setEditingPartnerId] = useState<string | null>(null);
  const [editingMemberId, setEditingMemberId] = useState<string | null>(null);
  const [editingWpId, setEditingWpId] = useState<string | null>(null);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editingMilestoneId, setEditingMilestoneId] = useState<string | null>(null);
  const [editingDeliverableId, setEditingDeliverableId] = useState<string | null>(null);
  const [lockedTaskWpId, setLockedTaskWpId] = useState<string | null>(null);
  const [selection, setSelection] = useState<WorkSelection | null>(null);
  const [activeWpId, setActiveWpId] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const [partners, setPartners] = useState<Partner[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [existingUsers, setExistingUsers] = useState<AuthUser[]>([]);
  const [workPackages, setWorkPackages] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [milestones, setMilestones] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);
  const [trashedEntities, setTrashedEntities] = useState<TrashedWorkEntity[]>([]);
  const [validationResult, setValidationResult] = useState<ProjectValidationResult | null>(null);

  const [projectCode, setProjectCode] = useState("");
  const [projectTitle, setProjectTitle] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectLanguage, setProjectLanguage] = useState("en_GB");
  const [projectStartDate, setProjectStartDate] = useState("");
  const [projectDurationMonths, setProjectDurationMonths] = useState(36);
  const [projectReportingDatesText, setProjectReportingDatesText] = useState("");
  const [projectCoordinatorPartnerId, setProjectCoordinatorPartnerId] = useState("");
  const [projectPrincipalInvestigatorId, setProjectPrincipalInvestigatorId] = useState("");

  const [partnerShortName, setPartnerShortName] = useState("");
  const [partnerLegalName, setPartnerLegalName] = useState("");
  const [partnerType, setPartnerType] = useState("beneficiary");
  const [partnerCountry, setPartnerCountry] = useState("");
  const [partnerExpertise, setPartnerExpertise] = useState("");

  const [memberPartnerId, setMemberPartnerId] = useState("");
  const [memberSourceMode, setMemberSourceMode] = useState<MemberSourceMode>("existing_user");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberFullName, setMemberFullName] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("");
  const [memberCreateUserIfMissing, setMemberCreateUserIfMissing] = useState(true);
  const [memberTemporaryPassword, setMemberTemporaryPassword] = useState("");
  const [userDiscoverySearch, setUserDiscoverySearch] = useState("");

  const [wpCode, setWpCode] = useState("");
  const [wpTitle, setWpTitle] = useState("");
  const [wpDescription, setWpDescription] = useState("");
  const [wpStartMonth, setWpStartMonth] = useState(1);
  const [wpEndMonth, setWpEndMonth] = useState(6);
  const [wpLeaderPartnerId, setWpLeaderPartnerId] = useState("");
  const [wpResponsiblePersonId, setWpResponsiblePersonId] = useState("");
  const [wpCollaboratingPartnerIds, setWpCollaboratingPartnerIds] = useState<string[]>([]);
  const [wpExecutionStatus, setWpExecutionStatus] = useState("planned");
  const [wpCompletionNote, setWpCompletionNote] = useState("");

  const [taskWpId, setTaskWpId] = useState("");
  const [taskCode, setTaskCode] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [taskStartMonth, setTaskStartMonth] = useState(1);
  const [taskEndMonth, setTaskEndMonth] = useState(3);
  const [taskLeaderPartnerId, setTaskLeaderPartnerId] = useState("");
  const [taskResponsiblePersonId, setTaskResponsiblePersonId] = useState("");
  const [taskCollaboratingPartnerIds, setTaskCollaboratingPartnerIds] = useState<string[]>([]);
  const [taskExecutionStatus, setTaskExecutionStatus] = useState("planned");
  const [taskCompletionNote, setTaskCompletionNote] = useState("");

  const [milestoneCode, setMilestoneCode] = useState("");
  const [milestoneTitle, setMilestoneTitle] = useState("");
  const [milestoneDescription, setMilestoneDescription] = useState("");
  const [milestoneDueMonth, setMilestoneDueMonth] = useState(6);
  const [milestoneWpIds, setMilestoneWpIds] = useState<string[]>([]);
  const [milestoneLeaderPartnerId, setMilestoneLeaderPartnerId] = useState("");
  const [milestoneResponsiblePersonId, setMilestoneResponsiblePersonId] = useState("");
  const [milestoneCollaboratingPartnerIds, setMilestoneCollaboratingPartnerIds] = useState<string[]>([]);

  const [deliverableWpIds, setDeliverableWpIds] = useState<string[]>([]);
  const [deliverableCode, setDeliverableCode] = useState("");
  const [deliverableTitle, setDeliverableTitle] = useState("");
  const [deliverableDescription, setDeliverableDescription] = useState("");
  const [deliverableDueMonth, setDeliverableDueMonth] = useState(6);
  const [deliverableLeaderPartnerId, setDeliverableLeaderPartnerId] = useState("");
  const [deliverableResponsiblePersonId, setDeliverableResponsiblePersonId] = useState("");
  const [deliverableCollaboratingPartnerIds, setDeliverableCollaboratingPartnerIds] = useState<string[]>([]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const reportingDatesKey = selectedProject ? selectedProject.reporting_dates.join("|") : "";
  useEffect(() => {
    if (!selectedProject) {
      setProjectCode("");
      setProjectTitle("");
      setProjectDescription("");
      setProjectStartDate("");
      setProjectDurationMonths(36);
      setProjectReportingDatesText("");
      setProjectLanguage("en_GB");
      setProjectCoordinatorPartnerId("");
      setProjectPrincipalInvestigatorId("");
      return;
    }
    setProjectCode(selectedProject.code);
    setProjectTitle(selectedProject.title);
    setProjectDescription(selectedProject.description || "");
    setProjectStartDate(selectedProject.start_date);
    setProjectDurationMonths(selectedProject.duration_months);
    setProjectReportingDatesText(selectedProject.reporting_dates.join(", "));
    setProjectLanguage(selectedProject.language || "en_GB");
    setProjectCoordinatorPartnerId(selectedProject.coordinator_partner_id || "");
    setProjectPrincipalInvestigatorId(selectedProject.principal_investigator_id || "");
  }, [
    selectedProjectId,
    selectedProject?.code,
    selectedProject?.title,
    selectedProject?.description,
    selectedProject?.start_date,
    selectedProject?.duration_months,
    selectedProject?.language,
    selectedProject?.coordinator_partner_id,
    selectedProject?.principal_investigator_id,
    reportingDatesKey,
  ]);

  const coordinatorMembers = useMemo(() => filterMembersByPartner(members, projectCoordinatorPartnerId), [members, projectCoordinatorPartnerId]);
  const wpMembers = useMemo(() => filterMembersByPartner(members, wpLeaderPartnerId), [members, wpLeaderPartnerId]);
  const taskMembers = useMemo(() => filterMembersByPartner(members, taskLeaderPartnerId), [members, taskLeaderPartnerId]);
  const milestoneMembers = useMemo(
    () => filterMembersByPartner(members, milestoneLeaderPartnerId),
    [members, milestoneLeaderPartnerId]
  );
  const deliverableMembers = useMemo(
    () => filterMembersByPartner(members, deliverableLeaderPartnerId),
    [members, deliverableLeaderPartnerId]
  );

  const wpById = useMemo(() => Object.fromEntries(workPackages.map((wp) => [wp.id, wp])), [workPackages]);
  const membersByPartner = useMemo(() => {
    const map: Record<string, Member[]> = {};
    members.forEach((member) => {
      if (!map[member.partner_id]) map[member.partner_id] = [];
      map[member.partner_id].push(member);
    });
    Object.values(map).forEach((bucket) => bucket.sort((a, b) => a.full_name.localeCompare(b.full_name)));
    return map;
  }, [members]);
  const existingUserById = useMemo(() => Object.fromEntries(existingUsers.map((user) => [user.id, user])), [existingUsers]);
  const tasksByWp = useMemo(() => {
    const map: Record<string, WorkEntity[]> = {};
    tasks.forEach((task) => {
      const key = task.wp_id || "";
      if (!map[key]) map[key] = [];
      map[key].push(task);
    });
    return map;
  }, [tasks]);

  const checks = useMemo(
    () => [
      { label: "Project baseline", done: Boolean(selectedProject), section: "project" as SetupSection },
      { label: "Partners", done: partners.length > 0, section: "consortium" as SetupSection },
      { label: "Members", done: members.length > 0, section: "consortium" as SetupSection },
      { label: "Work packages", done: workPackages.length > 0, section: "workplan" as SetupSection },
      { label: "Tasks", done: tasks.length > 0, section: "workplan" as SetupSection },
      { label: "Milestones", done: milestones.length > 0, section: "workplan" as SetupSection },
      { label: "Deliverables", done: deliverables.length > 0, section: "workplan" as SetupSection },
    ],
    [selectedProject, partners.length, members.length, workPackages.length, tasks.length, milestones.length, deliverables.length]
  );

  const completedChecks = checks.filter((check) => check.done).length;
  const progressPercent = Math.round((completedChecks / checks.length) * 100);

  const isProposalMode = selectedProject?.project_mode === "proposal";

  const allSectionItems: Array<{ id: SetupSection; title: string; done: boolean; count: string }> = [
    {
      id: "project",
      title: "Project",
      done: Boolean(selectedProject),
      count: selectedProject ? "1" : "0",
    },
    {
      id: "consortium",
      title: "Consortium",
      done: partners.length > 0 && members.length > 0,
      count: `${partners.length}/${members.length}`,
    },
    {
      id: "workplan",
      title: "Workplan",
      done: workPackages.length > 0 && tasks.length > 0,
      count: `${workPackages.length}/${tasks.length}`,
    },
    {
      id: "review",
      title: "Review",
      done: completedChecks === checks.length,
      count: `${completedChecks}/${checks.length}`,
    },
  ];

  const sectionItems = allSectionItems;

  async function loadProjectContext(projectId: string) {
    const [partnersRes, membersRes, usersRes, wpsRes, tasksRes, milestonesRes, deliverablesRes, trashRes] = await Promise.all([
      api.listPartners(projectId),
      api.listMembers(projectId),
      api.listUserDiscovery(1, 200),
      api.listWorkPackages(projectId),
      api.listTasks(projectId),
      api.listMilestones(projectId),
      api.listDeliverables(projectId),
      api.listTrashedWorkEntities(projectId),
    ]);
    setPartners(partnersRes.items);
    setMembers(membersRes.items);
    setExistingUsers(usersRes.items);
    setWorkPackages(wpsRes.items);
    setTasks(tasksRes.items);
    setMilestones(milestonesRes.items);
    setDeliverables(deliverablesRes.items);
    setTrashedEntities(trashRes.items);

    if (wpsRes.items.length > 0) {
      const defaultWpId = activeWpId && wpsRes.items.some((wp) => wp.id === activeWpId) ? activeWpId : wpsRes.items[0].id;
      setActiveWpId(defaultWpId);
      if (!taskWpId) setTaskWpId(defaultWpId);
      if (deliverableWpIds.length === 0) setDeliverableWpIds([defaultWpId]);
    } else {
      setActiveWpId("");
    }
  }

  useEffect(() => {
    if (!selectedProjectId) {
      setPartners([]);
      setMembers([]);
      setExistingUsers([]);
      setWorkPackages([]);
      setTasks([]);
      setMilestones([]);
      setDeliverables([]);
      setTrashedEntities([]);
      setActiveWpId("");
      setSelection(null);
      return;
    }
    setBusy(true);
    setError("");
    loadProjectContext(selectedProjectId)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load project context."))
      .finally(() => setBusy(false));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!activeWpId) return;
    setTaskWpId(activeWpId);
    setDeliverableWpIds((prev) => (prev.length > 0 ? prev : [activeWpId]));
  }, [activeWpId]);

  useEffect(() => {
    if (memberSourceMode !== "existing_user" || !memberUserId) return;
    const selectedUser = existingUserById[memberUserId];
    if (!selectedUser) return;
    setMemberFullName(selectedUser.display_name);
    setMemberEmail(selectedUser.email);
  }, [memberSourceMode, memberUserId, existingUserById]);

  // ── Modal open helpers ──

  function openCreateModal(kind: EditorKind) {
    setEditorKind(kind);
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setEditingMilestoneId(null);
    setEditingDeliverableId(null);
    setLockedTaskWpId(null);
    setEditingTaskId(null);
    if (kind === "partner") {
      setPartnerShortName("");
      setPartnerLegalName("");
      setPartnerType("beneficiary");
      setPartnerCountry("");
      setPartnerExpertise("");
    }
    if (kind === "member") {
      setMemberPartnerId(partners[0]?.id ?? "");
      setMemberSourceMode("existing_user");
      setMemberUserId(existingUsers[0]?.id ?? "");
      setMemberFullName("");
      setMemberEmail("");
      setMemberRole("");
      setMemberCreateUserIfMissing(true);
      setMemberTemporaryPassword("");
    }
    if (kind === "wp") {
      setEditingWpId(null);
      setWpCode("");
      setWpTitle("");
      setWpDescription("");
      setWpStartMonth(1);
      setWpEndMonth(6);
      setWpCollaboratingPartnerIds([]);
      setWpExecutionStatus("planned");
      setWpCompletionNote("");
    }
    if (kind === "task") {
      setTaskWpId(activeWpId || "");
      setTaskCode("");
      setTaskTitle("");
      setTaskDescription("");
      setTaskStartMonth(1);
      setTaskEndMonth(3);
      setTaskCollaboratingPartnerIds([]);
      setTaskExecutionStatus("planned");
      setTaskCompletionNote("");
    }
    if (kind === "milestone") {
      setMilestoneCode("");
      setMilestoneTitle("");
      setMilestoneDescription("");
      setMilestoneDueMonth(6);
      setMilestoneWpIds(activeWpId ? [activeWpId] : []);
      setMilestoneCollaboratingPartnerIds([]);
    }
    if (kind === "deliverable") {
      setDeliverableWpIds(activeWpId ? [activeWpId] : []);
      setDeliverableCode("");
      setDeliverableTitle("");
      setDeliverableDescription("");
      setDeliverableDueMonth(6);
      setDeliverableCollaboratingPartnerIds([]);
    }
    setShowCreateModal(true);
  }

  function openCreateTaskForWp(wpId: string) {
    setEditorKind("task");
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setEditingMilestoneId(null);
    setEditingDeliverableId(null);
    setEditingTaskId(null);
    setTaskWpId(wpId);
    setLockedTaskWpId(wpId);
    setTaskCode("");
    setTaskTitle("");
    setTaskDescription("");
    setTaskStartMonth(1);
    setTaskEndMonth(3);
    setTaskCollaboratingPartnerIds([]);
    setTaskExecutionStatus("planned");
    setTaskCompletionNote("");
    setShowCreateModal(true);
  }

  function openEditWpModal(wp: WorkEntity) {
    setEditorKind("wp");
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setEditingWpId(wp.id);
    setWpCode(wp.code);
    setWpTitle(wp.title);
    setWpDescription(wp.description || "");
    setWpStartMonth(wp.start_month ?? 1);
    setWpEndMonth(wp.end_month ?? (wp.start_month ?? 1));
    setWpLeaderPartnerId(wp.leader_organization_id);
    setWpResponsiblePersonId(wp.responsible_person_id);
    setWpCollaboratingPartnerIds(wp.collaborating_partner_ids);
    setWpExecutionStatus(wp.execution_status || "planned");
    setWpCompletionNote(wp.completion_note || "");
    setShowCreateModal(true);
  }

  function openEditTaskModal(task: WorkEntity) {
    setEditorKind("task");
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setEditingTaskId(task.id);
    setTaskWpId(task.wp_id || "");
    setLockedTaskWpId(task.wp_id || null);
    setTaskCode(task.code);
    setTaskTitle(task.title);
    setTaskDescription(task.description || "");
    setTaskStartMonth(task.start_month ?? 1);
    setTaskEndMonth(task.end_month ?? (task.start_month ?? 1));
    setTaskLeaderPartnerId(task.leader_organization_id);
    setTaskResponsiblePersonId(task.responsible_person_id);
    setTaskCollaboratingPartnerIds(task.collaborating_partner_ids);
    setTaskExecutionStatus(task.execution_status || "planned");
    setTaskCompletionNote(task.completion_note || "");
    setShowCreateModal(true);
  }

  function openEditMilestoneModal(milestone: WorkEntity) {
    setEditorKind("milestone");
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setEditingTaskId(null);
    setEditingWpId(null);
    setEditingMilestoneId(milestone.id);
    setEditingDeliverableId(null);
    setMilestoneCode(milestone.code);
    setMilestoneTitle(milestone.title);
    setMilestoneDescription(milestone.description || "");
    setMilestoneDueMonth(milestone.due_month ?? 1);
    setMilestoneWpIds(milestone.wp_ids || []);
    setMilestoneLeaderPartnerId(milestone.leader_organization_id);
    setMilestoneResponsiblePersonId(milestone.responsible_person_id);
    setMilestoneCollaboratingPartnerIds(milestone.collaborating_partner_ids);
    setShowCreateModal(true);
  }

  function openEditDeliverableModal(deliverable: WorkEntity) {
    setEditorKind("deliverable");
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setEditingTaskId(null);
    setEditingWpId(null);
    setEditingDeliverableId(deliverable.id);
    setEditingMilestoneId(null);
    setDeliverableCode(deliverable.code);
    setDeliverableTitle(deliverable.title);
    setDeliverableDescription(deliverable.description || "");
    setDeliverableDueMonth(deliverable.due_month ?? 1);
    setDeliverableWpIds(deliverable.wp_ids || []);
    setDeliverableLeaderPartnerId(deliverable.leader_organization_id);
    setDeliverableResponsiblePersonId(deliverable.responsible_person_id);
    setDeliverableCollaboratingPartnerIds(deliverable.collaborating_partner_ids);
    setShowCreateModal(true);
  }

  function openCreatePartnerModal() {
    openCreateModal("partner");
  }

  function openEditPartnerModal(partner: Partner) {
    setEditorKind("partner");
    setEditingPartnerId(partner.id);
    setEditingMemberId(null);
    setPartnerShortName(partner.short_name);
    setPartnerLegalName(partner.legal_name);
    setPartnerType(partner.partner_type || "beneficiary");
    setPartnerCountry(partner.country || "");
    setPartnerExpertise(partner.expertise || "");
    setShowCreateModal(true);
  }

  function openCreateMemberModal(partnerId: string) {
    setEditorKind("member");
    setEditingPartnerId(null);
    setEditingMemberId(null);
    setMemberPartnerId(partnerId);
    setMemberSourceMode("existing_user");
    setMemberUserId(existingUsers[0]?.id ?? "");
    setMemberFullName("");
    setMemberEmail("");
    setMemberRole("");
    setMemberCreateUserIfMissing(true);
    setMemberTemporaryPassword("");
    setShowCreateModal(true);
  }

  function openEditMemberModal(member: Member) {
    setEditorKind("member");
    setEditingPartnerId(null);
    setEditingMemberId(member.id);
    setMemberPartnerId(member.partner_id);
    setMemberRole(member.role);
    setMemberCreateUserIfMissing(true);
    setMemberTemporaryPassword("");
    if (member.user_account_id) {
      setMemberSourceMode("existing_user");
      setMemberUserId(member.user_account_id);
    } else {
      setMemberSourceMode("new_user");
      setMemberUserId("");
    }
    setMemberFullName(member.full_name);
    setMemberEmail(member.email);
    setShowCreateModal(true);
  }

  // ── API handlers ──

  async function handleCreateProject() {
    if (!canCreateProjects) { setError("Insufficient permissions."); return; }
    if (!isProposalMode && !projectStartDate) { setError("Start date required."); return; }
    try {
      setBusy(true); setError("");
      const payload: Parameters<typeof api.createProject>[0] = {
        code: projectCode, title: projectTitle, description: projectDescription || undefined,
        language: projectLanguage,
        coordinator_partner_id: projectCoordinatorPartnerId || undefined,
        principal_investigator_id: projectPrincipalInvestigatorId || undefined,
      };
      if (!isProposalMode) {
        payload.start_date = projectStartDate;
        payload.duration_months = projectDurationMonths;
        payload.reporting_dates = parseReportingDates(projectReportingDatesText);
      }
      const created = await api.createProject(payload);
      onProjectCreated(created);
      setStatus(`Project ${created.code} created.`);
      setActiveSection("consortium");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create project."); } finally { setBusy(false); }
  }

  async function handleUpdateProject() {
    if (!selectedProjectId) return;
    if (!isProposalMode && !projectStartDate) { setError("Start date required."); return; }
    try {
      setBusy(true); setError("");
      const payload: Parameters<typeof api.updateProject>[1] = {
        code: projectCode, title: projectTitle, description: projectDescription || null,
        language: projectLanguage,
        coordinator_partner_id: projectCoordinatorPartnerId || null,
        principal_investigator_id: projectPrincipalInvestigatorId || null,
      };
      if (!isProposalMode) {
        payload.start_date = projectStartDate;
        payload.duration_months = projectDurationMonths;
        payload.reporting_dates = parseReportingDates(projectReportingDatesText);
      }
      const updated = await api.updateProject(selectedProjectId, payload);
      onProjectUpdated(updated);
      setStatus(`Project ${updated.code} saved.`);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to update project."); } finally { setBusy(false); }
  }

  async function handleValidateProject() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const result = await api.validateProject(selectedProjectId, { includeLlm: true });
      setValidationResult(result);
      if (result.valid) setStatus("Validation passed.");
    } catch (err) { setError(err instanceof Error ? err.message : "Validation failed."); } finally { setBusy(false); }
  }

  async function handleActivateProject() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const result = await api.activateProject(selectedProjectId);
      if (selectedProject) {
        onProjectUpdated({ ...selectedProject, status: result.status, baseline_version: result.baseline_version });
      }
      setStatus(`Activated. Baseline v${result.baseline_version}.`);
      const validation = await api.validateProject(selectedProjectId, { includeLlm: true });
      setValidationResult(validation);
    } catch (err) { setError(err instanceof Error ? err.message : "Activation failed."); } finally { setBusy(false); }
  }

  async function refreshDiscoverableUsers() {
    try {
      const response = await api.listUserDiscovery(1, 200, userDiscoverySearch);
      setExistingUsers(response.items);
      if (!memberUserId && response.items.length > 0) setMemberUserId(response.items[0].id);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load users."); }
  }

  async function handleSavePartner() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      if (editingPartnerId) {
        const updated = await api.updatePartner(selectedProjectId, editingPartnerId, { short_name: partnerShortName, legal_name: partnerLegalName, partner_type: partnerType, country: partnerCountry || undefined, expertise: partnerExpertise || undefined });
        setPartners((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
        setStatus(`Partner ${updated.short_name} updated.`);
      } else {
        const created = await api.createPartner(selectedProjectId, { short_name: partnerShortName, legal_name: partnerLegalName, partner_type: partnerType, country: partnerCountry || undefined, expertise: partnerExpertise || undefined });
        setPartners((prev) => [...prev, created]);
        setStatus(`Partner ${created.short_name} added.`);
        if (!memberPartnerId) setMemberPartnerId(created.id);
      }
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save partner."); } finally { setBusy(false); }
  }

  async function handleSaveMember() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const payload = memberSourceMode === "existing_user"
        ? { partner_id: memberPartnerId, user_id: memberUserId, role: memberRole }
        : { partner_id: memberPartnerId, full_name: memberFullName, email: memberEmail, role: memberRole, create_user_if_missing: memberCreateUserIfMissing, temporary_password: memberTemporaryPassword || undefined };
      if (editingMemberId) {
        const updated = await api.updateMember(selectedProjectId, editingMemberId, payload);
        setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
        setStatus(updated.temporary_password ? `Member updated. Password: ${updated.temporary_password}` : `Member ${updated.full_name} updated.`);
      } else {
        const created = await api.createMember(selectedProjectId, payload);
        setMembers((prev) => [...prev, created]);
        setStatus(created.temporary_password ? `Member added. Password: ${created.temporary_password}` : `Member ${created.full_name} added.`);
      }
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save member."); } finally { setBusy(false); }
  }

  async function handleDeleteMember(memberId: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      await api.deleteMember(selectedProjectId, memberId);
      setMembers((prev) => prev.filter((m) => m.id !== memberId));
      setStatus("Member removed.");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete member."); } finally { setBusy(false); }
  }

  async function handleDeletePartner(partnerId: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      await api.deletePartner(selectedProjectId, partnerId);
      setPartners((prev) => prev.filter((p) => p.id !== partnerId));
      setMembers((prev) => prev.filter((m) => m.partner_id !== partnerId));
      setStatus("Partner removed.");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete partner."); } finally { setBusy(false); }
  }

  async function handleCreateWp() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const created = await api.createWorkPackage(selectedProjectId, {
        code: wpCode, title: wpTitle, description: wpDescription || undefined,
        start_month: wpStartMonth, end_month: wpEndMonth,
        execution_status: wpExecutionStatus,
        completed_by_member_id: wpExecutionStatus === "closed" ? wpResponsiblePersonId : null,
        completion_note: wpCompletionNote || undefined,
        assignment: { leader_organization_id: wpLeaderPartnerId, responsible_person_id: wpResponsiblePersonId, collaborating_partner_ids: wpCollaboratingPartnerIds },
      });
      setWorkPackages((prev) => [...prev, created]);
      setActiveWpId(created.id);
      setSelection({ kind: "wp", id: created.id });
      setStatus(`${created.code} created.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create WP."); } finally { setBusy(false); }
  }

  async function handleUpdateWp() {
    if (!selectedProjectId || !editingWpId) return;
    try {
      setBusy(true); setError("");
      const updated = await api.updateWorkPackage(selectedProjectId, editingWpId, {
        code: wpCode, title: wpTitle, description: wpDescription || undefined,
        start_month: wpStartMonth, end_month: wpEndMonth,
        execution_status: wpExecutionStatus,
        completed_by_member_id: wpExecutionStatus === "closed" ? wpResponsiblePersonId : null,
        completion_note: wpCompletionNote || undefined,
        assignment: { leader_organization_id: wpLeaderPartnerId, responsible_person_id: wpResponsiblePersonId, collaborating_partner_ids: wpCollaboratingPartnerIds },
      });
      setWorkPackages((prev) => prev.map((wp) => (wp.id === updated.id ? updated : wp)));
      setActiveWpId(updated.id);
      setStatus(`${updated.code} saved.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to update WP."); } finally { setBusy(false); }
  }

  async function handleCreateTask() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const created = await api.createTask(selectedProjectId, {
        wp_id: taskWpId, code: taskCode, title: taskTitle, description: taskDescription || undefined,
        start_month: taskStartMonth, end_month: taskEndMonth,
        execution_status: taskExecutionStatus,
        completed_by_member_id: taskExecutionStatus === "closed" ? taskResponsiblePersonId : null,
        completion_note: taskCompletionNote || undefined,
        assignment: { leader_organization_id: taskLeaderPartnerId, responsible_person_id: taskResponsiblePersonId, collaborating_partner_ids: taskCollaboratingPartnerIds },
      });
      setTasks((prev) => [...prev, created]);
      setSelection({ kind: "task", id: created.id });
      setStatus(`${created.code} created.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create task."); } finally { setBusy(false); }
  }

  async function handleUpdateTask() {
    if (!selectedProjectId || !editingTaskId) return;
    try {
      setBusy(true); setError("");
      const updated = await api.updateTask(selectedProjectId, editingTaskId, {
        code: taskCode, title: taskTitle, description: taskDescription || undefined,
        start_month: taskStartMonth, end_month: taskEndMonth,
        execution_status: taskExecutionStatus,
        completed_by_member_id: taskExecutionStatus === "closed" ? taskResponsiblePersonId : null,
        completion_note: taskCompletionNote || undefined,
        assignment: { leader_organization_id: taskLeaderPartnerId, responsible_person_id: taskResponsiblePersonId, collaborating_partner_ids: taskCollaboratingPartnerIds },
      });
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      if (updated.wp_id) setActiveWpId(updated.wp_id);
      setStatus(`${updated.code} saved.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to update task."); } finally { setBusy(false); }
  }

  async function handleCreateMilestone() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const created = await api.createMilestone(selectedProjectId, {
        code: milestoneCode, title: milestoneTitle, description: milestoneDescription || undefined,
        due_month: milestoneDueMonth, wp_ids: milestoneWpIds,
        assignment: { leader_organization_id: milestoneLeaderPartnerId, responsible_person_id: milestoneResponsiblePersonId, collaborating_partner_ids: milestoneCollaboratingPartnerIds },
      });
      setMilestones((prev) => [...prev, created]);
      setStatus(`${created.code} created.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create milestone."); } finally { setBusy(false); }
  }

  async function handleCreateDeliverable() {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      const created = await api.createDeliverable(selectedProjectId, {
        wp_ids: deliverableWpIds, code: deliverableCode, title: deliverableTitle,
        description: deliverableDescription || undefined, due_month: deliverableDueMonth,
        assignment: { leader_organization_id: deliverableLeaderPartnerId, responsible_person_id: deliverableResponsiblePersonId, collaborating_partner_ids: deliverableCollaboratingPartnerIds },
      });
      setDeliverables((prev) => [...prev, created]);
      setStatus(`${created.code} created.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create deliverable."); } finally { setBusy(false); }
  }

  async function handleUpdateMilestone() {
    if (!selectedProjectId || !editingMilestoneId) return;
    try {
      setBusy(true); setError("");
      const updated = await api.updateMilestone(selectedProjectId, editingMilestoneId, {
        code: milestoneCode, title: milestoneTitle, description: milestoneDescription || undefined,
        due_month: milestoneDueMonth, wp_ids: milestoneWpIds,
        assignment: { leader_organization_id: milestoneLeaderPartnerId, responsible_person_id: milestoneResponsiblePersonId, collaborating_partner_ids: milestoneCollaboratingPartnerIds },
      });
      setMilestones((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setStatus(`${updated.code} saved.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to update milestone."); } finally { setBusy(false); }
  }

  async function handleUpdateDeliverable() {
    if (!selectedProjectId || !editingDeliverableId) return;
    try {
      setBusy(true); setError("");
      const updated = await api.updateDeliverable(selectedProjectId, editingDeliverableId, {
        wp_ids: deliverableWpIds, code: deliverableCode, title: deliverableTitle,
        description: deliverableDescription || undefined, due_month: deliverableDueMonth,
        assignment: { leader_organization_id: deliverableLeaderPartnerId, responsible_person_id: deliverableResponsiblePersonId, collaborating_partner_ids: deliverableCollaboratingPartnerIds },
      });
      setDeliverables((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setStatus(`${updated.code} saved.`);
      setShowCreateModal(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to update deliverable."); } finally { setBusy(false); }
  }

  async function handleTrashEntity(kind: SelectionKind, entityId: string) {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      if (kind === "wp") await api.trashWorkPackage(selectedProjectId, entityId);
      if (kind === "task") await api.trashTask(selectedProjectId, entityId);
      if (kind === "milestone") await api.trashMilestone(selectedProjectId, entityId);
      if (kind === "deliverable") await api.trashDeliverable(selectedProjectId, entityId);
      await loadProjectContext(selectedProjectId);
      if (selection?.id === entityId) setSelection(null);
      setStatus("Moved to trash.");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to trash item."); } finally { setBusy(false); }
  }

  async function handleRestoreFromTrash(entity: TrashedWorkEntity) {
    if (!selectedProjectId) return;
    try {
      setBusy(true); setError("");
      if (entity.entity_type === "work_package") await api.restoreWorkPackage(selectedProjectId, entity.entity.id);
      if (entity.entity_type === "task") await api.restoreTask(selectedProjectId, entity.entity.id);
      if (entity.entity_type === "milestone") await api.restoreMilestone(selectedProjectId, entity.entity.id);
      if (entity.entity_type === "deliverable") await api.restoreDeliverable(selectedProjectId, entity.entity.id);
      await loadProjectContext(selectedProjectId);
      setStatus("Restored.");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to restore."); } finally { setBusy(false); }
  }

  // ── Section renderers ──

  function renderProjectSection() {
    const formReady = isProposalMode
      ? !busy && !!projectCode && !!projectTitle
      : !busy && !!projectCode && !!projectTitle && !!projectStartDate && projectDurationMonths >= 1;

    return (
      <div className="setup-section-content">
        <div className="card">
          <div className="call-details-section-head">Basics</div>
          <div className="form-grid">
            <label>
              Code
              <input value={projectCode} onChange={(e) => setProjectCode(e.target.value)} placeholder="ACRONYM" />
            </label>
            <label>
              Title
              <input value={projectTitle} onChange={(e) => setProjectTitle(e.target.value)} placeholder="Full project title" />
            </label>
            <label className="wide">
              Description
              <textarea value={projectDescription} onChange={(e) => setProjectDescription(e.target.value)} />
            </label>
            <label>
              Language
              <select value={projectLanguage} onChange={(e) => setProjectLanguage(e.target.value)}>
                <option value="en_GB">English (UK)</option>
                <option value="en_US">English (US)</option>
                <option value="it">Italian</option>
                <option value="fr">French</option>
                <option value="de">German</option>
                <option value="es">Spanish</option>
                <option value="pt">Portuguese</option>
              </select>
            </label>
          </div>
          {!isProposalMode ? (
            <>
              <div className="call-details-section-head">Timeline</div>
              <div className="form-grid">
                <label>
                  Start date
                  <input type="date" value={projectStartDate} onChange={(e) => setProjectStartDate(e.target.value)} />
                </label>
                <label>
                  Duration (months)
                  <input type="number" min={1} max={120} value={projectDurationMonths} onChange={(e) => setProjectDurationMonths(Number(e.target.value))} />
                </label>
                <label className="wide">
                  Reporting dates
                  <input value={projectReportingDatesText} onChange={(e) => setProjectReportingDatesText(e.target.value)} placeholder="2026-12-31, 2027-12-31" />
                </label>
              </div>
            </>
          ) : null}
          {selectedProjectId && partners.length > 0 ? (
            <>
              <div className="call-details-section-head">Governance</div>
              <div className="form-grid">
                <label>
                  Coordinator Partner
                  <select value={projectCoordinatorPartnerId} onChange={(e) => { setProjectCoordinatorPartnerId(e.target.value); setProjectPrincipalInvestigatorId(""); }}>
                    <option value="">None</option>
                    {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
                  </select>
                </label>
                <label>
                  Principal Investigator
                  <select value={projectPrincipalInvestigatorId} onChange={(e) => setProjectPrincipalInvestigatorId(e.target.value)} disabled={!projectCoordinatorPartnerId}>
                    <option value="">None</option>
                    {coordinatorMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                  </select>
                </label>
              </div>
            </>
          ) : null}
          <div className="row-actions">
            {selectedProjectId ? (
              <>
                <button type="button" disabled={!formReady} onClick={handleUpdateProject}>Save Changes</button>
                <button type="button" className="ghost" onClick={() => setActiveSection("consortium")} disabled={!formReady}>
                  Next <FontAwesomeIcon icon={faChevronRight} />
                </button>
              </>
            ) : canCreateProjects ? (
              <button type="button" disabled={!formReady} onClick={handleCreateProject}>
                Create Project
              </button>
            ) : null}
          </div>
        </div>

      </div>
    );
  }

  function renderConsortiumSection() {
    return (
      <div className="setup-section-content">
        <div className="setup-consortium-toolbar">
          <div className="timeline-stats">
            <span>{partners.length} partners</span>
            <span className="timeline-stat-sep" />
            <span>{members.length} members</span>
          </div>
          <div className="action-group">
            <button type="button" onClick={openCreatePartnerModal} disabled={!selectedProjectId || busy}>
              <FontAwesomeIcon icon={faPlus} /> Partner
            </button>
          </div>
        </div>

        {partners.length === 0 ? (
          <div className="card-slab">No partners yet. Add your first partner to get started.</div>
        ) : null}

        {partners.map((partner) => {
          const partnerMembers = membersByPartner[partner.id] || [];
          return (
            <div key={partner.id} className="card setup-partner-card">
              <div className="setup-partner-head">
                <div className="setup-partner-info">
                  <strong>{partner.short_name}</strong>
                  <span>{partner.legal_name}</span>
                </div>
                <div className="action-group">
                  <button type="button" className="ghost icon-only" title="Edit partner" onClick={() => openEditPartnerModal(partner)}>
                    <FontAwesomeIcon icon={faPen} />
                  </button>
                  <button type="button" className="ghost icon-only" title="Add member" onClick={() => openCreateMemberModal(partner.id)}>
                    <FontAwesomeIcon icon={faUserPlus} />
                  </button>
                  <button type="button" className="ghost icon-only" title="Delete partner" onClick={() => void handleDeletePartner(partner.id)} disabled={busy}>
                    <FontAwesomeIcon icon={faTrash} />
                  </button>
                </div>
              </div>
              {partnerMembers.length > 0 ? (
                <div className="setup-member-list">
                  {partnerMembers.map((member) => (
                    <div key={member.id} className="setup-member-row" onDoubleClick={() => openEditMemberModal(member)}>
                      <span className="setup-member-name">{member.full_name}</span>
                      <span className="setup-member-email">{member.email}</span>
                      <span className="setup-member-role">{member.role || "-"}</span>
                      <button type="button" className="ghost icon-only" title="Edit member" onClick={() => openEditMemberModal(member)}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                      <button type="button" className="ghost icon-only" title="Remove member" onClick={() => void handleDeleteMember(member.id)} disabled={busy}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted-small">No members yet</p>
              )}
            </div>
          );
        })}

        {partners.length > 0 ? (
          <div className="row-actions">
            <button type="button" className="ghost" onClick={() => setActiveSection("workplan")}>
              Next: Workplan <FontAwesomeIcon icon={faChevronRight} />
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  function renderPartnerEditor() {
    const isEditing = Boolean(editingPartnerId);
    return (
      <div className="form-grid">
        <label>
          Short Name
          <input value={partnerShortName} onChange={(e) => setPartnerShortName(e.target.value)} placeholder="ACME" />
        </label>
        <label>
          Legal Name
          <input value={partnerLegalName} onChange={(e) => setPartnerLegalName(e.target.value)} placeholder="ACME Corp Ltd." />
        </label>
        <label>
          Partner Type
          <select value={partnerType} onChange={(e) => setPartnerType(e.target.value)}>
            <option value="beneficiary">Beneficiary</option>
            <option value="coordinator">Coordinator</option>
            <option value="affiliated_entity">Affiliated Entity</option>
            <option value="associated_partner">Associated Partner</option>
          </select>
        </label>
        <label>
          Country
          <input value={partnerCountry} onChange={(e) => setPartnerCountry(e.target.value.toUpperCase().slice(0, 2))} placeholder="IT" maxLength={2} />
        </label>
        <label className="wide">
          Expertise
          <textarea rows={3} value={partnerExpertise} onChange={(e) => setPartnerExpertise(e.target.value)} placeholder="Key expertise, capabilities, and relevant experience..." />
        </label>
        <div className="wide row-actions">
          <button type="button" disabled={busy || !selectedProjectId || !partnerShortName || !partnerLegalName} onClick={handleSavePartner}>
            {isEditing ? "Save" : "Create"}
          </button>
        </div>
      </div>
    );
  }

  function renderMemberEditor() {
    const isEditing = Boolean(editingMemberId);
    const selectedExistingUser = memberUserId ? existingUserById[memberUserId] : null;
    return (
      <div className="form-grid">
        <label>
          Partner
          <select value={memberPartnerId} onChange={(e) => setMemberPartnerId(e.target.value)}>
            <option value="">Select partner</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <label>
          Source
          <select value={memberSourceMode} onChange={(e) => setMemberSourceMode(e.target.value as MemberSourceMode)}>
            <option value="existing_user">Existing User</option>
            <option value="new_user">Manual Entry</option>
          </select>
        </label>
        {memberSourceMode === "existing_user" ? (
          <>
            <label className="wide">
              Search & Select User
              <div className="inline-form two-cols">
                <input value={userDiscoverySearch} onChange={(e) => setUserDiscoverySearch(e.target.value)} placeholder="Name or email" />
                <button type="button" className="ghost" onClick={() => void refreshDiscoverableUsers()} disabled={busy}>Search</button>
              </div>
            </label>
            <label className="wide">
              User
              <select value={memberUserId} onChange={(e) => setMemberUserId(e.target.value)}>
                <option value="">Select user</option>
                {existingUsers.map((u) => <option key={u.id} value={u.id}>{u.display_name} · {u.email}</option>)}
              </select>
            </label>
            <label>Name<input value={selectedExistingUser?.display_name ?? memberFullName} readOnly /></label>
            <label>Email<input value={selectedExistingUser?.email ?? memberEmail} readOnly /></label>
          </>
        ) : (
          <>
            <label>Full Name<input value={memberFullName} onChange={(e) => setMemberFullName(e.target.value)} /></label>
            <label>Email<input type="email" value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} /></label>
            <label className="wide checkbox-label">
              <input type="checkbox" checked={memberCreateUserIfMissing} onChange={(e) => setMemberCreateUserIfMissing(e.target.checked)} />
              <span>Create user account if missing</span>
            </label>
            {memberCreateUserIfMissing ? (
              <label className="wide">Temporary Password<input value={memberTemporaryPassword} onChange={(e) => setMemberTemporaryPassword(e.target.value)} /></label>
            ) : null}
          </>
        )}
        <label>Role<input value={memberRole} onChange={(e) => setMemberRole(e.target.value)} placeholder="e.g. researcher" /></label>
        <div className="wide row-actions">
          <button type="button" disabled={busy || !selectedProjectId || !memberPartnerId || !memberRole || (memberSourceMode === "existing_user" ? !memberUserId : !memberFullName || !memberEmail)} onClick={handleSaveMember}>
            {isEditing ? "Save" : "Create"}
          </button>
        </div>
      </div>
    );
  }

  function renderWpEditor() {
    const isEditing = Boolean(editingWpId);
    const wpClosing = wpExecutionStatus === "closed";
    return (
      <div className="form-grid">
        <label>Code<input value={wpCode} onChange={(e) => setWpCode(e.target.value)} placeholder="WP1" /></label>
        <label>Title<input value={wpTitle} onChange={(e) => setWpTitle(e.target.value)} /></label>
        <label>Start Month<input type="number" min={1} value={wpStartMonth} onChange={(e) => setWpStartMonth(Number(e.target.value))} /></label>
        <label>End Month<input type="number" min={1} value={wpEndMonth} onChange={(e) => setWpEndMonth(Number(e.target.value))} /></label>
        <label>Leader Partner
          <select value={wpLeaderPartnerId} onChange={(e) => setWpLeaderPartnerId(e.target.value)}>
            <option value="">Select</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <label>Responsible Person
          <select value={wpResponsiblePersonId} onChange={(e) => setWpResponsiblePersonId(e.target.value)}>
            <option value="">Select</option>
            {wpMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
        </label>
        {!isProposalMode ? (
          <label>Status
            <select value={wpExecutionStatus} onChange={(e) => setWpExecutionStatus(e.target.value)}>
              {WORK_EXECUTION_STATUS_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
        ) : null}
        <label className="wide">Description<textarea value={wpDescription} onChange={(e) => setWpDescription(e.target.value)} /></label>
        {!isProposalMode && (wpExecutionStatus === "ready_for_closure" || wpClosing) ? (
          <label className="wide">Completion Note<textarea value={wpCompletionNote} onChange={(e) => setWpCompletionNote(e.target.value)} /></label>
        ) : null}
        <label className="wide">Collaborating Partners
          <select multiple value={wpCollaboratingPartnerIds} onChange={(e) => setWpCollaboratingPartnerIds(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <div className="wide row-actions">
          <button type="button" disabled={busy || !selectedProjectId || !wpCode || !wpTitle || wpStartMonth < 1 || wpEndMonth < wpStartMonth || !wpLeaderPartnerId || !wpResponsiblePersonId || (wpClosing && !wpCompletionNote.trim())} onClick={isEditing ? handleUpdateWp : handleCreateWp}>
            {isEditing ? "Save" : "Create"}
          </button>
          {isEditing ? <button type="button" className="ghost" onClick={() => openCreateModal("wp")}>New Instead</button> : null}
        </div>
      </div>
    );
  }

  function renderTaskEditor() {
    const isEditing = Boolean(editingTaskId);
    const lockedWp = lockedTaskWpId ? wpById[lockedTaskWpId] : null;
    const taskClosing = taskExecutionStatus === "closed";
    return (
      <div className="form-grid">
        {lockedWp ? (
          <label>WP<input value={`${lockedWp.code} · ${lockedWp.title}`} readOnly /></label>
        ) : (
          <label>WP
            <select value={taskWpId} onChange={(e) => setTaskWpId(e.target.value)}>
              <option value="">Select WP</option>
              {workPackages.map((wp) => <option key={wp.id} value={wp.id}>{wp.code} · {wp.title}</option>)}
            </select>
          </label>
        )}
        <label>Code<input value={taskCode} onChange={(e) => setTaskCode(e.target.value)} placeholder="T1.1" /></label>
        <label>Title<input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} /></label>
        <label>Start Month<input type="number" min={1} value={taskStartMonth} onChange={(e) => setTaskStartMonth(Number(e.target.value))} /></label>
        <label>End Month<input type="number" min={1} value={taskEndMonth} onChange={(e) => setTaskEndMonth(Number(e.target.value))} /></label>
        <label>Leader Partner
          <select value={taskLeaderPartnerId} onChange={(e) => setTaskLeaderPartnerId(e.target.value)}>
            <option value="">Select</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <label>Responsible Person
          <select value={taskResponsiblePersonId} onChange={(e) => setTaskResponsiblePersonId(e.target.value)}>
            <option value="">Select</option>
            {taskMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
        </label>
        {!isProposalMode ? (
          <label>Status
            <select value={taskExecutionStatus} onChange={(e) => setTaskExecutionStatus(e.target.value)}>
              {WORK_EXECUTION_STATUS_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
        ) : null}
        <label className="wide">Description<textarea value={taskDescription} onChange={(e) => setTaskDescription(e.target.value)} /></label>
        {!isProposalMode && (taskExecutionStatus === "ready_for_closure" || taskClosing) ? (
          <label className="wide">Completion Note<textarea value={taskCompletionNote} onChange={(e) => setTaskCompletionNote(e.target.value)} /></label>
        ) : null}
        <label className="wide">Collaborating Partners
          <select multiple value={taskCollaboratingPartnerIds} onChange={(e) => setTaskCollaboratingPartnerIds(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <div className="wide row-actions">
          <button type="button" disabled={busy || !selectedProjectId || !taskWpId || !taskCode || !taskTitle || taskStartMonth < 1 || taskEndMonth < taskStartMonth || !taskLeaderPartnerId || !taskResponsiblePersonId || (taskClosing && !taskCompletionNote.trim())} onClick={isEditing ? handleUpdateTask : handleCreateTask}>
            {isEditing ? "Save" : "Create"}
          </button>
          {isEditing ? <button type="button" className="ghost" onClick={() => openCreateTaskForWp(taskWpId)}>New Instead</button> : null}
        </div>
      </div>
    );
  }

  function renderMilestoneEditor() {
    const isEditing = Boolean(editingMilestoneId);
    return (
      <div className="form-grid">
        <label>Code<input value={milestoneCode} onChange={(e) => setMilestoneCode(e.target.value)} placeholder="MS1" /></label>
        <label>Title<input value={milestoneTitle} onChange={(e) => setMilestoneTitle(e.target.value)} /></label>
        <label>Due Month<input type="number" min={1} value={milestoneDueMonth} onChange={(e) => setMilestoneDueMonth(Number(e.target.value))} /></label>
        <label className="wide">Work Packages
          <select multiple value={milestoneWpIds} onChange={(e) => setMilestoneWpIds(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {workPackages.map((wp) => <option key={wp.id} value={wp.id}>{wp.code} · {wp.title}</option>)}
          </select>
        </label>
        <label>Leader Partner
          <select value={milestoneLeaderPartnerId} onChange={(e) => setMilestoneLeaderPartnerId(e.target.value)}>
            <option value="">Select</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <label>Responsible Person
          <select value={milestoneResponsiblePersonId} onChange={(e) => setMilestoneResponsiblePersonId(e.target.value)}>
            <option value="">Select</option>
            {milestoneMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
        </label>
        <label className="wide">Description<textarea value={milestoneDescription} onChange={(e) => setMilestoneDescription(e.target.value)} /></label>
        <label className="wide">Collaborating Partners
          <select multiple value={milestoneCollaboratingPartnerIds} onChange={(e) => setMilestoneCollaboratingPartnerIds(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <div className="wide row-actions">
          <button type="button" disabled={busy || !selectedProjectId || !milestoneCode || !milestoneTitle || milestoneDueMonth < 1 || !milestoneLeaderPartnerId || !milestoneResponsiblePersonId} onClick={isEditing ? handleUpdateMilestone : handleCreateMilestone}>
            {isEditing ? "Save" : "Create"}
          </button>
        </div>
      </div>
    );
  }

  function renderDeliverableEditor() {
    const isEditing = Boolean(editingDeliverableId);
    return (
      <div className="form-grid">
        <label className="wide">Work Packages
          <select multiple value={deliverableWpIds} onChange={(e) => setDeliverableWpIds(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {workPackages.map((wp) => <option key={wp.id} value={wp.id}>{wp.code} · {wp.title}</option>)}
          </select>
        </label>
        <label>Code<input value={deliverableCode} onChange={(e) => setDeliverableCode(e.target.value)} placeholder="D1.1" /></label>
        <label>Title<input value={deliverableTitle} onChange={(e) => setDeliverableTitle(e.target.value)} /></label>
        <label>Due Month<input type="number" min={1} value={deliverableDueMonth} onChange={(e) => setDeliverableDueMonth(Number(e.target.value))} /></label>
        <label>Leader Partner
          <select value={deliverableLeaderPartnerId} onChange={(e) => setDeliverableLeaderPartnerId(e.target.value)}>
            <option value="">Select</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <label>Responsible Person
          <select value={deliverableResponsiblePersonId} onChange={(e) => setDeliverableResponsiblePersonId(e.target.value)}>
            <option value="">Select</option>
            {deliverableMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
        </label>
        <label className="wide">Description<textarea value={deliverableDescription} onChange={(e) => setDeliverableDescription(e.target.value)} /></label>
        <label className="wide">Collaborating Partners
          <select multiple value={deliverableCollaboratingPartnerIds} onChange={(e) => setDeliverableCollaboratingPartnerIds(Array.from(e.target.selectedOptions).map((o) => o.value))}>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
          </select>
        </label>
        <div className="wide row-actions">
          <button type="button" disabled={busy || !selectedProjectId || deliverableWpIds.length === 0 || !deliverableCode || !deliverableTitle || deliverableDueMonth < 1 || !deliverableLeaderPartnerId || !deliverableResponsiblePersonId} onClick={isEditing ? handleUpdateDeliverable : handleCreateDeliverable}>
            {isEditing ? "Save" : "Create"}
          </button>
        </div>
      </div>
    );
  }

  function renderWorkplanSection() {
    return (
      <div className="setup-section-content">
        <div className="setup-workplan-toolbar">
          <div className="tab-strip">
            <button type="button" className={workplanTab === "wps" ? "active" : ""} onClick={() => setWorkplanTab("wps")}>
              WPs & Tasks <span className="setup-tab-count">{workPackages.length}/{tasks.length}</span>
            </button>
            <button type="button" className={workplanTab === "deliverables" ? "active" : ""} onClick={() => setWorkplanTab("deliverables")}>
              Deliverables <span className="setup-tab-count">{deliverables.length}</span>
            </button>
            <button type="button" className={workplanTab === "milestones" ? "active" : ""} onClick={() => setWorkplanTab("milestones")}>
              Milestones <span className="setup-tab-count">{milestones.length}</span>
            </button>
            {trashedEntities.length > 0 ? (
              <button type="button" className={workplanTab === "trash" ? "active" : ""} onClick={() => setWorkplanTab("trash")}>
                Trash <span className="setup-tab-count">{trashedEntities.length}</span>
              </button>
            ) : null}
          </div>
        </div>

        {workplanTab === "wps" ? renderWpsTab() : null}
        {workplanTab === "deliverables" ? renderDeliverablesTab() : null}
        {workplanTab === "milestones" ? renderMilestonesTab() : null}
        {workplanTab === "trash" ? renderTrashTab() : null}

        {workPackages.length > 0 ? (
          <div className="row-actions">
            <button type="button" className="ghost" onClick={() => setActiveSection("review")}>
              Next: Review <FontAwesomeIcon icon={faChevronRight} />
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  function renderWpsTab() {
    return (
      <div className="card">
        <div className="workpane-head">
          <h3>Work Packages & Tasks</h3>
          <button type="button" onClick={() => openCreateModal("wp")} disabled={!selectedProjectId}>
            <FontAwesomeIcon icon={faPlus} /> WP
          </button>
        </div>
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th className="col-50">Type</th>
                <th className="col-80">Code</th>
                <th>Title</th>
                <th className="col-90">Window</th>
                {!isProposalMode ? <th className="col-130">Status</th> : null}
                <th className="col-70">Actions</th>
              </tr>
            </thead>
            <tbody>
              {workPackages.map((wp) => (
                <Fragment key={wp.id}>
                  <tr
                    className={wp.id === activeWpId ? "active-row" : ""}
                    onClick={() => { setActiveWpId(wp.id); setSelection({ kind: "wp", id: wp.id }); }}
                    onDoubleClick={() => openEditWpModal(wp)}
                  >
                    <td><span className="chip">WP</span></td>
                    <td><strong>{wp.code}</strong></td>
                    <td>{wp.title}</td>
                    <td>{monthWindowLabel(wp.start_month, wp.end_month)}</td>
                    {!isProposalMode ? (
                      <td>
                        {(() => { const s = EXEC_STATUS_ICON[(wp.execution_status || "planned") as keyof typeof EXEC_STATUS_ICON] || EXEC_STATUS_ICON.planned; return <span className={`exec-status-icon ${s.cls}`} title={s.label}><FontAwesomeIcon icon={s.icon} /></span>; })()}
                      </td>
                    ) : null}
                    <td>
                      <div className="action-group">
                        <button type="button" className="ghost icon-only" title="Edit" onClick={(e) => { e.stopPropagation(); openEditWpModal(wp); }}>
                          <FontAwesomeIcon icon={faPen} />
                        </button>
                        <button type="button" className="ghost icon-only" title="Add task" onClick={(e) => { e.stopPropagation(); setActiveWpId(wp.id); openCreateTaskForWp(wp.id); }}>
                          <FontAwesomeIcon icon={faPlus} />
                        </button>
                        <button type="button" className="ghost icon-only" title="Trash" onClick={(e) => { e.stopPropagation(); void handleTrashEntity("wp", wp.id); }}>
                          <FontAwesomeIcon icon={faTrash} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {(tasksByWp[wp.id] || []).map((task) => (
                    <tr
                      key={task.id}
                      className={`task-sub-row ${selection?.kind === "task" && selection.id === task.id ? "active-row" : ""}`}
                      onClick={() => { setActiveWpId(wp.id); setSelection({ kind: "task", id: task.id }); }}
                      onDoubleClick={() => openEditTaskModal(task)}
                    >
                      <td><span className="chip muted">Task</span></td>
                      <td>{task.code}</td>
                      <td><span className="task-indent">{task.title}</span></td>
                      <td>{monthWindowLabel(task.start_month, task.end_month)}</td>
                      {!isProposalMode ? (
                        <td>
                          {(() => { const s = EXEC_STATUS_ICON[(task.execution_status || "planned") as keyof typeof EXEC_STATUS_ICON] || EXEC_STATUS_ICON.planned; return <span className={`exec-status-icon ${s.cls}`} title={s.label}><FontAwesomeIcon icon={s.icon} /></span>; })()}
                        </td>
                      ) : null}
                      <td>
                        <div className="action-group">
                          <button type="button" className="ghost icon-only" title="Edit" onClick={(e) => { e.stopPropagation(); openEditTaskModal(task); }}>
                            <FontAwesomeIcon icon={faPen} />
                          </button>
                          <button type="button" className="ghost icon-only" title="Trash" onClick={(e) => { e.stopPropagation(); void handleTrashEntity("task", task.id); }}>
                            <FontAwesomeIcon icon={faTrash} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
              {workPackages.length === 0 ? <tr><td colSpan={6} className="muted-small">No work packages yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  function renderDeliverablesTab() {
    return (
      <div className="card">
        <div className="workpane-head">
          <h3>Deliverables</h3>
          <button type="button" onClick={() => openCreateModal("deliverable")} disabled={!selectedProjectId}>
            <FontAwesomeIcon icon={faPlus} /> Deliverable
          </button>
        </div>
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th className="col-80">Code</th>
                <th>Title</th>
                <th>WPs</th>
                <th className="col-70">Due</th>
                <th className="col-50">Actions</th>
              </tr>
            </thead>
            <tbody>
              {deliverables.map((row) => (
                <tr
                  key={row.id}
                  className={selection?.kind === "deliverable" && selection.id === row.id ? "active-row" : ""}
                  onClick={() => setSelection({ kind: "deliverable", id: row.id })}
                  onDoubleClick={() => openEditDeliverableModal(row)}
                >
                  <td><strong>{row.code}</strong></td>
                  <td>{row.title}</td>
                  <td>{row.wp_ids.length > 0 ? row.wp_ids.map((id) => wpById[id]?.code).filter(Boolean).join(", ") : "-"}</td>
                  <td>{dueMonthLabel(row.due_month)}</td>
                  <td>
                    <div className="action-group">
                      <button type="button" className="ghost icon-only" title="Edit" onClick={(e) => { e.stopPropagation(); openEditDeliverableModal(row); }}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                      <button type="button" className="ghost icon-only" title="Trash" onClick={(e) => { e.stopPropagation(); void handleTrashEntity("deliverable", row.id); }}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {deliverables.length === 0 ? <tr><td colSpan={5} className="muted-small">No deliverables yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  function renderMilestonesTab() {
    return (
      <div className="card">
        <div className="workpane-head">
          <h3>Milestones</h3>
          <button type="button" onClick={() => openCreateModal("milestone")} disabled={!selectedProjectId}>
            <FontAwesomeIcon icon={faPlus} /> Milestone
          </button>
        </div>
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th className="col-80">Code</th>
                <th>Title</th>
                <th>WPs</th>
                <th className="col-70">Due</th>
                <th className="col-50">Actions</th>
              </tr>
            </thead>
            <tbody>
              {milestones.map((row) => (
                <tr
                  key={row.id}
                  className={selection?.kind === "milestone" && selection.id === row.id ? "active-row" : ""}
                  onClick={() => setSelection({ kind: "milestone", id: row.id })}
                  onDoubleClick={() => openEditMilestoneModal(row)}
                >
                  <td><strong>{row.code}</strong></td>
                  <td>{row.title}</td>
                  <td>{row.wp_ids.length > 0 ? row.wp_ids.map((id) => wpById[id]?.code).filter(Boolean).join(", ") : "-"}</td>
                  <td>{dueMonthLabel(row.due_month)}</td>
                  <td>
                    <div className="action-group">
                      <button type="button" className="ghost icon-only" title="Edit" onClick={(e) => { e.stopPropagation(); openEditMilestoneModal(row); }}>
                        <FontAwesomeIcon icon={faPen} />
                      </button>
                      <button type="button" className="ghost icon-only" title="Trash" onClick={(e) => { e.stopPropagation(); void handleTrashEntity("milestone", row.id); }}>
                        <FontAwesomeIcon icon={faTrash} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {milestones.length === 0 ? <tr><td colSpan={5} className="muted-small">No milestones yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  function renderTrashTab() {
    return (
      <div className="card">
        <div className="workpane-head">
          <h3>Trash</h3>
        </div>
        <div className="simple-table-wrap">
          <table className="simple-table compact-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Code</th>
                <th>Title</th>
                <th>Trashed</th>
                <th className="col-50">Restore</th>
              </tr>
            </thead>
            <tbody>
              {trashedEntities.map((row) => (
                <tr key={`${row.entity_type}-${row.entity.id}`}>
                  <td>{row.entity_type.replace("_", " ")}</td>
                  <td>{row.entity.code}</td>
                  <td>{row.entity.title}</td>
                  <td>{row.entity.trashed_at ? new Date(row.entity.trashed_at).toLocaleDateString() : "-"}</td>
                  <td>
                    <button type="button" className="ghost icon-only" title="Restore" onClick={() => void handleRestoreFromTrash(row)}>
                      <FontAwesomeIcon icon={faRotateLeft} />
                    </button>
                  </td>
                </tr>
              ))}
              {trashedEntities.length === 0 ? <tr><td colSpan={5} className="muted-small">Empty.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  function renderReviewSection() {
    return (
      <div className="setup-section-content">
        <div className="setup-review-header">
          <div className="setup-progress-ring">
            <svg viewBox="0 0 36 36" className="setup-progress-svg">
              <path className="setup-progress-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <path className="setup-progress-fill" strokeDasharray={`${progressPercent}, 100`} d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            </svg>
            <span className="setup-progress-text">{progressPercent}%</span>
          </div>
          <div className="setup-review-meta">
            <strong>{completedChecks} of {checks.length} complete</strong>
            <span>{completedChecks === checks.length
              ? (isProposalMode ? "Structure complete" : "Ready to activate")
              : (isProposalMode ? "Complete all items" : "Complete all items to activate")}</span>
          </div>
        </div>

        <div className="card">
          <h3>Checklist</h3>
          <div className="setup-checklist">
            {checks.map((check) => (
              <button
                key={check.label}
                type="button"
                className={`setup-check-item ${check.done ? "done" : "pending"}`}
                onClick={() => { if (!check.done) setActiveSection(check.section); }}
                title={check.done ? undefined : `Go to ${check.section}`}
              >
                <span className="setup-check-icon">
                  <FontAwesomeIcon icon={check.done ? faCheck : faCircleExclamation} />
                </span>
                <span>{check.label}</span>
              </button>
            ))}
          </div>
          <div className="row-actions">
            <button type="button" className="ghost" disabled={!selectedProjectId || busy} onClick={() => void handleValidateProject()}>
              Validate
            </button>
            {!isProposalMode ? (
              <button type="button" disabled={!selectedProjectId || busy || completedChecks < checks.length} onClick={() => void handleActivateProject()}>
                Activate Project
              </button>
            ) : null}
          </div>
        </div>

        <div className="card">
          <h3>Validation</h3>
          {validationResult ? (
            validationResult.errors.length > 0 || validationResult.warnings.length > 0 ? (
              <div className="settings-validation-list">
                {validationResult.errors.map((item) => (
                  <div key={`${item.entity_type}-${item.entity_id}-${item.code}`} className="settings-validation-item error">
                    <strong>{item.code}</strong>
                    <span>{item.message}</span>
                  </div>
                ))}
                {validationResult.warnings.map((item) => (
                  <div key={`${item.entity_type}-${item.entity_id}-${item.code}`} className="settings-validation-item warning">
                    <strong>{item.code}</strong>
                    <span>{item.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="settings-validation-item ok">
                <strong>All Clear</strong>
                <span>No validation issues found.</span>
              </div>
            )
          ) : (
            <p className="muted-small">Run validation to check for issues.</p>
          )}
        </div>
      </div>
    );
  }

  // ── Main render ──

  const modalTitle = editorKind === "partner"
    ? (editingPartnerId ? "Edit Partner" : "New Partner")
    : editorKind === "member"
      ? (editingMemberId ? "Edit Member" : "New Member")
      : editorKind === "wp"
        ? (editingWpId ? "Edit Work Package" : "New Work Package")
        : editorKind === "task"
          ? (editingTaskId ? "Edit Task" : "New Task")
          : editorKind === "milestone"
            ? (editingMilestoneId ? "Edit Milestone" : "New Milestone")
            : (editingDeliverableId ? "Edit Deliverable" : "New Deliverable");

  return (
    <section className="panel onboarding-panel">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      {selectedProject ? (
        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <span><strong>{selectedProject.code}</strong></span>
            {selectedProject.start_date ? (<><span className="setup-summary-sep" /><span>{selectedProject.start_date}</span></>) : null}
            {selectedProject.duration_months ? (<><span className="setup-summary-sep" /><span>{selectedProject.duration_months} months</span></>) : null}
            <span className="setup-summary-sep" />
            <span>{partners.length} partners</span>
            <span className="setup-summary-sep" />
            <span>{members.length} members</span>
          </div>
          <div className="setup-summary-progress">
            <div className="setup-summary-progress-track">
              <div className="setup-summary-progress-fill" style={{ width: `${progressPercent}%` }} />
            </div>
            <span>{progressPercent}%</span>
          </div>
        </div>
      ) : null}

      <div className="setup-layout">
        <aside className="setup-sections">
          {sectionItems.map((item, index) => (
            <button
              key={item.id}
              type="button"
              className={`setup-section-btn ${activeSection === item.id ? "active" : ""}`}
              onClick={() => setActiveSection(item.id)}
            >
              <div className="setup-section-btn-inner">
                <span className={`setup-step-number ${item.done ? "done" : ""}`}>
                  {item.done ? <FontAwesomeIcon icon={faCheck} /> : index + 1}
                </span>
                <strong>{item.title}</strong>
              </div>
              <span className="setup-section-count">{item.count}</span>
            </button>
          ))}
        </aside>

        <div className="setup-content">
          {!selectedProjectId && activeSection !== "project" ? (
            <div className="card-slab">Select or create a project first.</div>
          ) : null}
          {activeSection === "project" ? renderProjectSection() : null}
          {activeSection === "consortium" ? renderConsortiumSection() : null}
          {activeSection === "workplan" ? renderWorkplanSection() : null}
          {activeSection === "review" ? renderReviewSection() : null}
        </div>
      </div>

      {showCreateModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy) { e.preventDefault(); } }}>
            <div className="modal-head">
              <h3>{modalTitle}</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setShowCreateModal(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="modal-body">
              {editorKind === "partner" ? renderPartnerEditor() : null}
              {editorKind === "member" ? renderMemberEditor() : null}
              {editorKind === "wp" ? renderWpEditor() : null}
              {editorKind === "task" ? renderTaskEditor() : null}
              {editorKind === "milestone" ? renderMilestoneEditor() : null}
              {editorKind === "deliverable" ? renderDeliverableEditor() : null}
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}
    </section>
  );
}
