import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import type { ProposalCallLibraryEntry, ProposalTemplate, ProposalTemplateSection } from "../types";

export function ProposalTemplateEditor() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [templates, setTemplates] = useState<ProposalTemplate[]>([]);
  const [calls, setCalls] = useState<ProposalCallLibraryEntry[]>([]);
  const [callLibraryEntryId, setCallLibraryEntryId] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [name, setName] = useState("");
  const [fundingProgram, setFundingProgram] = useState("");
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [sectionKey, setSectionKey] = useState("");
  const [sectionTitle, setSectionTitle] = useState("");
  const [sectionGuidance, setSectionGuidance] = useState("");
  const [sectionPosition, setSectionPosition] = useState(1);
  const [sectionRequired, setSectionRequired] = useState(true);
  const [sectionScopeHint, setSectionScopeHint] = useState("project");
  const [editingSectionId, setEditingSectionId] = useState("");

  useEffect(() => {
    void loadTemplates();
    api.listProposalCallLibrary("", true)
      .then((res) => setCalls(res.items))
      .catch(() => setCalls([]));
  }, []);

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.id === selectedTemplateId) || null,
    [templates, selectedTemplateId]
  );

  useEffect(() => {
    if (!selectedTemplate) {
      setName("");
      setFundingProgram("");
      setDescription("");
      setIsActive(true);
      setEditingSectionId("");
      return;
    }
    setName(selectedTemplate.name);
    setCallLibraryEntryId(selectedTemplate.call_library_entry_id || "");
    setFundingProgram(selectedTemplate.funding_program);
    setDescription(selectedTemplate.description || "");
    setIsActive(selectedTemplate.is_active);
    setEditingSectionId("");
  }, [selectedTemplate]);

  async function loadTemplates() {
    try {
      const response = await api.listProposalTemplates();
      setTemplates(response.items);
      setSelectedTemplateId((current) => current || response.items[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load templates.");
    }
  }

  async function handleCreateTemplate() {
    try {
      setBusy(true);
      setError("");
      const created = await api.createProposalTemplate({
        call_library_entry_id: callLibraryEntryId || null,
        name,
        funding_program: fundingProgram,
        description: description || null,
        is_active: isActive,
      });
      setTemplates((prev) => [...prev, created]);
      setSelectedTemplateId(created.id);
      setStatus("Template created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create template.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveTemplate() {
    if (!selectedTemplateId) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.updateProposalTemplate(selectedTemplateId, {
        call_library_entry_id: callLibraryEntryId || null,
        name,
        funding_program: fundingProgram,
        description: description || null,
        is_active: isActive,
      });
      setTemplates((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setStatus("Template saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save template.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateSection() {
    if (!selectedTemplateId) return;
    try {
      setBusy(true);
      setError("");
      const payload = {
        key: sectionKey,
        title: sectionTitle,
        guidance: sectionGuidance || null,
        position: sectionPosition,
        required: sectionRequired,
        scope_hint: sectionScopeHint,
      };
      const updated = editingSectionId
        ? await api.updateProposalTemplateSection(selectedTemplateId, editingSectionId, payload)
        : await api.createProposalTemplateSection(selectedTemplateId, payload);
      setTemplates((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSectionKey("");
      setSectionTitle("");
      setSectionGuidance("");
      setSectionPosition(((updated.sections[updated.sections.length - 1]?.position) || 0) + 1 || 1);
      setSectionRequired(true);
      setSectionScopeHint("project");
      setEditingSectionId("");
      setStatus(editingSectionId ? "Section saved." : "Section added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save section.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteSection(section: ProposalTemplateSection) {
    if (!selectedTemplateId) return;
    try {
      setBusy(true);
      setError("");
      const updated = await api.deleteProposalTemplateSection(selectedTemplateId, section.id);
      setTemplates((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setStatus("Section deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete section.");
    } finally {
      setBusy(false);
    }
  }

  function startEditSection(section: ProposalTemplateSection) {
    setEditingSectionId(section.id);
    setSectionKey(section.key);
    setSectionTitle(section.title);
    setSectionGuidance(section.guidance || "");
    setSectionPosition(section.position);
    setSectionRequired(section.required);
    setSectionScopeHint(section.scope_hint);
  }

  function resetSectionForm() {
    setEditingSectionId("");
    setSectionKey("");
    setSectionTitle("");
    setSectionGuidance("");
    setSectionPosition(1);
    setSectionRequired(true);
    setSectionScopeHint("project");
  }

  return (
    <section className="panel">
      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success">{status}</p> : null}

      <div className="settings-layout">
        <div className="card">
          <div className="row-actions">
            <button
              type="button"
              onClick={() => {
                setSelectedTemplateId("");
                setCallLibraryEntryId("");
                setName("");
                setFundingProgram("");
                setDescription("");
                setIsActive(true);
              }}
            >
              New Template
            </button>
          </div>
          <div className="review-list">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                className={`app-nav-item ${template.id === selectedTemplateId ? "active" : ""}`}
                onClick={() => setSelectedTemplateId(template.id)}
              >
                <span className="app-nav-label">{template.funding_program} · {template.name}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="form-grid">
            <label>
              Call
              <select value={callLibraryEntryId} onChange={(event) => setCallLibraryEntryId(event.target.value)}>
                <option value="">None</option>
                {calls.map((item) => (
                  <option key={item.id} value={item.id}>{item.call_title}</option>
                ))}
              </select>
            </label>
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label>
              Funding Program
              <input value={fundingProgram} onChange={(event) => setFundingProgram(event.target.value)} />
            </label>
            <label className="wide">
              Description
              <textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              <span>Active</span>
            </label>
          </div>
          <div className="row-actions">
            {selectedTemplateId ? (
              <button type="button" disabled={busy || !name || !fundingProgram || !callLibraryEntryId} onClick={() => void handleSaveTemplate()}>
                Save Template
              </button>
            ) : (
              <button type="button" disabled={busy || !name || !fundingProgram || !callLibraryEntryId} onClick={() => void handleCreateTemplate()}>
                Create Template
              </button>
            )}
          </div>

          {selectedTemplate ? (
            <>
              <div className="form-grid">
                <label>
                  Key
                  <input value={sectionKey} onChange={(event) => setSectionKey(event.target.value)} />
                </label>
                <label>
                  Title
                  <input value={sectionTitle} onChange={(event) => setSectionTitle(event.target.value)} />
                </label>
                <label>
                  Position
                  <input
                    type="number"
                    min={1}
                    value={sectionPosition}
                    onChange={(event) => setSectionPosition(Number(event.target.value) || 1)}
                  />
                </label>
                <label>
                  Scope
                  <select value={sectionScopeHint} onChange={(event) => setSectionScopeHint(event.target.value)}>
                    <option value="project">Project</option>
                    <option value="wp">WP</option>
                    <option value="task">Task</option>
                    <option value="deliverable">Deliverable</option>
                    <option value="milestone">Milestone</option>
                  </select>
                </label>
                <label className="wide">
                  Guidance
                  <textarea rows={2} value={sectionGuidance} onChange={(event) => setSectionGuidance(event.target.value)} />
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" checked={sectionRequired} onChange={(event) => setSectionRequired(event.target.checked)} />
                  <span>Required</span>
                </label>
              </div>
              <div className="row-actions">
                <button
                  type="button"
                  disabled={busy || !sectionKey || !sectionTitle}
                  onClick={() => void handleCreateSection()}
                >
                  {editingSectionId ? "Save Section" : "Add Section"}
                </button>
                {editingSectionId ? (
                  <button type="button" className="ghost" onClick={resetSectionForm}>
                    Cancel
                  </button>
                ) : null}
              </div>

              <div className="simple-table-wrap">
                <table className="simple-table compact-table">
                  <thead>
                    <tr>
                      <th>Pos</th>
                      <th>Key</th>
                      <th>Title</th>
                      <th>Scope</th>
                      <th>Required</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedTemplate.sections.map((section) => (
                      <tr key={section.id}>
                        <td>{section.position}</td>
                        <td>{section.key}</td>
                        <td>{section.title}</td>
                        <td>{section.scope_hint}</td>
                        <td>{section.required ? "Yes" : "No"}</td>
                        <td>
                          <button type="button" className="ghost" onClick={() => startEditSection(section)}>
                            Edit
                          </button>
                          <button type="button" className="ghost" onClick={() => void handleDeleteSection(section)}>
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                    {selectedTemplate.sections.length === 0 ? (
                      <tr>
                        <td colSpan={6}>No sections defined.</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
