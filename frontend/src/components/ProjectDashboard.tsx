import { useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBan,
  faBookOpen,
  faCalendarDay,
  faCheck,
  faCheckCircle,
  faCheckDouble,
  faDownload,
  faEllipsis,
  faExclamationTriangle,
  faFileLines,
  faFlagCheckered,
  faFolderOpen,
  faHourglass,
  faLayerGroup,
  faPeopleGroup,
  faPlay,
  faShieldHalved,
  faSpinner,
  faWaveSquare,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { currentProjectMonth } from "../lib/utils";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type {
  DashboardHealth,
  DashboardHealthIssue,
  DashboardHealthSnapshot,
  DashboardRecurringIssue,
  DashboardScopeOptions,
  DocumentListItem,
  Member,
  Partner,
  Project,
  ProjectInboxItem,
  ProjectProposalSection,
  ProjectRisk,
  ProjectValidationResult,
  WorkEntity,
} from "../types";
import { MarkAsFundedModal } from "./MarkAsFundedModal";
import { ProjectActivityFeed } from "./ProjectActivityFeed";

type Props = {
  selectedProjectId: string;
  project: Project | null;
  onNavigate: (view: "delivery" | "documents" | "wizard" | "matrix" | "proposal") => void;
  onProjectUpdated?: (project: Project) => void;
};

type DeadlineRow = {
  id: string;
  code: string;
  title: string;
  kind: "deliverable" | "milestone";
  dueMonth: number;
  dueDateLabel: string;
  owner: string;
};

function addMonths(dateInput: string, monthsToAdd: number): Date | null {
  const base = new Date(dateInput);
  if (Number.isNaN(base.getTime())) return null;
  const next = new Date(base);
  next.setMonth(next.getMonth() + monthsToAdd);
  return next;
}

function formatDateLabel(date: Date | null): string {
  if (!date) return "-";
  return date.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" });
}

function monthCode(value: number): string {
  return `M${value}`;
}

function healthActionForIssue(issue: DashboardHealthIssue): {
  label: string;
  view: "delivery" | "documents" | "wizard" | "matrix";
} | null {
  if (issue.primary_action?.type === "navigate" && issue.primary_action.view) {
    return { label: issue.primary_action.label, view: issue.primary_action.view as "delivery" | "documents" | "wizard" | "matrix" };
  }
  const category = (issue.category || "").toLowerCase();
  const entityType = (issue.entity_type || "").toLowerCase();
  if (category.includes("deliverable") || category.includes("milestone") || category.includes("reporting") || entityType === "deliverable" || entityType === "milestone") {
    return { label: "Open Delivery", view: "delivery" };
  }
  if (category.includes("document")) {
    return { label: "Open Documents", view: "documents" };
  }
  if (entityType === "partner" || entityType === "member") {
    return { label: "Open Matrix", view: "matrix" };
  }
  return { label: "Open Workplan", view: "wizard" };
}

function healthGroupForIssue(issue: DashboardHealthIssue): string {
  const category = issue.category.toLowerCase();
  const entityType = (issue.entity_type || "").toLowerCase();
  if (category.includes("timeline") || category.includes("reporting")) return "Timeline";
  if (category.includes("deliverable") || category.includes("milestone") || entityType === "deliverable" || entityType === "milestone") return "Deliverables";
  if (category.includes("risk") || entityType === "risk") return "Risks";
  if (category.includes("document")) return "Documents";
  if (entityType === "partner" || entityType === "member") return "Ownership";
  return "Coordination";
}

const EXEC_STATUS_ICON = {
  planned: { icon: faHourglass, cls: "exec-planned", label: "Planned" },
  in_progress: { icon: faPlay, cls: "exec-progress", label: "In Progress" },
  blocked: { icon: faBan, cls: "exec-blocked", label: "Blocked" },
  ready_for_closure: { icon: faCheckDouble, cls: "exec-ready", label: "Ready for Closure" },
  closed: { icon: faCheck, cls: "exec-closed", label: "Closed" },
} as const;

export function ProjectDashboard({ selectedProjectId, project, onNavigate, onProjectUpdated }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [validation, setValidation] = useState<ProjectValidationResult | null>(null);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [wps, setWps] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);
  const [milestones, setMilestones] = useState<WorkEntity[]>([]);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [risks, setRisks] = useState<ProjectRisk[]>([]);
  const [health, setHealth] = useState<DashboardHealth | null>(null);
  const [healthHistory, setHealthHistory] = useState<DashboardHealthSnapshot[]>([]);
  const [healthRecurring, setHealthRecurring] = useState<DashboardRecurringIssue[]>([]);
  const [healthScopeOptions, setHealthScopeOptions] = useState<DashboardScopeOptions>({
    work_packages: [],
    tasks: [],
    deliverables: [],
    milestones: [],
  });
  const [healthScopeType, setHealthScopeType] = useState("project");
  const [healthScopeRefId, setHealthScopeRefId] = useState("");
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthManualLoading, setHealthManualLoading] = useState(false);
  const [healthActionBusyKey, setHealthActionBusyKey] = useState("");
  const [healthActionMenuKey, setHealthActionMenuKey] = useState("");
  const [inboxItems, setInboxItems] = useState<ProjectInboxItem[]>([]);
  const [proposalSections, setProposalSections] = useState<ProjectProposalSection[]>([]);
  const [fundedModalOpen, setFundedModalOpen] = useState(false);

  useAutoRefresh(() => {
    if (selectedProjectId) {
      void loadHealth(healthScopeType, healthScopeRefId);
    }
  });

  useEffect(() => {
    if (!selectedProjectId) {
      setValidation(null);
      setPartners([]);
      setMembers([]);
      setWps([]);
      setTasks([]);
      setDeliverables([]);
      setMilestones([]);
      setDocuments([]);
      setRisks([]);
      setHealth(null);
      setHealthHistory([]);
      setHealthRecurring([]);
      setInboxItems([]);
      return;
    }
    setBusy(true);
    setError("");
    Promise.all([
      api.validateProject(selectedProjectId),
      api.listPartners(selectedProjectId),
      api.listMembers(selectedProjectId),
      api.listWorkPackages(selectedProjectId),
      api.listTasks(selectedProjectId),
      api.listDeliverables(selectedProjectId),
      api.listMilestones(selectedProjectId),
      api.listDocuments(selectedProjectId),
      api.listRisks(selectedProjectId),
    ])
      .then(([validationRes, partnersRes, membersRes, wpsRes, tasksRes, deliverablesRes, milestonesRes, documentsRes, risksRes]) => {
        setValidation(validationRes);
        setPartners(partnersRes.items);
        setMembers(membersRes.items);
        setWps(wpsRes.items);
        setTasks(tasksRes.items);
        setDeliverables(deliverablesRes.items);
        setMilestones(milestonesRes.items);
        setDocuments(documentsRes.items);
        setRisks(risksRes.items);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load dashboard."))
      .finally(() => setBusy(false));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    api.getDashboardHealthScopeOptions(selectedProjectId)
      .then((res) => setHealthScopeOptions(res))
      .catch(() => {
        setHealthScopeOptions({ work_packages: [], tasks: [], deliverables: [], milestones: [] });
      });
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    api.listProjectInbox(selectedProjectId, "", 1, 8)
      .then((res) => setInboxItems(res.items))
      .catch(() => setInboxItems([]));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || project?.project_mode !== "proposal") {
      setProposalSections([]);
      return;
    }
    api.listProjectProposalSections(selectedProjectId)
      .then((res) => setProposalSections(res.items))
      .catch(() => setProposalSections([]));
  }, [selectedProjectId, project?.project_mode]);

  useEffect(() => {
    setHealthScopeType("project");
    setHealthScopeRefId("");
    setHealth(null);
    setHealthHistory([]);
    setHealthRecurring([]);
    setInboxItems([]);
  }, [selectedProjectId]);

  async function loadHealth(
    scopeType = healthScopeType,
    scopeRefId = healthScopeRefId,
    options?: { manual?: boolean }
  ) {
    if (!selectedProjectId) return;
    if (scopeType !== "project" && !scopeRefId) {
      setHealth(null);
      return;
    }
    setHealthLoading(true);
    if (options?.manual) setHealthManualLoading(true);
    try {
      const [h, history, recurring] = await Promise.all([
        api.getDashboardHealth(selectedProjectId, scopeType, scopeRefId || null),
        api.getDashboardHealthHistory(selectedProjectId),
        api.getDashboardHealthRecurring(selectedProjectId),
      ]);
      setHealth(h);
      setHealthHistory(history);
      setHealthRecurring(recurring);
    } catch {
      /* ignore */
    } finally {
      setHealthLoading(false);
      setHealthManualLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedProjectId) return;
    if (healthScopeType !== "project" && !healthScopeRefId) {
      setHealth(null);
      setHealthHistory([]);
      setHealthRecurring([]);
      return;
    }
    api.getDashboardHealthLatest(selectedProjectId, healthScopeType, healthScopeRefId || null)
      .then(async (saved) => {
        setHealth(saved);
        const [history, recurring] = await Promise.all([
          api.getDashboardHealthHistory(selectedProjectId),
          api.getDashboardHealthRecurring(selectedProjectId),
        ]);
        setHealthHistory(history);
        setHealthRecurring(recurring);
      })
      .catch(() => {
        setHealth(null);
        setHealthHistory([]);
        setHealthRecurring([]);
      });
  }, [selectedProjectId, healthScopeType, healthScopeRefId]);

  const partnerNameById = useMemo(
    () => Object.fromEntries(partners.map((item) => [item.id, item.short_name])),
    [partners]
  );

  const reportingDates = useMemo(() => (project?.reporting_dates || []).map((item) => new Date(item)).filter((item) => !Number.isNaN(item.getTime())), [project]);
  const today = new Date();
  const runningMonth = currentProjectMonth(project?.start_date);
  const nextReportingDate = reportingDates.find((item) => item >= today) || reportingDates[0] || null;
  const indexedDocuments = documents.filter((item) => item.status === "indexed").length;
  const pendingDocuments = documents.filter((item) => item.status !== "indexed").length;
  const highRisks = risks.filter((item) => ["high", "critical"].includes(item.probability) || ["high", "critical"].includes(item.impact));
  const openRisks = risks.filter((item) => item.status !== "closed");

  const partnerLoad = useMemo(() => {
    const counts = new Map<string, { code: string; lead: number; support: number }>();
    partners.forEach((partner) => counts.set(partner.id, { code: partner.short_name, lead: 0, support: 0 }));
    for (const entity of [...wps, ...tasks, ...deliverables, ...milestones]) {
      const bucket = counts.get(entity.leader_organization_id);
      if (bucket) bucket.lead += 1;
      entity.collaborating_partner_ids.forEach((partnerId) => {
        const target = counts.get(partnerId);
        if (target) target.support += 1;
      });
    }
    return Array.from(counts.values()).sort((a, b) => b.lead - a.lead || b.support - a.support || a.code.localeCompare(b.code));
  }, [partners, wps, tasks, deliverables, milestones]);

  const deadlines = useMemo<DeadlineRow[]>(() => {
    const rows: DeadlineRow[] = [];
    for (const item of deliverables) {
      if (!item.due_month) continue;
      rows.push({
        id: item.id,
        code: item.code,
        title: item.title,
        kind: "deliverable",
        dueMonth: item.due_month,
        dueDateLabel: formatDateLabel(addMonths(project?.start_date || "", item.due_month - 1)),
        owner: partnerNameById[item.leader_organization_id] || "-",
      });
    }
    for (const item of milestones) {
      if (!item.due_month) continue;
      rows.push({
        id: item.id,
        code: item.code,
        title: item.title,
        kind: "milestone",
        dueMonth: item.due_month,
        dueDateLabel: formatDateLabel(addMonths(project?.start_date || "", item.due_month - 1)),
        owner: partnerNameById[item.leader_organization_id] || "-",
      });
    }
    return rows.sort((a, b) => a.dueMonth - b.dueMonth).slice(0, 8);
  }, [deliverables, milestones, partnerNameById, project?.start_date]);

  const wpRows = useMemo(() => {
    const tasksByWp = new Map<string, number>();
    tasks.forEach((item) => tasksByWp.set(item.wp_id || "", (tasksByWp.get(item.wp_id || "") || 0) + 1));
    const deliverablesByWp = new Map<string, number>();
    deliverables.forEach((item) => item.wp_ids.forEach((wpId) => deliverablesByWp.set(wpId, (deliverablesByWp.get(wpId) || 0) + 1)));
    return wps
      .map((wp) => ({
        id: wp.id,
        code: wp.code,
        title: wp.title,
        window: `${monthCode(wp.start_month || 1)}-${monthCode(wp.end_month || 1)}`,
        status: wp.execution_status || "planned",
        owner: partnerNameById[wp.leader_organization_id] || "-",
        tasks: tasksByWp.get(wp.id) || 0,
        deliverables: deliverablesByWp.get(wp.id) || 0,
      }))
      .sort((a, b) => a.code.localeCompare(b.code));
  }, [wps, tasks, deliverables, partnerNameById]);


  const visibleHealthIssues = useMemo(
    () => [
      ...(health?.validation_error_details || []),
      ...(health?.validation_warning_details || []),
      ...(health?.coherence_issue_details || []),
    ],
    [health]
  );
  const groupedHealthIssues = useMemo(() => {
    const groups = new Map<string, DashboardHealthIssue[]>();
    for (const issue of visibleHealthIssues) {
      const group = healthGroupForIssue(issue);
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group)!.push(issue);
    }
    return Array.from(groups.entries());
  }, [visibleHealthIssues]);
  const scopeEntityOptions = useMemo(() => {
    if (healthScopeType === "work_package") return healthScopeOptions.work_packages;
    if (healthScopeType === "task") return healthScopeOptions.tasks;
    if (healthScopeType === "deliverable") return healthScopeOptions.deliverables;
    if (healthScopeType === "milestone") return healthScopeOptions.milestones;
    return [];
  }, [healthScopeOptions, healthScopeType]);

  function removeIssueFromHealth(issueKey: string) {
    setHealth((current) => {
      if (!current) return current;
      const nextValidationErrors = current.validation_error_details.filter((item) => item.issue_key !== issueKey);
      const nextValidationWarnings = current.validation_warning_details.filter((item) => item.issue_key !== issueKey);
      const nextCoherence = current.coherence_issue_details.filter((item) => item.issue_key !== issueKey);
      return {
        ...current,
        validation_error_details: nextValidationErrors,
        validation_warning_details: nextValidationWarnings,
        coherence_issue_details: nextCoherence,
        validation_errors: nextValidationErrors.length,
        validation_warnings: nextValidationWarnings.length,
        coherence_issues: nextCoherence.length,
      };
    });
  }

  async function handleIssueState(issue: DashboardHealthIssue, nextStatus: "dismissed" | "accepted" | "snoozed") {
    if (!selectedProjectId) return;
    setHealthActionBusyKey(`${issue.issue_key}:${nextStatus}`);
    try {
      await api.updateDashboardHealthIssueState(selectedProjectId, {
        issue_key: issue.issue_key,
        source: issue.source,
        category: issue.category,
        entity_type: issue.entity_type,
        entity_id: issue.entity_id,
        status: nextStatus,
        snooze_days: nextStatus === "snoozed" ? 7 : undefined,
      });
      removeIssueFromHealth(issue.issue_key);
    } catch {
      /* ignore */
    } finally {
      setHealthActionBusyKey("");
    }
  }

  async function handleSendToInbox(issue: DashboardHealthIssue) {
    if (!selectedProjectId) return;
    setHealthActionBusyKey(`${issue.issue_key}:inbox`);
    try {
      const created = await api.createDashboardHealthIssueInbox(selectedProjectId, issue);
      await api.updateDashboardHealthIssueState(selectedProjectId, {
        issue_key: issue.issue_key,
        source: issue.source,
        category: issue.category,
        entity_type: issue.entity_type,
        entity_id: issue.entity_id,
        status: "inboxed",
      });
      const inboxRes = await api.listProjectInbox(selectedProjectId, "", 1, 8);
      setInboxItems(inboxRes.items);
      removeIssueFromHealth(issue.issue_key);
    } catch {
      /* ignore */
    } finally {
      setHealthActionBusyKey("");
    }
  }

  if (!selectedProjectId || !project) {
    return (
      <section className="panel">
        <div className="dashboard-empty"><strong>Select a project</strong></div>
      </section>
    );
  }

  if (project.project_mode === "proposal") {
    const completedSections = proposalSections.filter((s) => s.status === "completed" || s.status === "approved").length;
    const totalSections = proposalSections.length;
    const progressPct = totalSections > 0 ? Math.round((completedSections / totalSections) * 100) : 0;

    return (
      <section className="panel dashboard-panel">
        {error ? <p className="error">{error}</p> : null}

        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <span className="dashboard-project-code">{project.code}</span>
            <span className="setup-summary-sep" />
            <span className="topbar-project-status">Proposal</span>
            <span className="setup-summary-sep" />
            <span>{project.title}</span>
          </div>
        </div>

        <div className="dashboard-grid">
          <div className="dashboard-main-column">
            <div className="dashboard-card">
              <div className="dashboard-card-head">
                <h3>Proposal Progress</h3>
                {totalSections > 0 ? <span className="muted-small">{progressPct}% complete</span> : null}
              </div>
              {totalSections > 0 ? (
                <div className="dashboard-partner-stack">
                  {proposalSections.map((s) => (
                    <div key={s.id} className={`dashboard-alert ${s.status === "completed" || s.status === "approved" ? "ok" : "warning"}`}>
                      <FontAwesomeIcon icon={s.status === "completed" || s.status === "approved" ? faCheckCircle : faFileLines} />
                      <div>
                        <strong>{s.title}</strong>
                        <p>{s.status}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted-small">No proposal sections yet. Assign a proposal template in Setup.</p>
              )}
            </div>

            <div className="dashboard-card">
              <div className="dashboard-card-head">
                <h3>Consortium</h3>
              </div>
              <div className="dashboard-side-stats">
                <div className="dashboard-side-stat">
                  <FontAwesomeIcon icon={faPeopleGroup} />
                  <strong>{partners.length}</strong>
                  <span>partners</span>
                </div>
                <div className="dashboard-side-stat">
                  <FontAwesomeIcon icon={faPeopleGroup} />
                  <strong>{members.length}</strong>
                  <span>members</span>
                </div>
              </div>
            </div>

            <div className="dashboard-card">
              <div className="dashboard-card-head">
                <h3>Activity</h3>
              </div>
              <ProjectActivityFeed projectId={selectedProjectId} limit={8} />
            </div>
          </div>

          <div className="dashboard-side-column">
            <div className="dashboard-card">
              <div className="dashboard-card-head">
                <h3>Actions</h3>
              </div>
              <div className="dashboard-partner-stack">
                <button type="button" className="mode-toggle-card" onClick={() => setFundedModalOpen(true)}>
                  <strong>Mark as Funded</strong>
                  <span>Transition to execution mode</span>
                </button>
              </div>
            </div>

            <div className="dashboard-card">
              <div className="dashboard-card-head">
                <h3>Quick Nav</h3>
              </div>
              <div className="dashboard-partner-stack">
                <button type="button" className="ghost icon-text-button small" onClick={() => onNavigate("proposal")}>Proposal Workspace</button>
                <button type="button" className="ghost icon-text-button small" onClick={() => onNavigate("documents")}>Documents</button>
                <button type="button" className="ghost icon-text-button small" onClick={() => onNavigate("wizard")}>Setup</button>
              </div>
            </div>

            <div className="dashboard-card">
              <div className="dashboard-card-head">
                <h3>Knowledge Base</h3>
              </div>
              <div className="dashboard-side-stats">
                <div className="dashboard-side-stat">
                  <FontAwesomeIcon icon={faFileLines} />
                  <strong>{documents.length}</strong>
                  <span>files</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {onProjectUpdated ? (
          <MarkAsFundedModal
            open={fundedModalOpen}
            project={project}
            onClose={() => setFundedModalOpen(false)}
            onProjectUpdated={onProjectUpdated}
          />
        ) : null}
        {busy ? <p className="muted-small">Loading</p> : null}
      </section>
    );
  }

  return (
    <section className="panel dashboard-panel">
      {error ? <p className="error">{error}</p> : null}

      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span className="dashboard-project-code">{project.code}</span>
          <span className="setup-summary-sep" />
          <span>{project.status}</span>
          {runningMonth ? (
            <>
              <span className="setup-summary-sep" />
              <span>{monthCode(runningMonth)} of {project.duration_months}</span>
            </>
          ) : null}
          <span className="setup-summary-sep" />
          <span>v{project.baseline_version}</span>
          {nextReportingDate ? (
            <>
              <span className="setup-summary-sep" />
              <span>Next report {formatDateLabel(nextReportingDate)}</span>
            </>
          ) : null}
          <span className="setup-summary-sep" />
          <button type="button" className="dashboard-kpi-chip" onClick={() => onNavigate("wizard")}>
            <strong>{wps.length}</strong> WPs · <strong>{tasks.length}</strong> tasks
          </button>
          <button type="button" className="dashboard-kpi-chip" onClick={() => onNavigate("delivery")}>
            <strong>{deliverables.length}</strong> D · <strong>{milestones.length}</strong> MS
          </button>
          <button type="button" className="dashboard-kpi-chip" onClick={() => onNavigate("matrix")}>
            <strong>{partners.length}</strong> partners · <strong>{members.length}</strong> members
          </button>
          <button type="button" className="dashboard-kpi-chip" onClick={() => onNavigate("documents")}>
            <strong>{indexedDocuments}</strong> indexed · <strong>{pendingDocuments}</strong> pending
          </button>
        </div>
        <div className="proposal-summary-actions">
          <button
            type="button"
            className="ghost icon-only"
            title="Status Report"
            onClick={async () => {
              try {
                const md = await api.getStatusReport(selectedProjectId);
                const blob = new Blob([md], { type: "text/markdown" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `status-report-${project.code}.md`;
                a.click();
                URL.revokeObjectURL(url);
              } catch { /* ignore */ }
            }}
          >
            <FontAwesomeIcon icon={faDownload} />
          </button>
          <button
            type="button"
            className="ghost icon-only"
            title="Audit Log"
            onClick={async () => {
              try {
                const blob = await api.getAuditLogCsv(selectedProjectId);
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `audit-log-${project.code}.csv`;
                a.click();
                URL.revokeObjectURL(url);
              } catch { /* ignore */ }
            }}
          >
            <FontAwesomeIcon icon={faFileLines} />
          </button>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="dashboard-main-column">
          {/* Health */}
          {health ? (
            <div className={`dashboard-health-widget health-${health.health_score} dashboard-card`}>
              <div className="health-panel-head">
                <div className="health-score-indicator">
                  <span className={`health-dot ${health.health_score}`} />
                  <strong>{health.health_score === "green" ? "Healthy" : health.health_score === "yellow" ? "Needs Attention" : "Critical"}</strong>
                  {healthHistory.length ? (
                    <div className="health-history-strip">
                      {healthHistory.slice(0, 8).map((snap) => (
                        <div
                          key={snap.id}
                          className={`health-history-dot ${snap.health_score}`}
                          title={`${new Date(snap.created_at).toLocaleString()} · ${snap.validation_errors}E/${snap.validation_warnings}W/${snap.coherence_issues}C`}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="health-scope-bar">
                  <select
                    className="health-scope-select"
                    value={healthScopeType}
                    onChange={(event) => {
                      setHealthScopeType(event.target.value);
                      setHealthScopeRefId("");
                    }}
                  >
                    <option value="project">Project</option>
                    <option value="work_package">Work Package</option>
                    <option value="task">Task</option>
                    <option value="deliverable">Deliverable</option>
                    <option value="milestone">Milestone</option>
                  </select>
                  {healthScopeType !== "project" ? (
                    <select
                      className="health-scope-select"
                      value={healthScopeRefId}
                      onChange={(event) => setHealthScopeRefId(event.target.value)}
                    >
                      <option value="">Select</option>
                      {scopeEntityOptions.map((opt) => (
                        <option key={opt.id} value={opt.id}>{opt.label}</option>
                      ))}
                    </select>
                  ) : null}
                  <button
                    type="button"
                    className="ghost small"
                    disabled={healthLoading || (healthScopeType !== "project" && !healthScopeRefId)}
                    onClick={async () => {
                      await loadHealth(healthScopeType, healthScopeRefId, { manual: true });
                    }}
                  >
                    {healthManualLoading ? (
                      <><FontAwesomeIcon icon={faSpinner} spin /> Checking...</>
                    ) : "Run Check"}
                  </button>
                </div>
              </div>
              <div className="health-metrics">
                {health.validation_errors > 0 ? <span className="health-metric red">{health.validation_errors} validation errors</span> : null}
                {health.validation_warnings > 0 ? <span className="health-metric yellow">{health.validation_warnings} warnings</span> : null}
                {health.coherence_issues > 0 ? <span className="health-metric yellow">{health.coherence_issues} coherence issues</span> : null}
                {health.action_items_pending > 0 ? <span className="health-metric">{health.action_items_pending} pending actions</span> : null}
                {health.risks_open > 0 ? <span className="health-metric">{health.risks_open} open risks</span> : null}
                {health.overdue_deliverables > 0 ? <span className="health-metric red">{health.overdue_deliverables} overdue deliverables</span> : null}
                {health.validation_errors === 0 && health.validation_warnings === 0 && health.coherence_issues === 0 && health.overdue_deliverables === 0 ? (
                  <span className="health-metric green">All checks passed</span>
                ) : null}
              </div>
              {groupedHealthIssues.length ? (
                <div className="health-issue-groups">
                  {groupedHealthIssues.map(([group, items]) => (
                    <div key={group} className="health-group">
                      <div className="dashboard-card-head">
                        <h3>{group}</h3>
                      </div>
                      <div className="health-issue-list">
                        {items.map((item) => {
                          const navigateAction = healthActionForIssue(item);
                          return (
                            <div key={item.issue_key} className={`health-issue-item ${item.severity === "error" ? "red" : "yellow"}`}>
                              <div className="health-issue-content">
                                <strong>{item.category}</strong>
                                <span>{item.message}</span>
                                {item.suggestion ? <em>{item.suggestion}</em> : null}
                              </div>
                              <div style={{ position: "relative" }}>
                                <button
                                  type="button"
                                  className="ghost icon-only"
                                  onClick={() => setHealthActionMenuKey((prev) => prev === item.issue_key ? "" : item.issue_key)}
                                >
                                  <FontAwesomeIcon icon={faEllipsis} />
                                </button>
                                {healthActionMenuKey === item.issue_key ? (
                                  <>
                                    <div style={{ position: "fixed", inset: 0, zIndex: 19 }} onClick={() => setHealthActionMenuKey("")} />
                                    <div className="proposal-table-dropdown" style={{ right: 0, left: "auto" }}>
                                      {item.primary_action?.type === "send_to_inbox" ? (
                                        <button
                                          type="button"
                                          disabled={healthActionBusyKey === `${item.issue_key}:inbox`}
                                          onClick={() => { setHealthActionMenuKey(""); void handleSendToInbox(item); }}
                                        >
                                          {healthActionBusyKey === `${item.issue_key}:inbox` ? "Working..." : "Send to Inbox"}
                                        </button>
                                      ) : null}
                                      {navigateAction ? (
                                        <button type="button" onClick={() => { setHealthActionMenuKey(""); onNavigate(navigateAction.view); }}>
                                          {navigateAction.label}
                                        </button>
                                      ) : null}
                                      <button
                                        type="button"
                                        disabled={healthActionBusyKey === `${item.issue_key}:dismissed`}
                                        onClick={() => { setHealthActionMenuKey(""); void handleIssueState(item, "dismissed"); }}
                                      >
                                        Dismiss
                                      </button>
                                      <button
                                        type="button"
                                        disabled={healthActionBusyKey === `${item.issue_key}:snoozed`}
                                        onClick={() => { setHealthActionMenuKey(""); void handleIssueState(item, "snoozed"); }}
                                      >
                                        Snooze 7d
                                      </button>
                                      <button
                                        type="button"
                                        disabled={healthActionBusyKey === `${item.issue_key}:accepted`}
                                        onClick={() => { setHealthActionMenuKey(""); void handleIssueState(item, "accepted"); }}
                                      >
                                        Accept
                                      </button>
                                    </div>
                                  </>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {healthRecurring.length ? (
                <div className="health-recurring">
                  <div className="dashboard-card-head">
                    <h3>Recurring</h3>
                  </div>
                  <div className="health-recurring-list">
                    {healthRecurring.map((item) => (
                      <div key={`${item.issue_key}-${item.category}`} className="health-recurring-item">
                        <span className="health-recurring-count">
                          <FontAwesomeIcon icon={faWaveSquare} /> {item.count}
                        </span>
                        <span>{item.message || item.category}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {/* Upcoming deadlines */}
          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Upcoming</h3>
            </div>
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th style={{ width: 28 }}></th>
                    <th>Code</th>
                    <th>Title</th>
                    <th>Owner</th>
                    <th>Due</th>
                  </tr>
                </thead>
                <tbody>
                  {deadlines.map((item) => (
                    <tr key={`${item.kind}-${item.id}`}>
                      <td>
                        <span className={`dashboard-kind ${item.kind}`}>{item.kind === "deliverable" ? "D" : "MS"}</span>
                      </td>
                      <td><strong>{item.code}</strong></td>
                      <td>{item.title}</td>
                      <td>{item.owner}</td>
                      <td>
                        <strong>{monthCode(item.dueMonth)}</strong>
                        <span className="dashboard-due-date">{item.dueDateLabel}</span>
                      </td>
                    </tr>
                  ))}
                  {deadlines.length === 0 ? <tr><td colSpan={5}>No deadlines</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>

          {/* Work packages */}
          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Work Packages</h3>
            </div>
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>WP</th>
                    <th>Title</th>
                    <th>Window</th>
                    <th>Status</th>
                    <th>Owner</th>
                    <th>Load</th>
                  </tr>
                </thead>
                <tbody>
                  {wpRows.map((item) => (
                    <tr key={item.id}>
                      <td><strong>{item.code}</strong></td>
                      <td>{item.title}</td>
                      <td>{item.window}</td>
                      <td>{(() => { const s = EXEC_STATUS_ICON[item.status as keyof typeof EXEC_STATUS_ICON] || EXEC_STATUS_ICON.planned; return <span className={`exec-status-icon ${s.cls}`} title={s.label}><FontAwesomeIcon icon={s.icon} /></span>; })()}</td>
                      <td>{item.owner}</td>
                      <td>{item.tasks}T · {item.deliverables}D</td>
                    </tr>
                  ))}
                  {wpRows.length === 0 ? <tr><td colSpan={6}>No work packages</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>

          {/* Activity */}
          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Activity</h3>
            </div>
            <ProjectActivityFeed projectId={selectedProjectId} limit={8} />
          </div>
        </div>

        <div className="dashboard-side-column">
          {/* Reporting dates */}
          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Reporting</h3>
            </div>
            <div className="dashboard-report-list">
              {reportingDates.map((item) => {
                const itemMonth = Math.max(1, (item.getFullYear() - new Date(project.start_date).getFullYear()) * 12 + (item.getMonth() - new Date(project.start_date).getMonth()) + 1);
                const isNext = nextReportingDate?.toISOString() === item.toISOString();
                return (
                  <div key={item.toISOString()} className={`dashboard-report-row ${isNext ? "active" : ""}`}>
                    <FontAwesomeIcon icon={faCalendarDay} className="dashboard-report-icon" />
                    <strong>{monthCode(itemMonth)}</strong>
                    <span>{formatDateLabel(item)}</span>
                  </div>
                );
              })}
              {reportingDates.length === 0 ? <div className="dashboard-empty-row">No reporting dates</div> : null}
            </div>
          </div>

          {/* Partner load */}
          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Partner Load</h3>
            </div>
            <div className="dashboard-partner-stack">
              {partnerLoad.map((item) => (
                <div key={item.code} className="dashboard-partner-row">
                  <div className="dashboard-partner-head">
                    <strong>{item.code}</strong>
                    <span>{item.lead} lead · {item.support} support</span>
                  </div>
                  <div className="dashboard-partner-bar">
                    <span style={{ width: `${Math.min(100, item.lead * 12 + item.support * 6)}%` }} />
                  </div>
                </div>
              ))}
              {partnerLoad.length === 0 ? <div className="dashboard-empty-row">No partners</div> : null}
            </div>
          </div>

          {/* Overview */}
          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Overview</h3>
            </div>
            <div className="dashboard-side-stats">
              <div className="dashboard-side-stat">
                <FontAwesomeIcon icon={faShieldHalved} />
                <strong>{openRisks.length}</strong>
                <span>open risks</span>
              </div>
              <div className={`dashboard-side-stat ${highRisks.length > 0 ? "danger" : ""}`}>
                <FontAwesomeIcon icon={faExclamationTriangle} />
                <strong>{highRisks.length}</strong>
                <span>high</span>
              </div>
            </div>
            <div className="dashboard-side-stats three" style={{ marginTop: 8 }}>
              <div className="dashboard-side-stat">
                <FontAwesomeIcon icon={faFileLines} />
                <strong>{documents.length}</strong>
                <span>files</span>
              </div>
              <div className="dashboard-side-stat">
                <FontAwesomeIcon icon={faCheckCircle} />
                <strong>{indexedDocuments}</strong>
                <span>indexed</span>
              </div>
              <div className={`dashboard-side-stat ${pendingDocuments > 0 ? "warning" : ""}`}>
                <FontAwesomeIcon icon={faBookOpen} />
                <strong>{pendingDocuments}</strong>
                <span>pending</span>
              </div>
            </div>
          </div>

          <div className="dashboard-card">
            <div className="dashboard-card-head">
              <h3>Inbox</h3>
            </div>
            <div className="dashboard-partner-stack">
              {inboxItems.map((item) => (
                <div key={item.id} className="dashboard-alert warning">
                  <FontAwesomeIcon icon={faFileLines} />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.status}</p>
                  </div>
                  <div className="health-issue-actions">
                    {item.status !== "in_progress" ? (
                      <button type="button" className="ghost small" onClick={async () => {
                        if (!selectedProjectId) return;
                        const updated = await api.updateProjectInbox(selectedProjectId, item.id, { status: "in_progress" });
                        setInboxItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
                      }}>Start</button>
                    ) : null}
                    {item.status !== "done" ? (
                      <button type="button" className="ghost small" onClick={async () => {
                        if (!selectedProjectId) return;
                        const updated = await api.updateProjectInbox(selectedProjectId, item.id, { status: "done" });
                        setInboxItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
                      }}>Done</button>
                    ) : null}
                  </div>
                </div>
              ))}
              {inboxItems.length === 0 ? <div className="dashboard-empty-row">No inbox items</div> : null}
            </div>
          </div>
        </div>
      </div>

      {busy ? <p className="muted-small">Loading</p> : null}
    </section>
  );
}
