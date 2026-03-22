import { useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";

import { api } from "../lib/api";
import type { AuthUser, Course, Member, Partner, Project, ProjectValidationResult } from "../types";
import { MarkAsFundedModal } from "./MarkAsFundedModal";

type Props = {
  open: boolean;
  project: Project | null;
  currentUser: AuthUser | null;
  onClose: () => void;
  onProjectUpdated: (project: Project) => void;
  onProjectDeleted: (projectId: string) => void;
};

function parseReportingDates(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProjectSettingsModal({ open, project, currentUser, onClose, onProjectUpdated, onProjectDeleted }: Props) {
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState("");
  const [durationMonths, setDurationMonths] = useState(36);
  const [reportingDatesText, setReportingDatesText] = useState("");
  const [validation, setValidation] = useState<ProjectValidationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [language, setLanguage] = useState("en_GB");
  const [coordinatorPartnerId, setCoordinatorPartnerId] = useState("");
  const [principalInvestigatorId, setPrincipalInvestigatorId] = useState("");
  const [partners, setPartners] = useState<Partner[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [teachingCourseId, setTeachingCourseId] = useState("");
  const [teachingAcademicYear, setTeachingAcademicYear] = useState("");
  const [teachingTerm, setTeachingTerm] = useState("");
  const [status, setStatus] = useState("");
  const [fundedModalOpen, setFundedModalOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<"archive" | "delete" | null>(null);

  useEffect(() => {
    if (!project) {
      setCode("");
      setTitle("");
      setDescription("");
      setStartDate("");
      setDurationMonths(36);
      setReportingDatesText("");
      setLanguage("en_GB");
      setCoordinatorPartnerId("");
      setPrincipalInvestigatorId("");
      setPartners([]);
      setMembers([]);
      setCourses([]);
      setTeachingCourseId("");
      setTeachingAcademicYear("");
      setTeachingTerm("");
      setValidation(null);
      setError("");
      setStatus("");
      return;
    }
    setCode(project.code);
    setTitle(project.title);
    setDescription(project.description || "");
    setStartDate(project.start_date);
    setDurationMonths(project.duration_months);
    setReportingDatesText(project.reporting_dates.join(", "));
    setLanguage(project.language || "en_GB");
    setCoordinatorPartnerId(project.coordinator_partner_id || "");
    setPrincipalInvestigatorId(project.principal_investigator_id || "");
    setValidation(null);
    setError("");
    setStatus("");
    Promise.all([
      api.listPartners(project.id),
      api.listMembers(project.id),
      api.listCourses(1, 200, "", true),
      project.project_kind === "teaching" ? api.getTeachingWorkspace(project.id) : Promise.resolve(null),
    ])
      .then(([partnersRes, membersRes, coursesRes, teachingWorkspace]) => {
        setPartners(partnersRes.items);
        setMembers(membersRes.items);
        setCourses(coursesRes.items);
        if (teachingWorkspace) {
          setTeachingCourseId(teachingWorkspace.profile.course_id || "");
          setTeachingAcademicYear(teachingWorkspace.profile.academic_year || "");
          setTeachingTerm(teachingWorkspace.profile.term || "");
        }
      })
      .catch(() => {});
  }, [project, open]);

  const coordinatorMembers = useMemo(
    () => members.filter((m) => m.partner_id === coordinatorPartnerId),
    [members, coordinatorPartnerId]
  );
  const isSuperAdmin = currentUser?.platform_role === "super_admin";

  useEffect(() => {
    if (!principalInvestigatorId) return;
    if (coordinatorMembers.some((member) => member.id === principalInvestigatorId)) return;
    setPrincipalInvestigatorId("");
  }, [coordinatorMembers, principalInvestigatorId]);

  if (!open) return null;

  async function handleSave() {
    if (!project) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.updateProject(project.id, {
        code,
        title,
        description: description || null,
        start_date: startDate,
        duration_months: project.project_kind === "teaching" ? undefined : durationMonths,
        reporting_dates: parseReportingDates(reportingDatesText),
        language,
        teaching_course_id: project.project_kind === "teaching" ? teachingCourseId || null : undefined,
        teaching_academic_year: project.project_kind === "teaching" ? teachingAcademicYear || null : undefined,
        teaching_term: project.project_kind === "teaching" ? teachingTerm || null : undefined,
        coordinator_partner_id: coordinatorPartnerId || null,
        principal_investigator_id: principalInvestigatorId || null,
      });
      onProjectUpdated(updated);
      setStatus("Project settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save project settings.");
    } finally {
      setBusy(false);
    }
  }

  async function handleValidate() {
    if (!project) return;
    try {
      setBusy(true);
      setError("");
      const result = await api.validateProject(project.id);
      setValidation(result);
      setStatus(result.valid ? "Validation passed." : "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to validate project.");
    } finally {
      setBusy(false);
    }
  }

  async function handleActivate() {
    if (!project) return;
    try {
      setBusy(true);
      setError("");
      const result = await api.activateProject(project.id);
      onProjectUpdated({ ...project, status: result.status, baseline_version: result.baseline_version });
      setStatus(`Project activated. Baseline v${result.baseline_version}.`);
      const validationResult = await api.validateProject(project.id);
      setValidation(validationResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate project.");
    } finally {
      setBusy(false);
    }
  }

  async function handleArchiveProject() {
    if (!project) return;
    try {
      setBusy(true);
      setError("");
      const archived = await api.archiveProject(project.id);
      onProjectUpdated(archived);
      setConfirmAction(null);
      setStatus("Project archived.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive project.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteProject() {
    if (!project) return;
    try {
      setBusy(true);
      setError("");
      await api.deleteProject(project.id);
      onProjectDeleted(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete project.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <FocusLock returnFocus>
      <div className="modal-card settings-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy) { e.preventDefault(); void handleSave(); } }}>
        <div className="modal-head">
          <h3>Project Settings</h3>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>

        {error ? <p className="error">{error}</p> : null}
        {status ? <p className="success">{status}</p> : null}

        {project ? (
          <div className="settings-layout">
            <div className="card">
              <div className="form-grid">
                <label>
                  Code
                  <input value={code} onChange={(event) => setCode(event.target.value)} />
                </label>
                <label>
                  Title
                  <input value={title} onChange={(event) => setTitle(event.target.value)} />
                </label>
                <label>
                  Start Date
                  <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                </label>
                {project.project_kind !== "teaching" ? (
                  <label>
                    Duration Months
                    <input
                      type="number"
                      min={1}
                      max={120}
                      value={durationMonths}
                      onChange={(event) => setDurationMonths(Number(event.target.value) || 1)}
                    />
                  </label>
                ) : null}
                <label className="full-span">
                  Reporting Dates
                  <input
                    value={reportingDatesText}
                    onChange={(event) => setReportingDatesText(event.target.value)}
                    placeholder="2026-06-30, 2026-12-31"
                  />
                </label>
                <label className="full-span">
                  Description
                  <textarea rows={5} value={description} onChange={(event) => setDescription(event.target.value)} />
                </label>
                <label>
                  Language
                  <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                    <option value="en_GB">English (UK)</option>
                    <option value="en_US">English (US)</option>
                    <option value="it">Italian</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                    <option value="es">Spanish</option>
                    <option value="pt">Portuguese</option>
                  </select>
                </label>
                {project.project_kind === "teaching" ? (
                  <>
                    <label>
                      Course
                      <select value={teachingCourseId} onChange={(event) => setTeachingCourseId(event.target.value)}>
                        <option value="">Select</option>
                        {courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.title}</option>)}
                      </select>
                    </label>
                    <label>
                      Academic Year
                      <input value={teachingAcademicYear} onChange={(event) => setTeachingAcademicYear(event.target.value)} placeholder="2025/2026" />
                    </label>
                    <label>
                      Term
                      <input value={teachingTerm} onChange={(event) => setTeachingTerm(event.target.value)} placeholder="spring" />
                    </label>
                  </>
                ) : null}
                {partners.length > 0 ? (
                  <>
                    <label>
                      Coordinator Partner
                      <select value={coordinatorPartnerId} onChange={(event) => { setCoordinatorPartnerId(event.target.value); setPrincipalInvestigatorId(""); }}>
                        <option value="">None</option>
                        {partners.map((p) => <option key={p.id} value={p.id}>{p.short_name}</option>)}
                      </select>
                    </label>
                    <label>
                      Principal Investigator
                      <select value={principalInvestigatorId} onChange={(event) => setPrincipalInvestigatorId(event.target.value)} disabled={!coordinatorPartnerId}>
                        <option value="">None</option>
                        {coordinatorMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                      </select>
                    </label>
                  </>
                ) : null}
              </div>
              <div className="row-actions">
                <button
                  type="button"
                  disabled={busy || !code.trim() || !title.trim() || !startDate || durationMonths < 1}
                  onClick={() => void handleSave()}
                >
                  Save
                </button>
                <button type="button" className="ghost" disabled={busy} onClick={() => void handleValidate()}>
                  Validate
                </button>
                <button type="button" className="ghost" disabled={busy} onClick={() => void handleActivate()}>
                  Activate
                </button>
              </div>
            </div>

            <div className="card">
              <div className="settings-status-grid">
                <div>
                  <span className="label">Status</span>
                  <strong>{project.status}</strong>
                </div>
                <div>
                  <span className="label">Mode</span>
                  <strong>{project.project_mode === "proposal" ? "Proposal" : "Execution"}</strong>
                </div>
                <div>
                  <span className="label">Baseline</span>
                  <strong>v{project.baseline_version}</strong>
                </div>
              </div>
              {project.project_mode === "proposal" ? (
                <div className="row-actions">
                  <button type="button" onClick={() => setFundedModalOpen(true)}>
                    Mark as Funded
                  </button>
                </div>
              ) : null}
              {isSuperAdmin ? (
                <div className="row-actions">
                  <button type="button" className="ghost" disabled={busy} onClick={() => setConfirmAction("archive")}>
                    Archive
                  </button>
                  <button type="button" className="danger" disabled={busy} onClick={() => setConfirmAction("delete")}>
                    Delete Project
                  </button>
                </div>
              ) : null}

              <div className="settings-validation-list">
                {(validation?.errors || []).map((item) => (
                  <div key={`${item.entity_type}-${item.entity_id}-${item.code}`} className="settings-validation-item error">
                    <strong>{item.code}</strong>
                    <span>{item.message}</span>
                  </div>
                ))}
                {(validation?.warnings || []).map((item) => (
                  <div key={`${item.entity_type}-${item.entity_id}-${item.code}`} className="settings-validation-item warning">
                    <strong>{item.code}</strong>
                    <span>{item.message}</span>
                  </div>
                ))}
                {validation && validation.errors.length === 0 && validation.warnings.length === 0 ? (
                  <div className="settings-validation-item ok">
                    <strong>OK</strong>
                    <span>No validation issues.</span>
                  </div>
                ) : null}
                {!validation ? <div className="settings-validation-item"><span>Run validation to check the project.</span></div> : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="card">
            <h3>No Active Project</h3>
          </div>
        )}
        {project?.project_mode === "proposal" ? (
          <MarkAsFundedModal
            open={fundedModalOpen}
            project={project}
            onClose={() => setFundedModalOpen(false)}
            onProjectUpdated={onProjectUpdated}
          />
        ) : null}
        {project && confirmAction ? (
          <div className="modal-overlay" role="dialog" aria-modal="true" onClick={(e) => { if (e.target === e.currentTarget) setConfirmAction(null); }}>
            <div className="modal-card project-confirm-card">
              <div className="modal-head">
                <h3>{confirmAction === "archive" ? "Archive Project" : "Delete Project"}</h3>
                <button type="button" className="ghost" onClick={() => setConfirmAction(null)}>
                  Close
                </button>
              </div>
              <div className="project-confirm-body">
                <strong>{project.code}</strong>
                <span>{project.title}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost" onClick={() => setConfirmAction(null)} disabled={busy}>
                  Cancel
                </button>
                <button
                  type="button"
                  className={confirmAction === "delete" ? "danger" : ""}
                  onClick={() => void (confirmAction === "archive" ? handleArchiveProject() : handleDeleteProject())}
                  disabled={busy}
                >
                  {confirmAction === "archive" ? "Archive" : "Delete"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
      </FocusLock>
    </div>
  );
}
