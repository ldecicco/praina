import { useEffect, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { Course, Project } from "../types";

type Props = {
  open: boolean;
  platformSection: "research" | "teaching";
  onClose: () => void;
  onProjectCreated: (project: Project) => void;
};

type ProjectMode = "proposal" | "execution";
type ProjectKind = "funded" | "teaching";

function parseReportingDates(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function NewProjectModal({ open, platformSection, onClose, onProjectCreated }: Props) {
  const initialKind: ProjectKind = platformSection === "teaching" ? "teaching" : "funded";
  const initialMode: ProjectMode = platformSection === "teaching" ? "execution" : "proposal";
  const [mode, setMode] = useState<ProjectMode>(initialMode);
  const [kind, setKind] = useState<ProjectKind>(initialKind);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState("");
  const [durationMonths, setDurationMonths] = useState(36);
  const [reportingDatesText, setReportingDatesText] = useState("");
  const [courses, setCourses] = useState<Course[]>([]);
  const [teachingCourseId, setTeachingCourseId] = useState("");
  const [teachingAcademicYear, setTeachingAcademicYear] = useState("");
  const [teachingTerm, setTeachingTerm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isTeaching = kind === "teaching";
  const isProposal = !isTeaching && mode === "proposal";
  const canSubmit = isProposal
    ? !busy && !!code.trim() && !!title.trim()
    : !busy && !!code.trim() && !!title.trim() && !!startDate && durationMonths >= 1 && (!isTeaching || !!teachingCourseId);

  useEffect(() => {
    if (!open) return;
    setKind(initialKind);
    setMode(initialMode);
    api.listCourses(1, 200, "", true)
      .then((response) => setCourses(response.items))
      .catch(() => setCourses([]));
  }, [open, initialKind, initialMode]);

  function resetForm() {
    setMode(initialMode);
    setKind(initialKind);
    setCode("");
    setTitle("");
    setDescription("");
    setStartDate("");
    setDurationMonths(36);
    setReportingDatesText("");
    setTeachingCourseId("");
    setTeachingAcademicYear("");
    setTeachingTerm("");
    setBusy(false);
    setError("");
  }

  function handleClose() {
    if (busy) return;
    resetForm();
    onClose();
  }

  async function handleCreate() {
    try {
      setBusy(true);
      setError("");
      const payload: Parameters<typeof api.createProject>[0] = {
        code,
        title,
        description: description || undefined,
        project_mode: isTeaching ? "execution" : mode,
        project_kind: kind,
        teaching_course_id: isTeaching ? teachingCourseId || null : undefined,
        teaching_academic_year: isTeaching ? teachingAcademicYear || null : undefined,
        teaching_term: isTeaching ? teachingTerm || null : undefined,
      };
      if (!isProposal) {
        payload.start_date = startDate;
        payload.duration_months = isTeaching ? 1 : durationMonths;
        if (!isTeaching) {
          payload.reporting_dates = parseReportingDates(reportingDatesText);
        }
      }
      const created = await api.createProject(payload);
      resetForm();
      onProjectCreated(created);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project.");
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <FocusLock returnFocus>
        <div
          className="modal-card settings-modal-card new-project-modal-card"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !(event.target instanceof HTMLTextAreaElement) && canSubmit) {
              event.preventDefault();
              void handleCreate();
            }
          }}
        >
          <div className="modal-head">
            <h3>New Project</h3>
            <div className="modal-head-actions">
              <button type="button" disabled={!canSubmit} onClick={() => void handleCreate()}>
                {busy ? "Creating..." : isProposal ? "Create Proposal" : "Create Project"}
              </button>
              <button type="button" className="ghost docs-action-btn" onClick={handleClose} title="Close">
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          </div>

          {!isTeaching ? (
            <div className="mode-toggle-row">
              <button
                type="button"
                className={`mode-toggle-card ${isProposal ? "active" : ""}`}
                onClick={() => setMode("proposal")}
              >
                <strong>Proposal</strong>
              </button>
              <button
                type="button"
                className={`mode-toggle-card ${!isProposal ? "active" : ""}`}
                onClick={() => setMode("execution")}
              >
                <strong>Execution</strong>
              </button>
            </div>
          ) : null}

          {error ? <p className="error">{error}</p> : null}

          <div className="new-project-stack">
            <div className="form-grid">
              <label>
                Acronym
                <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="ACRONYM" />
              </label>
              <label>
                Name
                <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Full project name" />
              </label>
              {!isProposal ? (
                <>
                  {isTeaching ? (
                    <>
                      <label>
                        Course
                        <select value={teachingCourseId} onChange={(event) => setTeachingCourseId(event.target.value)}>
                          <option value="">Select</option>
                          {courses.map((course) => (
                            <option key={course.id} value={course.id}>{course.code} · {course.title}</option>
                          ))}
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
                  <label>
                    Start Date
                    <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                  </label>
                  {!isTeaching ? (
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
                  {!isTeaching ? (
                    <label className="full-span">
                      Reporting Dates
                      <input
                        value={reportingDatesText}
                        onChange={(event) => setReportingDatesText(event.target.value)}
                        placeholder="2026-06-30, 2026-12-31"
                      />
                    </label>
                  ) : null}
                </>
              ) : null}
              <label className="full-span">
                Short Description
                <textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
              </label>
            </div>
          </div>
        </div>
      </FocusLock>
    </div>
  );
}
