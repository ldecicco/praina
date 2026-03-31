import { useEffect, useMemo, useState } from "react";
import FocusLock from "react-focus-lock";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faChevronDown,
  faPlus,
  faShieldHalved,
  faTriangleExclamation,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { currentProjectMonth } from "../lib/utils";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import { useStatusToast } from "../lib/useStatusToast";
import type { Member, Partner, Project, ProjectRisk, WorkEntity } from "../types";
import { ProjectActivityFeed } from "./ProjectActivityFeed";

type Props = {
  selectedProjectId: string;
  project: Project | null;
};

const DELIVERABLE_STATUS_OPTIONS = ["draft", "in_review", "changes_requested", "approved", "submitted"];
const RISK_STATUS_OPTIONS = ["open", "monitoring", "mitigated", "closed"];
const RISK_LEVEL_OPTIONS = ["low", "medium", "high", "critical"];

type Tab = "deliverables" | "risks" | "activity";

function pressureClass(currentMonth: number | null, reviewDueMonth: number | null, dueMonth: number | null): string {
  const anchor = reviewDueMonth ?? dueMonth;
  if (!currentMonth || !anchor) return "normal";
  if (anchor < currentMonth) return "late";
  if (anchor <= currentMonth + 1) return "soon";
  return "normal";
}

function pressureLabel(currentMonth: number | null, reviewDueMonth: number | null, dueMonth: number | null): string {
  const anchor = reviewDueMonth ?? dueMonth;
  if (!anchor) return "-";
  if (!currentMonth) return `M${anchor}`;
  if (anchor < currentMonth) return "Late";
  if (anchor <= currentMonth + 1) return "Soon";
  return `M${anchor}`;
}

export function DeliveryBoard({ selectedProjectId, project }: Props) {
  const [busy, setBusy] = useState(false);
  const { error, setError, status, setStatus } = useStatusToast();
  const [partners, setPartners] = useState<Partner[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [deliverables, setDeliverables] = useState<WorkEntity[]>([]);
  const [risks, setRisks] = useState<ProjectRisk[]>([]);
  const [tab, setTab] = useState<Tab>("deliverables");
  const [riskModalOpen, setRiskModalOpen] = useState(false);
  const [editingRiskId, setEditingRiskId] = useState<string | null>(null);
  const [riskFilterStatus, setRiskFilterStatus] = useState("all");
  const [riskFilterPartnerId, setRiskFilterPartnerId] = useState("all");
  const [riskCode, setRiskCode] = useState("");
  const [riskTitle, setRiskTitle] = useState("");
  const [riskDescription, setRiskDescription] = useState("");
  const [riskMitigation, setRiskMitigation] = useState("");
  const [riskStatus, setRiskStatus] = useState("open");
  const [riskProbability, setRiskProbability] = useState("medium");
  const [riskImpact, setRiskImpact] = useState("medium");
  const [riskDueMonth, setRiskDueMonth] = useState("");
  const [riskOwnerPartnerId, setRiskOwnerPartnerId] = useState("");
  const [riskOwnerMemberId, setRiskOwnerMemberId] = useState("");
  const [activityOpen, setActivityOpen] = useState(false);

  useAutoRefresh(() => { void loadData(); });

  const membersByPartner = useMemo(() => {
    const map: Record<string, Member[]> = {};
    members.forEach((member) => {
      if (!map[member.partner_id]) map[member.partner_id] = [];
      map[member.partner_id].push(member);
    });
    return map;
  }, [members]);

  const partnerNameById = useMemo(() => Object.fromEntries(partners.map((item) => [item.id, item.short_name])), [partners]);
  const memberNameById = useMemo(() => Object.fromEntries(members.map((item) => [item.id, item.full_name])), [members]);
  const projectMonth = useMemo(() => currentProjectMonth(project?.start_date), [project?.start_date]);
  const workflowCounts = useMemo(() => {
    const counts = Object.fromEntries(DELIVERABLE_STATUS_OPTIONS.map((option) => [option, 0])) as Record<string, number>;
    deliverables.forEach((item) => {
      counts[item.workflow_status || "draft"] = (counts[item.workflow_status || "draft"] || 0) + 1;
    });
    return counts;
  }, [deliverables]);
  const filteredRisks = useMemo(
    () =>
      risks.filter((item) => {
        if (riskFilterStatus !== "all" && item.status !== riskFilterStatus) return false;
        if (riskFilterPartnerId !== "all" && item.owner_partner_id !== riskFilterPartnerId) return false;
        return true;
      }),
    [riskFilterPartnerId, riskFilterStatus, risks]
  );
  const highRiskCount = useMemo(
    () => risks.filter((item) => ["high", "critical"].includes(item.probability) || ["high", "critical"].includes(item.impact)).length,
    [risks]
  );
  const openRiskCount = useMemo(() => risks.filter((item) => item.status !== "closed").length, [risks]);

  useEffect(() => {
    if (!selectedProjectId) {
      setPartners([]);
      setMembers([]);
      setDeliverables([]);
      setRisks([]);
      return;
    }
    void loadData();
  }, [selectedProjectId]);

  async function loadData() {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const [partnersRes, membersRes, deliverablesRes, risksRes] = await Promise.all([
        api.listPartners(selectedProjectId),
        api.listMembers(selectedProjectId),
        api.listDeliverables(selectedProjectId),
        api.listRisks(selectedProjectId),
      ]);
      setPartners(partnersRes.items);
      setMembers(membersRes.items);
      setDeliverables(deliverablesRes.items);
      setRisks(risksRes.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load delivery data.");
    } finally {
      setBusy(false);
    }
  }

  async function handleWorkflowChange(deliverable: WorkEntity, workflowStatus: string) {
    await updateDeliverable(deliverable, { workflow_status: workflowStatus });
  }

  async function updateDeliverable(
    deliverable: WorkEntity,
    patch: { workflow_status?: string; review_due_month?: number; review_owner_member_id?: string | null }
  ) {
    if (!selectedProjectId) return;
    try {
      setError("");
      const updated = await api.updateDeliverable(selectedProjectId, deliverable.id, {
        code: deliverable.code,
        title: deliverable.title,
        description: deliverable.description || undefined,
        due_month: deliverable.due_month || 1,
        wp_ids: deliverable.wp_ids,
        workflow_status: patch.workflow_status ?? deliverable.workflow_status ?? "draft",
        review_due_month:
          Object.prototype.hasOwnProperty.call(patch, "review_due_month")
            ? patch.review_due_month
            : (deliverable.review_due_month ?? undefined),
        review_owner_member_id:
          Object.prototype.hasOwnProperty.call(patch, "review_owner_member_id")
            ? patch.review_owner_member_id || undefined
            : (deliverable.review_owner_member_id ?? undefined),
        assignment: {
          leader_organization_id: deliverable.leader_organization_id,
          responsible_person_id: deliverable.responsible_person_id,
          collaborating_partner_ids: deliverable.collaborating_partner_ids,
        },
      });
      setDeliverables((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setStatus(`Updated ${updated.code}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update deliverable.");
    }
  }

  function openNewRisk() {
    setEditingRiskId(null);
    setRiskCode("");
    setRiskTitle("");
    setRiskDescription("");
    setRiskMitigation("");
    setRiskStatus("open");
    setRiskProbability("medium");
    setRiskImpact("medium");
    setRiskDueMonth("");
    setRiskOwnerPartnerId(partners[0]?.id || "");
    setRiskOwnerMemberId("");
    setRiskModalOpen(true);
  }

  function openEditRisk(risk: ProjectRisk) {
    setEditingRiskId(risk.id);
    setRiskCode(risk.code);
    setRiskTitle(risk.title);
    setRiskDescription(risk.description || "");
    setRiskMitigation(risk.mitigation_plan || "");
    setRiskStatus(risk.status);
    setRiskProbability(risk.probability);
    setRiskImpact(risk.impact);
    setRiskDueMonth(risk.due_month ? String(risk.due_month) : "");
    setRiskOwnerPartnerId(risk.owner_partner_id);
    setRiskOwnerMemberId(risk.owner_member_id);
    setRiskModalOpen(true);
  }

  async function handleSaveRisk() {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      const payload = {
        code: riskCode,
        title: riskTitle,
        description: riskDescription || undefined,
        mitigation_plan: riskMitigation || undefined,
        status: riskStatus,
        probability: riskProbability,
        impact: riskImpact,
        due_month: riskDueMonth ? Number(riskDueMonth) : undefined,
        owner_partner_id: riskOwnerPartnerId,
        owner_member_id: riskOwnerMemberId,
      };
      const saved = editingRiskId
        ? await api.updateRisk(selectedProjectId, editingRiskId, payload)
        : await api.createRisk(selectedProjectId, payload);
      setRisks((prev) => {
        const index = prev.findIndex((item) => item.id === saved.id);
        if (index >= 0) {
          const next = [...prev];
          next[index] = saved;
          return next;
        }
        return [saved, ...prev];
      });
      setRiskModalOpen(false);
      setStatus(`${saved.code} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save risk.");
    } finally {
      setBusy(false);
    }
  }

  if (!selectedProjectId) {
    return (
      <section className="panel">
        <div className="dashboard-empty"><strong>Select a project</strong></div>
      </section>
    );
  }

  return (
    <section className="panel delivery-page">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      {/* Summary bar */}
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span>{deliverables.length} deliverables</span>
          <span className="setup-summary-sep" />
          <span>{openRiskCount} open risks</span>
          <span className="setup-summary-sep" />
          <span className={highRiskCount > 0 ? "docs-failed-count" : ""}>{highRiskCount} high/critical</span>
          {projectMonth ? (
            <>
              <span className="setup-summary-sep" />
              <span>M{projectMonth}</span>
            </>
          ) : null}
        </div>
      </div>

      {/* Tab bar */}
      <div className="delivery-tabs">
        <button type="button" className={`delivery-tab ${tab === "deliverables" ? "active" : ""}`} onClick={() => setTab("deliverables")}>
          Deliverables
          <span className="delivery-tab-count">{deliverables.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "risks" ? "active" : ""}`} onClick={() => setTab("risks")}>
          <FontAwesomeIcon icon={faShieldHalved} />
          Risks
          <span className="delivery-tab-count">{risks.length}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "activity" ? "active" : ""}`} onClick={() => setTab("activity")}>
          Activity
        </button>

        {/* Right-side actions */}
        {tab === "risks" ? (
          <button type="button" className="meetings-new-btn delivery-tab-action" onClick={openNewRisk}>
            <FontAwesomeIcon icon={faPlus} /> New Risk
          </button>
        ) : null}
      </div>

      {/* Deliverables tab */}
      {tab === "deliverables" ? (
        <>
          <div className="delivery-status-strip">
            {DELIVERABLE_STATUS_OPTIONS.map((option) => (
              <div key={option} className="delivery-status-chip">
                <span>{option.split("_").join(" ")}</span>
                <strong>{workflowCounts[option] || 0}</strong>
              </div>
            ))}
          </div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Due</th>
                  <th>Review</th>
                  <th>WPs</th>
                  <th>Owner</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {deliverables.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.code}</strong></td>
                    <td>{item.title}</td>
                    <td>{item.due_month ? `M${item.due_month}` : "-"}</td>
                    <td>
                      <div className={`delivery-review-inline ${pressureClass(projectMonth, item.review_due_month, item.due_month)}`}>
                        <span className="delivery-review-pressure">{pressureLabel(projectMonth, item.review_due_month, item.due_month)}</span>
                        <select
                          value={item.review_owner_member_id || ""}
                          onChange={(event) =>
                            void updateDeliverable(item, {
                              review_owner_member_id: event.target.value || null,
                            })
                          }
                        >
                          <option value="">No reviewer</option>
                          {members.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.full_name}
                            </option>
                          ))}
                        </select>
                        <input
                          type="number"
                          min={1}
                          max={item.due_month || 120}
                          defaultValue={item.review_due_month || ""}
                          placeholder="M"
                          className="delivery-review-month"
                          onBlur={(event) => {
                            const value = event.target.value.trim();
                            void updateDeliverable(item, {
                              review_due_month: value ? Number(value) : undefined,
                            });
                          }}
                        />
                      </div>
                    </td>
                    <td>{item.wp_ids.length}</td>
                    <td>{partnerNameById[item.leader_organization_id] || "-"}</td>
                    <td>
                      <select
                        value={item.workflow_status || "draft"}
                        onChange={(event) => void handleWorkflowChange(item, event.target.value)}
                      >
                        {DELIVERABLE_STATUS_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
                {deliverables.length === 0 ? (
                  <tr><td colSpan={7} className="empty-state-card">No deliverables yet. Use the Setup wizard to define your work plan.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {/* Risks tab */}
      {tab === "risks" ? (
        <>
          <div className="meetings-toolbar">
            <div className="meetings-filter-group">
              <select value={riskFilterStatus} onChange={(event) => setRiskFilterStatus(event.target.value)}>
                <option value="all">All statuses</option>
                {RISK_STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
              <select value={riskFilterPartnerId} onChange={(event) => setRiskFilterPartnerId(event.target.value)}>
                <option value="all">All partners</option>
                {partners.map((partner) => (
                  <option key={partner.id} value={partner.id}>{partner.short_name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead>
                <tr>
                  <th style={{ width: 28 }}></th>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Prob / Impact</th>
                  <th>Due</th>
                  <th>Owner</th>
                </tr>
              </thead>
              <tbody>
                {filteredRisks.map((item) => {
                  const isHighOrCritical = ["high", "critical"].includes(item.probability) || ["high", "critical"].includes(item.impact);
                  return (
                    <tr key={item.id} onDoubleClick={() => openEditRisk(item)}>
                      <td>
                        <span className={`meetings-source-icon ${isHighOrCritical ? "transcript" : ""}`} style={isHighOrCritical ? { background: "rgba(232,93,93,0.1)", color: "#e85d5d" } : {}}>
                          <FontAwesomeIcon icon={isHighOrCritical ? faTriangleExclamation : faShieldHalved} />
                        </span>
                      </td>
                      <td><strong>{item.code}</strong></td>
                      <td>{item.title}</td>
                      <td><span className={`chip small ${item.status === "closed" ? "muted" : ""}`}>{item.status}</span></td>
                      <td>
                        <span className={`delivery-risk-level ${isHighOrCritical ? "high" : ""}`}>
                          {item.probability} / {item.impact}
                        </span>
                      </td>
                      <td>{item.due_month ? `M${item.due_month}` : "-"}</td>
                      <td>{partnerNameById[item.owner_partner_id] || memberNameById[item.owner_member_id] || "-"}</td>
                    </tr>
                  );
                })}
                {filteredRisks.length === 0 ? (
                  <tr><td colSpan={7} className="empty-state-card">No risks registered. Click "New Risk" to add one.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {/* Activity tab */}
      {tab === "activity" ? (
        <div className="delivery-activity-section">
          <ProjectActivityFeed projectId={selectedProjectId} limit={20} />
        </div>
      ) : null}

      {/* Risk modal */}
      {riskModalOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <FocusLock returnFocus>
          <div className="modal-card settings-modal-card" onKeyDown={(e) => { if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement) && !busy && riskCode.trim() && riskTitle.trim() && riskOwnerPartnerId && riskOwnerMemberId) { e.preventDefault(); void handleSaveRisk(); } }}>
            <div className="modal-head">
              <h3>{editingRiskId ? "Edit Risk" : "New Risk"}</h3>
              <button type="button" className="ghost docs-action-btn" onClick={() => setRiskModalOpen(false)} title="Close"><FontAwesomeIcon icon={faXmark} /></button>
            </div>
            <div className="form-grid">
              <label>
                Code
                <input value={riskCode} onChange={(event) => setRiskCode(event.target.value)} />
              </label>
              <label>
                Title
                <input value={riskTitle} onChange={(event) => setRiskTitle(event.target.value)} />
              </label>
              <label>
                Status
                <select value={riskStatus} onChange={(event) => setRiskStatus(event.target.value)}>
                  {RISK_STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
              <label>
                Due Month
                <input value={riskDueMonth} onChange={(event) => setRiskDueMonth(event.target.value)} />
              </label>
              <label>
                Probability
                <select value={riskProbability} onChange={(event) => setRiskProbability(event.target.value)}>
                  {RISK_LEVEL_OPTIONS.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
              <label>
                Impact
                <select value={riskImpact} onChange={(event) => setRiskImpact(event.target.value)}>
                  {RISK_LEVEL_OPTIONS.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
              <label>
                Owner Partner
                <select
                  value={riskOwnerPartnerId}
                  onChange={(event) => {
                    setRiskOwnerPartnerId(event.target.value);
                    setRiskOwnerMemberId("");
                  }}
                >
                  <option value="">Select partner</option>
                  {partners.map((partner) => (
                    <option key={partner.id} value={partner.id}>{partner.short_name}</option>
                  ))}
                </select>
              </label>
              <label>
                Owner Member
                <select value={riskOwnerMemberId} onChange={(event) => setRiskOwnerMemberId(event.target.value)}>
                  <option value="">Select member</option>
                  {(membersByPartner[riskOwnerPartnerId] || []).map((member) => (
                    <option key={member.id} value={member.id}>{member.full_name}</option>
                  ))}
                </select>
              </label>
              <label className="full-span">
                Description
                <textarea rows={4} value={riskDescription} onChange={(event) => setRiskDescription(event.target.value)} />
              </label>
              <label className="full-span">
                Mitigation
                <textarea rows={4} value={riskMitigation} onChange={(event) => setRiskMitigation(event.target.value)} />
              </label>
            </div>
            <div className="row-actions">
              <button
                type="button"
                disabled={busy || !riskCode.trim() || !riskTitle.trim() || !riskOwnerPartnerId || !riskOwnerMemberId}
                onClick={() => void handleSaveRisk()}
              >
                Save
              </button>
            </div>
          </div>
          </FocusLock>
        </div>
      ) : null}
    </section>
  );
}
