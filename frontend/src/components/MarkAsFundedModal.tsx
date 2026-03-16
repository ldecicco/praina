import { useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import type { Project } from "../types";

type Props = {
  open: boolean;
  project: Project;
  onClose: () => void;
  onProjectUpdated: (project: Project) => void;
};

function parseReportingDates(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function MarkAsFundedModal({ open, project, onClose, onProjectUpdated }: Props) {
  const [startDate, setStartDate] = useState("");
  const [durationMonths, setDurationMonths] = useState(36);
  const [reportingDatesText, setReportingDatesText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  async function handleSubmit() {
    try {
      setBusy(true);
      setError("");
      await api.markAsFunded(project.id, {
        start_date: startDate,
        duration_months: durationMonths,
        reporting_dates: parseReportingDates(reportingDatesText),
      });
      onProjectUpdated({
        ...project,
        project_mode: "execution",
        start_date: startDate,
        duration_months: durationMonths,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to mark as funded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <FocusLock returnFocus>
      <div className="modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy && startDate && durationMonths >= 1) { e.preventDefault(); void handleSubmit(); } }}>
        <div className="modal-head">
          <h3>Mark as Funded</h3>
          <button type="button" className="ghost docs-action-btn" onClick={onClose} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
        </div>
        <p className="muted-small">
          Transition <strong>{project.code}</strong> from proposal to execution mode. The project will remain in draft status so you can complete the setup wizard.
        </p>
        {error ? <p className="error">{error}</p> : null}
        <div className="form-grid">
          <label>
            Start Date
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            Duration (months)
            <input
              type="number"
              min={1}
              max={120}
              value={durationMonths}
              onChange={(e) => setDurationMonths(Number(e.target.value) || 1)}
            />
          </label>
          <label className="full-span">
            Reporting Dates (optional)
            <input
              value={reportingDatesText}
              onChange={(e) => setReportingDatesText(e.target.value)}
              placeholder="2026-06-30, 2026-12-31"
            />
          </label>
        </div>
        <div className="row-actions">
          <button
            type="button"
            disabled={busy || !startDate || durationMonths < 1}
            onClick={() => void handleSubmit()}
          >
            {busy ? "Processing..." : "Mark as Funded"}
          </button>
        </div>
      </div>
      </FocusLock>
    </div>
  );
}
