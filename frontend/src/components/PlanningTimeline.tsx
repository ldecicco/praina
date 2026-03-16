import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import { currentProjectMonth } from "../lib/utils";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type { Project, WorkEntity } from "../types";

type Props = {
  selectedProjectId: string;
  project: Project | null;
  onNavigate?: () => void;
};

type TimelineRow = {
  id: string;
  code: string;
  title: string;
  kind: "wp" | "task";
  wpId: string | null;
  startMonth: number;
  endMonth: number;
  dueMonth: number | null;
  executionStatus: string | null;
};

function projectMonthForDate(startDate: string | null | undefined, isoDate: string): number | null {
  if (!startDate) return null;
  const start = new Date(startDate);
  const target = new Date(isoDate);
  if (Number.isNaN(start.getTime()) || Number.isNaN(target.getTime())) return null;
  return Math.max(1, (target.getFullYear() - start.getFullYear()) * 12 + (target.getMonth() - start.getMonth()) + 1);
}

export function PlanningTimeline({ selectedProjectId, project, onNavigate }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [horizon, setHorizon] = useState(36);

  const [wps, setWps] = useState<WorkEntity[]>([]);
  const [tasks, setTasks] = useState<WorkEntity[]>([]);
  const [milestones, setMilestones] = useState<WorkEntity[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);

  const loadData = useCallback(() => {
    if (!selectedProjectId) return;
    setBusy(true);
    setError("");
    Promise.all([
      api.listWorkPackages(selectedProjectId),
      api.listTasks(selectedProjectId),
      api.listMilestones(selectedProjectId),
      api.listDeliverables(selectedProjectId),
    ])
      .then(([wpsRes, tasksRes, msRes, delRes]) => {
        setWps(wpsRes.items);
        setTasks(tasksRes.items);
        setMilestones(msRes.items);
        setDeliverables(delRes.items);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load timeline data."))
      .finally(() => setBusy(false));
  }, [selectedProjectId]);

  useAutoRefresh(loadData);

  const months = useMemo(() => Array.from({ length: horizon }, (_, idx) => idx + 1), [horizon]);
  const nowMonth = useMemo(() => currentProjectMonth(project?.start_date), [project?.start_date]);
  const reportingMarkers = useMemo(
    () =>
      (project?.reporting_dates || [])
        .map((item) => ({
          date: item,
          month: projectMonthForDate(project?.start_date, item),
        }))
        .filter((item): item is { date: string; month: number } => item.month !== null),
    [project?.reporting_dates, project?.start_date]
  );

  // Auto-detect horizon from data
  useEffect(() => {
    const allEntities = [...wps, ...tasks, ...milestones, ...deliverables];
    if (allEntities.length === 0) return;
    let maxMonth = 24;
    allEntities.forEach((entity) => {
      if (entity.end_month && entity.end_month > maxMonth) maxMonth = entity.end_month;
      if (entity.due_month && entity.due_month > maxMonth) maxMonth = entity.due_month;
    });
    // Round up to nearest 6
    const rounded = Math.ceil(maxMonth / 6) * 6;
    setHorizon(Math.max(12, rounded));
  }, [wps, tasks, milestones, deliverables]);

  const rows = useMemo<TimelineRow[]>(() => {
    const taskByWp = new Map<string, WorkEntity[]>();
    tasks.forEach((task) => {
      const list = taskByWp.get(task.wp_id || "") || [];
      list.push(task);
      taskByWp.set(task.wp_id || "", list);
    });
    const result: TimelineRow[] = [];
    wps.forEach((wp) => {
      result.push({
        id: wp.id,
        code: wp.code,
        title: wp.title,
        kind: "wp",
        wpId: null,
        startMonth: wp.start_month ?? 1,
        endMonth: wp.end_month ?? 1,
        dueMonth: wp.due_month,
        executionStatus: wp.execution_status,
      });
      (taskByWp.get(wp.id) || []).forEach((task) => {
        result.push({
          id: task.id,
          code: task.code,
          title: task.title,
          kind: "task",
          wpId: task.wp_id,
          startMonth: task.start_month ?? 1,
          endMonth: task.end_month ?? 1,
          dueMonth: task.due_month,
          executionStatus: task.execution_status,
        });
      });
    });
    return result;
  }, [wps, tasks]);

  const milestoneMarkers = useMemo(() => {
    return milestones
      .filter((ms) => ms.due_month != null)
      .map((ms) => ({
        id: ms.id,
        code: ms.code,
        title: ms.title,
        dueMonth: ms.due_month as number,
      }));
  }, [milestones]);

  const deliverableMarkers = useMemo(() => {
    return deliverables
      .filter((d) => d.due_month != null)
      .map((d) => ({
        id: d.id,
        code: d.code,
        title: d.title,
        dueMonth: d.due_month as number,
      }));
  }, [deliverables]);

  const validationWarnings = useMemo(() => {
    const warnings: string[] = [];
    const wpRangeById: Record<string, { start: number; end: number }> = {};
    wps.forEach((wp) => {
      if (wp.start_month != null && wp.end_month != null) {
        wpRangeById[wp.id] = { start: wp.start_month, end: wp.end_month };
      }
    });
    tasks.forEach((task) => {
      const wpId = task.wp_id || "";
      const wpRange = wpRangeById[wpId];
      if (!wpRange || task.start_month == null || task.end_month == null) return;
      const wpCode = wps.find((wp) => wp.id === wpId)?.code || "WP";
      if (task.end_month > wpRange.end) {
        warnings.push(`${task.code} ends after ${wpCode} (M${task.end_month} > M${wpRange.end})`);
      }
      if (task.start_month < wpRange.start) {
        warnings.push(`${task.code} starts before ${wpCode} (M${task.start_month} < M${wpRange.start})`);
      }
    });
    return warnings;
  }, [tasks, wps]);

  useEffect(() => {
    if (!selectedProjectId) {
      setWps([]);
      setTasks([]);
      setMilestones([]);
      setDeliverables([]);
      return;
    }
    loadData();
  }, [selectedProjectId, loadData]);

  function barStyle(startMonth: number, endMonth: number): { left: string; width: string } {
    const left = ((startMonth - 1) / horizon) * 100;
    const width = ((endMonth - startMonth + 1) / horizon) * 100;
    return { left: `${left}%`, width: `${Math.max(width, 100 / horizon)}%` };
  }

  function markerPosition(dueMonth: number): string {
    return `${((dueMonth - 0.5) / horizon) * 100}%`;
  }

  function verticalMarkerPosition(month: number): string {
    return `${(month / horizon) * 100}%`;
  }

  if (!selectedProjectId) {
    return (
      <section className="panel">
        <p className="muted-small">Select a project.</p>
      </section>
    );
  }

  return (
    <section className="panel timeline-panel">
      {error ? <p className="error">{error}</p> : null}

      <div className="timeline-toolbar">
        <div className="timeline-stats">
          <span>{wps.length} WPs</span>
          <span className="timeline-stat-sep" />
          <span>{tasks.length} Tasks</span>
          <span className="timeline-stat-sep" />
          <span>{milestoneMarkers.length} Milestones</span>
          <span className="timeline-stat-sep" />
          <span>{deliverableMarkers.length} Deliverables</span>
          {nowMonth ? (
            <>
              <span className="timeline-stat-sep" />
              <span>Now {`M${nowMonth}`}</span>
            </>
          ) : null}
        </div>
        <label className="timeline-horizon-picker">
          Horizon
          <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
            <option value={12}>12m</option>
            <option value={24}>24m</option>
            <option value={36}>36m</option>
            <option value={48}>48m</option>
            <option value={60}>60m</option>
          </select>
        </label>
      </div>

      {validationWarnings.length > 0 ? (
        <div className="timeline-warnings">
          {validationWarnings.map((warning) => (
            <span key={warning} className="timeline-warning-chip">{warning}</span>
          ))}
        </div>
      ) : null}

      <div className="timeline-board">
        <div className="timeline-header">
          <div className="timeline-label-col timeline-header-label">Entity</div>
          <div className="timeline-months">
            {months.map((month) => (
              <div key={month} className={`timeline-month ${month % 6 === 0 ? "period-end" : ""}`}>
                {month % 3 === 1 || horizon <= 24 ? `M${month}` : ""}
              </div>
            ))}
            {reportingMarkers
              .filter((item) => item.month <= horizon)
              .map((item) => (
                <span
                  key={`reporting-header-${item.date}`}
                  className="timeline-vertical-marker reporting"
                  style={{ left: verticalMarkerPosition(item.month) }}
                  title={`Report ${item.date} (M${item.month})`}
                />
              ))}
            {nowMonth && nowMonth <= horizon ? (
              <span
                className="timeline-vertical-marker now"
                style={{ left: verticalMarkerPosition(nowMonth) }}
                title={`Now (M${nowMonth})`}
              />
            ) : null}
          </div>
        </div>
        <div className="timeline-body">
          {rows.map((row) => {
            const style = barStyle(row.startMonth, row.endMonth);
            const isOverdue = nowMonth !== null && row.endMonth < nowMonth && row.executionStatus !== "closed";
            return (
              <div key={row.id} className={`timeline-row ${row.kind} ${isOverdue ? "overdue" : ""}`}>
                <div className="timeline-label-col">
                  <div className="timeline-label-main">
                    <strong>{row.code}</strong>
                    <span>{row.title}</span>
                  </div>
                  <span className="timeline-label-range">
                    M{row.startMonth}{row.endMonth !== row.startMonth ? ` - M${row.endMonth}` : ""}
                  </span>
                </div>
                <div className="timeline-track">
                  <div className="timeline-grid">
                    {months.map((month) => (
                      <span key={`${row.id}-${month}`} className={`timeline-grid-cell ${month % 6 === 0 ? "period-end" : ""}`} />
                    ))}
                  </div>
                  {reportingMarkers
                    .filter((item) => item.month <= horizon)
                    .map((item) => (
                      <span
                        key={`${row.id}-report-${item.date}`}
                        className="timeline-vertical-marker reporting"
                        style={{ left: verticalMarkerPosition(item.month) }}
                        title={`Report ${item.date} (M${item.month})`}
                      />
                    ))}
                  {nowMonth && nowMonth <= horizon ? (
                    <span
                      className="timeline-vertical-marker now"
                      style={{ left: verticalMarkerPosition(nowMonth) }}
                      title={`Now (M${nowMonth})`}
                    />
                  ) : null}
                  <div
                    className={`timeline-bar ${row.kind}`}
                    style={style}
                    title={`${row.code}: M${row.startMonth} - M${row.endMonth}`}
                  >
                    {row.kind === "wp" ? row.code : ""}
                  </div>
                </div>
              </div>
            );
          })}

          {(milestoneMarkers.length > 0 || deliverableMarkers.length > 0) ? (
            <div className="timeline-row markers">
              <div className="timeline-label-col">
                <div className="timeline-label-main">
                  <strong>Milestones & Deliverables</strong>
                </div>
              </div>
              <div className="timeline-track timeline-marker-track">
                <div className="timeline-grid">
                  {months.map((month) => (
                    <span key={`marker-${month}`} className={`timeline-grid-cell ${month % 6 === 0 ? "period-end" : ""}`} />
                  ))}
                </div>
                {reportingMarkers
                  .filter((item) => item.month <= horizon)
                  .map((item) => (
                    <span
                      key={`marker-report-${item.date}`}
                      className="timeline-vertical-marker reporting"
                      style={{ left: verticalMarkerPosition(item.month) }}
                      title={`Report ${item.date} (M${item.month})`}
                    />
                  ))}
                {nowMonth && nowMonth <= horizon ? (
                  <span
                    className="timeline-vertical-marker now"
                    style={{ left: verticalMarkerPosition(nowMonth) }}
                    title={`Now (M${nowMonth})`}
                  />
                ) : null}
                {milestoneMarkers.map((ms) => (
                  <div
                    key={ms.id}
                    className="timeline-marker milestone"
                    style={{ left: markerPosition(ms.dueMonth) }}
                    title={`${ms.code}: ${ms.title} (M${ms.dueMonth})`}
                  >
                    <span className="timeline-marker-diamond" />
                    <span className="timeline-marker-label">{ms.code}</span>
                  </div>
                ))}
                {deliverableMarkers.map((d) => (
                  <div
                    key={d.id}
                    className="timeline-marker deliverable"
                    style={{ left: markerPosition(d.dueMonth) }}
                    title={`${d.code}: ${d.title} (M${d.dueMonth})`}
                  >
                    <span className="timeline-marker-circle" />
                    <span className="timeline-marker-label">{d.code}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {!busy && rows.length === 0 ? (
            <div className="timeline-empty empty-state-card">
              No work packages or tasks defined yet.
              {onNavigate ? <button type="button" className="ghost" onClick={onNavigate} style={{ marginTop: 8 }}>Go to Setup</button> : null}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
