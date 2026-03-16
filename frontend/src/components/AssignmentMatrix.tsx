import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import type { AssignmentMatrixRow, Member, Partner } from "../types";

type Props = {
  selectedProjectId: string;
};

type EntityTypeFilter = "" | "work_package" | "task" | "milestone" | "deliverable";

export function AssignmentMatrix({ selectedProjectId }: Props) {
  const [entityType, setEntityType] = useState<EntityTypeFilter>("");
  const [rows, setRows] = useState<AssignmentMatrixRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [editingRowId, setEditingRowId] = useState<string | null>(null);
  const [leaderOrgId, setLeaderOrgId] = useState("");
  const [responsiblePersonId, setResponsiblePersonId] = useState("");
  const [collabPartnerIds, setCollabPartnerIds] = useState<string[]>([]);

  const membersForLeader = useMemo(
    () => members.filter((member) => member.partner_id === leaderOrgId),
    [members, leaderOrgId]
  );
  const partnerNameById = useMemo(
    () => Object.fromEntries(partners.map((partner) => [partner.id, partner.short_name])),
    [partners]
  );
  const memberNameById = useMemo(
    () => Object.fromEntries(members.map((member) => [member.id, member.full_name])),
    [members]
  );

  useAutoRefresh(() => { if (selectedProjectId) void loadData(selectedProjectId, entityType); });

  async function loadData(projectId: string, currentEntityType: EntityTypeFilter) {
    setBusy(true);
    setError("");
    try {
      const [partnersRes, membersRes, matrixRes] = await Promise.all([
        api.listPartners(projectId),
        api.listMembers(projectId),
        api.listAssignmentMatrix(projectId, currentEntityType || undefined),
      ]);
      setPartners(partnersRes.items);
      setMembers(membersRes.items);
      setRows(matrixRes.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load assignment matrix.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!selectedProjectId) {
      setRows([]);
      setPartners([]);
      setMembers([]);
      return;
    }
    void loadData(selectedProjectId, entityType);
  }, [selectedProjectId, entityType]);

  function startEditing(row: AssignmentMatrixRow) {
    setEditingRowId(row.entity_id);
    setLeaderOrgId(row.leader_organization_id);
    setResponsiblePersonId(row.responsible_person_id);
    setCollabPartnerIds(row.collaborating_partner_ids);
    setStatus("");
    setError("");
  }

  async function saveAssignment(row: AssignmentMatrixRow) {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      setError("");
      await api.updateAssignment(selectedProjectId, row, {
        leader_organization_id: leaderOrgId,
        responsible_person_id: responsiblePersonId,
        collaborating_partner_ids: collabPartnerIds,
      });
      await loadData(selectedProjectId, entityType);
      setEditingRowId(null);
      setStatus(`Updated assignment for ${row.code}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update assignment.");
    } finally {
      setBusy(false);
    }
  }

  if (!selectedProjectId) {
    return (
      <section className="panel">
        <p className="muted-small">Select a project to start.</p>
      </section>
    );
  }

  return (
    <section className="panel">

      <div className="kpi-row">
        <article className="kpi-card">
          <span className="kpi-label">Rows</span>
          <strong className="kpi-value">{rows.length}</strong>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Partners</span>
          <strong className="kpi-value">{partners.length}</strong>
        </article>
        <article className="kpi-card">
          <span className="kpi-label">Members</span>
          <strong className="kpi-value">{members.length}</strong>
        </article>
      </div>

      <div className="filters">
        <label>
          Entity Type
          <select value={entityType} onChange={(e) => setEntityType(e.target.value as EntityTypeFilter)}>
            <option value="">All</option>
            <option value="work_package">Work Packages</option>
            <option value="task">Tasks</option>
            <option value="milestone">Milestones</option>
            <option value="deliverable">Deliverables</option>
          </select>
        </label>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Code</th>
              <th>Title</th>
              <th>Leader Partner</th>
              <th>Responsible</th>
              <th>Collaborators</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isEditing = editingRowId === row.entity_id;
              const entityLabel =
                row.entity_type === "work_package"
                  ? "WP"
                  : row.entity_type === "task"
                    ? "Task"
                    : row.entity_type === "milestone"
                      ? "Milestone"
                      : "Deliverable";
              return (
                <tr key={row.entity_id}>
                  <td>
                    <span className="chip">{entityLabel}</span>
                  </td>
                  <td>{row.code}</td>
                  <td>{row.title}</td>
                  <td>
                    {isEditing ? (
                      <select value={leaderOrgId} onChange={(e) => setLeaderOrgId(e.target.value)}>
                        <option value="">Select partner</option>
                        {partners.map((partner) => (
                          <option key={partner.id} value={partner.id}>
                            {partner.short_name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span>{partnerNameById[row.leader_organization_id] ?? row.leader_organization_id}</span>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <select value={responsiblePersonId} onChange={(e) => setResponsiblePersonId(e.target.value)}>
                        <option value="">Select member</option>
                        {membersForLeader.map((member) => (
                          <option key={member.id} value={member.id}>
                            {member.full_name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span>{memberNameById[row.responsible_person_id] ?? row.responsible_person_id}</span>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <select
                        multiple
                        value={collabPartnerIds}
                        onChange={(e) =>
                          setCollabPartnerIds(Array.from(e.target.selectedOptions).map((option) => option.value))
                        }
                      >
                        {partners.map((partner) => (
                          <option key={partner.id} value={partner.id}>
                            {partner.short_name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <div className="chips-row">
                        {row.collaborating_partner_ids.length === 0 ? (
                          <span className="muted-small">No collaborators</span>
                        ) : (
                          row.collaborating_partner_ids.map((partnerId) => (
                            <span key={partnerId} className="chip muted">
                              {partnerNameById[partnerId] ?? partnerId}
                            </span>
                          ))
                        )}
                      </div>
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <div className="action-group">
                        <button type="button" disabled={busy || !leaderOrgId || !responsiblePersonId} onClick={() => saveAssignment(row)}>
                          Save
                        </button>
                        <button type="button" className="ghost" onClick={() => setEditingRowId(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button type="button" onClick={() => startEditing(row)}>
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {!busy && rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-state-card">No assignments available for the current filter.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
