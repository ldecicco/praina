import { useState } from "react";
import FocusLock from "react-focus-lock";

import { api } from "../lib/api";
import type { Project } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  onProjectCreated: (project: Project) => void;
};

type ProjectMode = "proposal" | "execution";

function parseReportingDates(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function NewProjectModal({ open, onClose, onProjectCreated }: Props) {
  const [mode, setMode] = useState<ProjectMode>("proposal");
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState("");
  const [durationMonths, setDurationMonths] = useState(36);
  const [reportingDatesText, setReportingDatesText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isProposal = mode === "proposal";
  const canSubmit = isProposal
    ? !busy && !!code.trim() && !!title.trim()
    : !busy && !!code.trim() && !!title.trim() && !!startDate && durationMonths >= 1;

  function resetForm() {
    setMode("proposal");
    setCode("");
    setTitle("");
    setDescription("");
    setStartDate("");
    setDurationMonths(36);
    setReportingDatesText("");
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
        project_mode: mode,
      };
      if (!isProposal) {
        payload.start_date = startDate;
        payload.duration_months = durationMonths;
        payload.reporting_dates = parseReportingDates(reportingDatesText);
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
            <button type="button" className="ghost" onClick={handleClose}>
              Close
            </button>
          </div>

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

          {error ? <p className="error">{error}</p> : null}

          <div className="new-project-stack">
            <div className="setup-summary-bar">
              <div className="setup-summary-stats">
                <span>{code.trim() || "No code"}</span>
                <span className="setup-summary-sep" />
                <span>{title.trim() || "No title"}</span>
                <span className="setup-summary-sep" />
                <span>{isProposal ? "Proposal" : "Execution"}</span>
              </div>
            </div>

            <section className="new-project-section">
              <div className="proposal-card-head">
                <strong>Project</strong>
              </div>
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
                    <label>
                      Start Date
                      <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                    </label>
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
                    <label className="full-span">
                      Reporting Dates
                      <input
                        value={reportingDatesText}
                        onChange={(event) => setReportingDatesText(event.target.value)}
                        placeholder="2026-06-30, 2026-12-31"
                      />
                    </label>
                  </>
                ) : null}
                <label className="full-span">
                  Short Description
                  <textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
                </label>
              </div>
            </section>
          </div>

          <div className="row-actions">
            <button type="button" disabled={!canSubmit} onClick={() => void handleCreate()}>
              {busy ? "Creating..." : isProposal ? "Create Proposal" : "Create Project"}
            </button>
          </div>
        </div>
      </FocusLock>
    </div>
  );
}
