import { useCallback, useEffect, useMemo, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUpRightFromSquare,
  faBrain,
  faChevronDown,
  faChevronUp,
  faCircle,
  faComment,
  faGraduationCap,
  faMicrophone,
  faPaperclip,
  faPenToSquare,
  faPlus,
  faTrash,
  faWandMagicSparkles,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

import { api } from "../lib/api";
import { renderMarkdown } from "../lib/renderMarkdown";
import { ProjectResourcesPanel } from "./ProjectResourcesPanel";
import { ProposalRichEditor } from "./ProposalRichEditor";
import type {
  AuthUser,
  BibliographyReference,
  Course,
  CourseStaffUser,
  DocumentListItem,
  Member,
  Project,
  TeachingWorkspace,
} from "../types";
import { renderHealthIndicator } from "./TeachingHealthIndicator";

type Props = {
  selectedProjectId: string;
  project: Project | null;
  currentUser: AuthUser | null;
  onOpenAssistant: (prompt: string) => void;
};

type Tab = "overview" | "background" | "artifacts" | "progress" | "assessment";
type EntityModal =
  | "project"
  | "objectives"
  | "specifications"
  | "student"
  | "background"
  | "artifact"
  | "milestone"
  | "blocker"
  | "report"
  | null;
type AssessmentEditorTab = "strengths" | "weaknesses" | "rationale";
type ReportEditorTab = "work_done" | "next_steps" | "supervisor_feedback";
type OverviewDocTab = "objectives" | "specifications";
type ReportBlockerDraft = {
  id?: string;
  title: string;
  description: string;
  severity: string;
  status: string;
};

function toDateInput(value: string | null | undefined): string {
  if (!value) return "";
  return value.slice(0, 10);
}

function isOverdue(dueAt: string | null | undefined, status: string): boolean {
  if (!dueAt || status === "completed") return false;
  return new Date(dueAt) < new Date();
}

function modalTitle(modal: EntityModal, editingId: string | null): string {
  if (modal === "project") return "Edit Project";
  if (modal === "objectives") return "Edit Functional Objectives";
  if (modal === "specifications") return "Edit Specifications";
  if (modal === "background") return editingId ? "Edit Background" : "Add Background";
  return editingId ? "Edit" : "Add";
}

export function TeachingWorkspace({ selectedProjectId, project, currentUser, onOpenAssistant }: Props) {
  const [workspace, setWorkspace] = useState<TeachingWorkspace | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [assessmentEditorTab, setAssessmentEditorTab] = useState<AssessmentEditorTab>("strengths");
  const [reportEditorTab, setReportEditorTab] = useState<ReportEditorTab>("work_done");
  const [overviewDocTab, setOverviewDocTab] = useState<OverviewDocTab>("objectives");
  const [artifactTypeFilter, setArtifactTypeFilter] = useState("");
  const [artifactStatusFilter, setArtifactStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [modal, setModal] = useState<EntityModal>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedReports, setExpandedReports] = useState<Set<string>>(new Set());

  const [courseId, setCourseId] = useState("");
  const [academicYear, setAcademicYear] = useState("");
  const [term, setTerm] = useState("");
  const [responsibleUserId, setResponsibleUserId] = useState("");
  const [profileStatus, setProfileStatus] = useState("draft");
  const [health, setHealth] = useState("green");
  const [reportingCadenceDays, setReportingCadenceDays] = useState(14);
  const [functionalObjectives, setFunctionalObjectives] = useState("");
  const [specifications, setSpecifications] = useState("");
  const [finalGrade, setFinalGrade] = useState("");

  const [studentName, setStudentName] = useState("");
  const [studentEmail, setStudentEmail] = useState("");

  const [backgroundMaterialType, setBackgroundMaterialType] = useState("paper");
  const [backgroundMaterialTitle, setBackgroundMaterialTitle] = useState("");
  const [backgroundMaterialBibliographyId, setBackgroundMaterialBibliographyId] = useState("");
  const [backgroundMaterialDocumentKey, setBackgroundMaterialDocumentKey] = useState("");
  const [backgroundMaterialExternalUrl, setBackgroundMaterialExternalUrl] = useState("");
  const [backgroundMaterialNotes, setBackgroundMaterialNotes] = useState("");
  const [backgroundUploadFile, setBackgroundUploadFile] = useState<File | null>(null);
  const [backgroundUploading, setBackgroundUploading] = useState(false);
  const [bibliography, setBibliography] = useState<BibliographyReference[]>([]);

  const [artifactType, setArtifactType] = useState("report");
  const [artifactLabel, setArtifactLabel] = useState("");
  const [artifactRequired, setArtifactRequired] = useState(true);
  const [artifactStatus, setArtifactStatus] = useState("missing");
  const [artifactDocumentKey, setArtifactDocumentKey] = useState("");
  const [artifactExternalUrl, setArtifactExternalUrl] = useState("");
  const [artifactNotes, setArtifactNotes] = useState("");
  const [artifactUploadFile, setArtifactUploadFile] = useState<File | null>(null);
  const [artifactUploading, setArtifactUploading] = useState(false);

  const [milestoneKind, setMilestoneKind] = useState("");
  const [milestoneLabel, setMilestoneLabel] = useState("");
  const [milestoneDueAt, setMilestoneDueAt] = useState("");
  const [milestoneStatus, setMilestoneStatus] = useState("pending");

  const [blockerTitle, setBlockerTitle] = useState("");
  const [blockerDescription, setBlockerDescription] = useState("");
  const [blockerSeverity, setBlockerSeverity] = useState("medium");
  const [blockerStatus, setBlockerStatus] = useState("open");
  const [blockerDetectedFrom, setBlockerDetectedFrom] = useState("");

  const [reportDate, setReportDate] = useState("");
  const [reportMeetingDate, setReportMeetingDate] = useState("");
  const [reportWorkDone, setReportWorkDone] = useState("");
  const [reportNextSteps, setReportNextSteps] = useState("");
  const [reportSupervisorFeedback, setReportSupervisorFeedback] = useState("");
  const [reportAttachmentDocumentKeys, setReportAttachmentDocumentKeys] = useState<string[]>([]);
  const [reportTranscriptDocumentKeys, setReportTranscriptDocumentKeys] = useState<string[]>([]);
  const [reportBlockers, setReportBlockers] = useState<ReportBlockerDraft[]>([]);
  const [reportBlockerTitle, setReportBlockerTitle] = useState("");
  const [reportBlockerDescription, setReportBlockerDescription] = useState("");
  const [reportBlockerSeverity, setReportBlockerSeverity] = useState("medium");
  const [reportBlockerStatus, setReportBlockerStatus] = useState("open");
  const [reportUploadFile, setReportUploadFile] = useState<File | null>(null);
  const [reportUploading, setReportUploading] = useState(false);
  const [reportTranscriptUploadFile, setReportTranscriptUploadFile] = useState<File | null>(null);
  const [reportTranscriptUploading, setReportTranscriptUploading] = useState(false);

  const [assessmentStrengths, setAssessmentStrengths] = useState("");
  const [assessmentWeaknesses, setAssessmentWeaknesses] = useState("");
  const [assessmentRationale, setAssessmentRationale] = useState("");

  const activeDocuments = useMemo(
    () => documents.filter((item) => item.status === "uploaded" || item.status === "indexed"),
    [documents]
  );
  const documentMap = useMemo(
    () => new Map(activeDocuments.map((item) => [item.document_key, item])),
    [activeDocuments]
  );
  const bibliographyMap = useMemo(
    () => new Map(bibliography.map((item) => [item.id, item])),
    [bibliography]
  );

  const loadWorkspace = useCallback(async (projectId = selectedProjectId) => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [workspaceRes, membersRes, docsRes, coursesRes, bibliographyRes] = await Promise.all([
        api.getTeachingWorkspace(projectId),
        api.listMembers(projectId),
        api.listDocuments(projectId),
        api.listCourses(1, 200, "", true),
        api.listGlobalBibliography({ page: 1, page_size: 200, visibility: "shared" }),
      ]);
      setWorkspace(workspaceRes);
      setMembers(membersRes.items.filter((item) => item.is_active));
      setDocuments(docsRes.items);
      setCourses(coursesRes.items);
      setBibliography(bibliographyRes.items);
      setCourseId(workspaceRes.profile.course_id || "");
      setAcademicYear(workspaceRes.profile.academic_year || "");
      setTerm(workspaceRes.profile.term || "");
      setResponsibleUserId(workspaceRes.profile.responsible_user_id || "");
      setProfileStatus(workspaceRes.profile.status || "draft");
      setHealth(workspaceRes.profile.health || "green");
      setReportingCadenceDays(workspaceRes.profile.reporting_cadence_days || 14);
      setFunctionalObjectives(workspaceRes.profile.functional_objectives_markdown || "");
      setSpecifications(workspaceRes.profile.specifications_markdown || "");
      setFinalGrade(workspaceRes.profile.final_grade == null ? "" : String(workspaceRes.profile.final_grade));
      setAssessmentStrengths(workspaceRes.assessment?.strengths_markdown || "");
      setAssessmentWeaknesses(workspaceRes.assessment?.weaknesses_markdown || "");
      setAssessmentRationale(workspaceRes.assessment?.grading_rationale_markdown || "");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load teaching project.");
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  // Auto-dismiss status messages
  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(""), 3000);
    return () => clearTimeout(timer);
  }, [status]);

  function resetEntityForm() {
    setEditingId(null);
    setStudentName("");
    setStudentEmail("");
    setBackgroundMaterialType("paper");
    setBackgroundMaterialTitle("");
    setBackgroundMaterialBibliographyId("");
    setBackgroundMaterialDocumentKey("");
    setBackgroundMaterialExternalUrl("");
    setBackgroundMaterialNotes("");
    setBackgroundUploadFile(null);
    setArtifactType("report");
    setArtifactLabel("");
    setArtifactRequired(true);
    setArtifactStatus("missing");
    setArtifactDocumentKey("");
    setArtifactExternalUrl("");
    setArtifactNotes("");
    setArtifactUploadFile(null);
    setMilestoneKind("");
    setMilestoneLabel("");
    setMilestoneDueAt("");
    setMilestoneStatus("pending");
    setBlockerTitle("");
    setBlockerDescription("");
    setBlockerSeverity("medium");
    setBlockerStatus("open");
    setBlockerDetectedFrom("");
    setReportDate("");
    setReportMeetingDate("");
    setReportWorkDone("");
    setReportNextSteps("");
    setReportSupervisorFeedback("");
    setReportAttachmentDocumentKeys([]);
    setReportTranscriptDocumentKeys([]);
    setReportBlockers([]);
    setReportBlockerTitle("");
    setReportBlockerDescription("");
    setReportBlockerSeverity("medium");
    setReportBlockerStatus("open");
    setReportUploadFile(null);
    setReportTranscriptUploadFile(null);
    setReportEditorTab("work_done");
  }

  function openModal(kind: EntityModal, id?: string) {
    resetEntityForm();
    setStatus("");
    setError("");
    setModal(kind);
    if (!workspace || !id) return;
    setEditingId(id);
    if (kind === "student") {
      const item = workspace.students.find((entry) => entry.id === id);
      if (!item) return;
      setStudentName(item.full_name);
      setStudentEmail(item.email || "");
    }
    if (kind === "background") {
      const item = workspace.background_materials.find((entry) => entry.id === id);
      if (!item) return;
      setBackgroundMaterialType(item.material_type);
      setBackgroundMaterialTitle(item.title);
      setBackgroundMaterialBibliographyId(item.bibliography_reference_id || "");
      setBackgroundMaterialDocumentKey(item.document_key || "");
      setBackgroundMaterialExternalUrl(item.external_url || "");
      setBackgroundMaterialNotes(item.notes || "");
    }
    if (kind === "artifact") {
      const item = workspace.artifacts.find((entry) => entry.id === id);
      if (!item) return;
      setArtifactType(item.artifact_type);
      setArtifactLabel(item.label);
      setArtifactRequired(item.required);
      setArtifactStatus(item.status);
      setArtifactDocumentKey(item.document_key || "");
      setArtifactExternalUrl(item.external_url || "");
      setArtifactNotes(item.notes || "");
      setArtifactUploadFile(null);
    }
    if (kind === "milestone") {
      const item = workspace.milestones.find((entry) => entry.id === id);
      if (!item) return;
      setMilestoneKind(item.kind);
      setMilestoneLabel(item.label);
      setMilestoneDueAt(toDateInput(item.due_at));
      setMilestoneStatus(item.status);
    }
    if (kind === "blocker") {
      const item = workspace.blockers.find((entry) => entry.id === id);
      if (!item) return;
      setBlockerTitle(item.title);
      setBlockerDescription(item.description || "");
      setBlockerSeverity(item.severity);
      setBlockerStatus(item.status);
      setBlockerDetectedFrom(item.detected_from || "");
    }
    if (kind === "report") {
      if (!id && workspace) {
        setReportBlockers(
          workspace.blockers
            .filter((entry) => entry.status !== "resolved")
            .map((entry) => ({
              id: entry.id,
              title: entry.title,
              description: entry.description || "",
              severity: entry.severity,
              status: entry.status,
            }))
        );
      }
      const item = workspace.progress_reports.find((entry) => entry.id === id);
      if (!item) return;
      setReportDate(toDateInput(item.report_date));
      setReportMeetingDate(toDateInput(item.meeting_date));
      setReportWorkDone(item.work_done_markdown || "");
      setReportNextSteps(item.next_steps_markdown || "");
      setReportSupervisorFeedback(item.supervisor_feedback_markdown || "");
      setReportAttachmentDocumentKeys(item.attachment_document_keys || []);
      setReportTranscriptDocumentKeys(item.transcript_document_keys || []);
      setReportBlockers(
        item.blockers.map((entry) => ({
          id: entry.id,
          title: entry.title,
          description: entry.description || "",
          severity: entry.severity,
          status: entry.status,
        }))
      );
    }
  }

  async function saveProfile() {
    if (!selectedProjectId) return;
    try {
      setSavingProfile(true);
      const next = await api.updateTeachingProfile(selectedProjectId, {
        course_id: courseId || null,
        academic_year: academicYear || null,
        term: term || null,
        responsible_user_id: responsibleUserId || null,
        status: profileStatus,
        health,
        reporting_cadence_days: reportingCadenceDays,
        functional_objectives_markdown: functionalObjectives || null,
        specifications_markdown: specifications || null,
        final_grade: finalGrade === "" ? null : Number(finalGrade),
      });
      setWorkspace((current) => current ? { ...current, profile: next } : current);
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save teaching profile.");
    } finally {
      setSavingProfile(false);
    }
  }

  async function refreshDocuments(projectId = selectedProjectId) {
    if (!projectId) return;
    const docsRes = await api.listDocuments(projectId);
    setDocuments(docsRes.items);
  }

  async function handleArtifactUpload() {
    if (!selectedProjectId || !artifactUploadFile) return;
    try {
      setArtifactUploading(true);
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: artifactUploadFile,
        scope: "project",
        title: artifactLabel.trim() || artifactUploadFile.name,
        metadata_json: JSON.stringify({ category: "teaching_artifact" }),
      });
      await refreshDocuments(selectedProjectId);
      setArtifactDocumentKey(uploaded.document_key);
      if (artifactType !== "repository") {
        setArtifactStatus("submitted");
      }
      setArtifactUploadFile(null);
      setStatus("Uploaded.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload artifact file.");
    } finally {
      setArtifactUploading(false);
    }
  }

  async function handleBackgroundUpload() {
    if (!selectedProjectId || !backgroundUploadFile) return;
    try {
      setBackgroundUploading(true);
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: backgroundUploadFile,
        scope: "project",
        title: backgroundMaterialTitle.trim() || backgroundUploadFile.name,
        metadata_json: JSON.stringify({ category: "teaching_background_material" }),
      });
      await refreshDocuments(selectedProjectId);
      setBackgroundMaterialDocumentKey(uploaded.document_key);
      setBackgroundUploadFile(null);
      setStatus("Uploaded.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload background material.");
    } finally {
      setBackgroundUploading(false);
    }
  }

  async function handleReportUpload() {
    if (!selectedProjectId || !reportUploadFile) return;
    try {
      setReportUploading(true);
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: reportUploadFile,
        scope: "project",
        title: reportUploadFile.name,
        metadata_json: JSON.stringify({ category: "teaching_progress_attachment" }),
      });
      await refreshDocuments(selectedProjectId);
      setReportAttachmentDocumentKeys((current) =>
        current.includes(uploaded.document_key) ? current : [...current, uploaded.document_key]
      );
      setReportUploadFile(null);
      setStatus("Uploaded.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload progress attachment.");
    } finally {
      setReportUploading(false);
    }
  }

  async function handleTranscriptUpload() {
    if (!selectedProjectId || !reportTranscriptUploadFile) return;
    try {
      setReportTranscriptUploading(true);
      const uploaded = await api.uploadDocument(selectedProjectId, {
        file: reportTranscriptUploadFile,
        scope: "project",
        title: reportTranscriptUploadFile.name,
        metadata_json: JSON.stringify({ category: "teaching_meeting_transcript" }),
      });
      await refreshDocuments(selectedProjectId);
      setReportTranscriptDocumentKeys((current) =>
        current.includes(uploaded.document_key) ? current : [...current, uploaded.document_key]
      );
      setReportTranscriptUploadFile(null);
      setStatus("Uploaded.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload meeting transcript.");
    } finally {
      setReportTranscriptUploading(false);
    }
  }

  async function submitProfileSection(section: "project" | "objectives" | "specifications") {
    if (!selectedProjectId) return;
    try {
      setBusy(true);
      const next = await api.updateTeachingProfile(selectedProjectId, {
        course_id: courseId || null,
        academic_year: academicYear || null,
        term: term || null,
        responsible_user_id: responsibleUserId || null,
        status: profileStatus,
        health,
        reporting_cadence_days: reportingCadenceDays,
        functional_objectives_markdown: functionalObjectives || null,
        specifications_markdown: specifications || null,
        final_grade: finalGrade === "" ? null : Number(finalGrade),
      });
      setWorkspace((current) => current ? { ...current, profile: next } : current);
      setModal(null);
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save teaching profile.");
    } finally {
      setBusy(false);
    }
  }

  async function submitEntity() {
    if (!selectedProjectId || !modal) return;
    if (modal === "project" || modal === "objectives" || modal === "specifications") {
      await submitProfileSection(modal);
      return;
    }
    try {
      setBusy(true);
      if (modal === "student") {
        if (editingId) {
          await api.updateTeachingStudent(selectedProjectId, editingId, { full_name: studentName, email: studentEmail || null });
        } else {
          await api.createTeachingStudent(selectedProjectId, { full_name: studentName, email: studentEmail || null });
        }
      }
      if (modal === "background") {
        const payload = {
          material_type: backgroundMaterialType,
          title: backgroundMaterialTitle,
          bibliography_reference_id: backgroundMaterialBibliographyId || null,
          document_key: backgroundMaterialDocumentKey || null,
          external_url: backgroundMaterialExternalUrl || null,
          notes: backgroundMaterialNotes || null,
        };
        if (editingId) await api.updateTeachingBackgroundMaterial(selectedProjectId, editingId, payload);
        else await api.createTeachingBackgroundMaterial(selectedProjectId, payload);
      }
      if (modal === "artifact") {
        const payload = {
          artifact_type: artifactType,
          label: artifactLabel,
          required: artifactRequired,
          status: artifactStatus,
          document_key: artifactDocumentKey || null,
          external_url: artifactExternalUrl || null,
          notes: artifactNotes || null,
        };
        if (editingId) await api.updateTeachingArtifact(selectedProjectId, editingId, payload);
        else await api.createTeachingArtifact(selectedProjectId, payload);
      }
      if (modal === "milestone") {
        const payload = {
          kind: milestoneKind,
          label: milestoneLabel,
          due_at: hasProjectDeadlines ? milestoneDueAt || null : null,
          status: milestoneStatus,
        };
        if (editingId) await api.updateTeachingMilestone(selectedProjectId, editingId, payload);
        else await api.createTeachingMilestone(selectedProjectId, payload);
      }
      if (modal === "blocker") {
        const payload = {
          title: blockerTitle,
          description: blockerDescription || null,
          severity: blockerSeverity,
          status: blockerStatus,
          detected_from: blockerDetectedFrom || null,
        };
        if (editingId) await api.updateTeachingBlocker(selectedProjectId, editingId, payload);
        else await api.createTeachingBlocker(selectedProjectId, payload);
      }
      if (modal === "report") {
        const payload = {
          report_date: reportDate || null,
          meeting_date: reportMeetingDate || null,
          work_done_markdown: reportWorkDone,
          next_steps_markdown: reportNextSteps,
          blocker_updates: reportBlockers.map((item) => ({
            id: item.id || null,
            title: item.title,
            description: item.description || null,
            severity: item.severity,
            status: item.status,
          })),
          supervisor_feedback_markdown: reportSupervisorFeedback || null,
          attachment_document_keys: reportAttachmentDocumentKeys,
          transcript_document_keys: reportTranscriptDocumentKeys,
        };
        if (editingId) await api.updateTeachingProgressReport(selectedProjectId, editingId, payload);
        else await api.createTeachingProgressReport(selectedProjectId, payload);
      }
      setModal(null);
      await loadWorkspace();
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save item.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteEntity(kind: Exclude<EntityModal, null>, id: string) {
    if (!selectedProjectId) return;
    const labels: Record<string, string> = {
      student: "student",
      background: "background material",
      artifact: "artifact",
      milestone: "milestone",
      blocker: "blocker",
      report: "progress report",
    };
    if (!window.confirm(`Delete this ${labels[kind] || "item"}?`)) return;
    try {
      if (kind === "student") await api.deleteTeachingStudent(selectedProjectId, id);
      if (kind === "background") await api.deleteTeachingBackgroundMaterial(selectedProjectId, id);
      if (kind === "artifact") await api.deleteTeachingArtifact(selectedProjectId, id);
      if (kind === "milestone") await api.deleteTeachingMilestone(selectedProjectId, id);
      if (kind === "blocker") await api.deleteTeachingBlocker(selectedProjectId, id);
      if (kind === "report") await api.deleteTeachingProgressReport(selectedProjectId, id);
      await loadWorkspace();
      setStatus("Deleted.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete item.");
    }
  }

  async function quickResolveBlocker(blockerId: string) {
    if (!selectedProjectId) return;
    try {
      const item = workspace?.blockers.find((entry) => entry.id === blockerId);
      if (!item) return;
      await api.updateTeachingBlocker(selectedProjectId, blockerId, {
        title: item.title,
        description: item.description || null,
        severity: item.severity,
        status: "resolved",
        detected_from: item.detected_from || null,
      });
      await loadWorkspace();
      setStatus("Resolved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve blocker.");
    }
  }

  async function saveAssessment() {
    if (!selectedProjectId) return;
    try {
      const next = await api.upsertTeachingAssessment(selectedProjectId, {
        grade: finalGrade === "" ? null : Number(finalGrade),
        strengths_markdown: assessmentStrengths || null,
        weaknesses_markdown: assessmentWeaknesses || null,
        grading_rationale_markdown: assessmentRationale || null,
        grader_user_id: responsibleUserId || null,
      });
      setWorkspace((current) => current ? { ...current, assessment: next } : current);
      setStatus("Saved.");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save assessment.");
    }
  }

  function addReportBlockerDraft() {
    if (!reportBlockerTitle.trim()) return;
    setReportBlockers((current) => [
      ...current,
      {
        title: reportBlockerTitle.trim(),
        description: reportBlockerDescription.trim(),
        severity: reportBlockerSeverity,
        status: reportBlockerStatus,
      },
    ]);
    setReportBlockerTitle("");
    setReportBlockerDescription("");
    setReportBlockerSeverity("medium");
    setReportBlockerStatus("open");
  }

  function updateReportBlockerDraft(index: number, next: Partial<ReportBlockerDraft>) {
    setReportBlockers((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...next } : item)));
  }

  function removeReportBlockerDraft(index: number) {
    setReportBlockers((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  function removeReportAttachment(documentKey: string) {
    setReportAttachmentDocumentKeys((current) => current.filter((item) => item !== documentKey));
  }

  function removeReportTranscript(documentKey: string) {
    setReportTranscriptDocumentKeys((current) => current.filter((item) => item !== documentKey));
  }

  function toggleReport(reportId: string) {
    setExpandedReports((current) => {
      const next = new Set(current);
      if (next.has(reportId)) next.delete(reportId);
      else next.add(reportId);
      return next;
    });
  }

  if (!selectedProjectId || !project) {
    return <div className="card">Select a project.</div>;
  }

  if (project.project_kind !== "teaching") {
    return <div className="card">This view is available for teaching projects only.</div>;
  }

  const profile = workspace?.profile ?? null;
  const openBlockers = workspace?.blockers.filter((item) => item.status !== "resolved").length ?? 0;
  const backgroundCount = workspace?.background_materials.length ?? 0;
  const missingArtifacts = workspace?.artifacts.filter((item) => item.required && item.status === "missing").length ?? 0;
  const latestReport = workspace?.progress_reports[0] ?? null;
  const selectedCourse = courses.find((course) => course.id === courseId) || null;
  const statusLabel = profileStatus.split("_").join(" ");
  const courseLabel = selectedCourse ? `${selectedCourse.code} · ${selectedCourse.title}` : "No course";
  const hasProjectDeadlines = selectedCourse?.has_project_deadlines ?? true;
  const overdueMilestones = workspace?.milestones.filter((item) => hasProjectDeadlines && isOverdue(item.due_at, item.status)).length ?? 0;
  const courseStaff: CourseStaffUser[] = selectedCourse
    ? [selectedCourse.teacher, ...selectedCourse.teaching_assistants].filter((item): item is CourseStaffUser => Boolean(item))
    : [];

  return (
    <div className="teaching-workspace">
      <div className="setup-summary-bar">
        <div className="setup-summary-stats">
          <span><strong>{project.code}</strong></span>
          <span className="setup-summary-sep" />
          <span>{courseLabel}</span>
          <span className="setup-summary-sep" />
          <span>{academicYear || "No year"}{term ? ` · ${term}` : ""}</span>
          <span className="setup-summary-sep" />
          <span>{workspace?.profile.responsible_user?.display_name || "No responsible"}</span>
          <span className="setup-summary-sep" />
          <span>{statusLabel}</span>
          <span className="setup-summary-sep" />
          <span>{renderHealthIndicator(health)}</span>
          <span className="setup-summary-sep" />
          <span>{openBlockers} blockers</span>
          <span className="setup-summary-sep" />
          <span>{missingArtifacts} missing</span>
          {overdueMilestones > 0 ? (
            <>
              <span className="setup-summary-sep" />
              <span className="danger-text">{overdueMilestones} overdue</span>
            </>
          ) : null}
        </div>
        <div className="teaching-summary-actions">
          <button
            type="button"
            className="meetings-new-btn"
            onClick={() =>
              onOpenAssistant(
                `Summarize the teaching project ${project.code}. Focus on progress, blockers, missing artifacts, milestones, and next supervision actions.`
              )
            }
          >
            <FontAwesomeIcon icon={faBrain} /> Summary
          </button>
          <button
            type="button"
            className="ghost teaching-summary-btn"
            onClick={() =>
              onOpenAssistant(
                `Review the teaching project ${project.code}. Provide a critical analysis grounded in the latest progress reports, artifacts, blockers, and milestones.`
              )
            }
          >
            <FontAwesomeIcon icon={faWandMagicSparkles} /> Analysis
          </button>
          <button
            type="button"
            className="ghost teaching-summary-btn"
              onClick={() =>
                onOpenAssistant(
                  `Prepare oral examination questions for the teaching project ${project.code}. Group them into technical questions, validation questions, and weak-point questions. Base them on the latest progress reports, meeting transcripts if available, artifacts, blockers, specifications, and claimed results.`
                )
              }
          >
            <FontAwesomeIcon icon={faGraduationCap} /> Oral
          </button>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {status ? <p className="success-message">{status}</p> : null}

      <div className="delivery-tabs">
        <button type="button" className={`delivery-tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          Overview
        </button>
        <button type="button" className={`delivery-tab ${tab === "background" ? "active" : ""}`} onClick={() => setTab("background")}>
          Background <span className="delivery-tab-count">{backgroundCount}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "artifacts" ? "active" : ""}`} onClick={() => setTab("artifacts")}>
          Artifacts <span className="delivery-tab-count">{missingArtifacts}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "progress" ? "active" : ""}`} onClick={() => setTab("progress")}>
          Progress <span className="delivery-tab-count">{workspace?.progress_reports.length ?? 0}</span>
        </button>
        <button type="button" className={`delivery-tab ${tab === "assessment" ? "active" : ""}`} onClick={() => setTab("assessment")}>
          Assessment
        </button>
        {tab === "progress" ? (
          <button type="button" className="meetings-new-btn delivery-tab-action" onClick={() => openModal("report")}>
            <FontAwesomeIcon icon={faPlus} /> Report
          </button>
        ) : null}
      </div>

      {loading || !workspace || !profile ? <div className="card">Loading...</div> : null}

      {!loading && workspace && profile && tab === "overview" ? (
        <div className="teaching-section-stack">
          {/* Latest Report */}
          <div className="card teaching-card">
            <div className="proposal-card-head">
              <div className="teaching-report-head-left">
                <strong>Latest Report</strong>
                {latestReport ? (
                  <span className="teaching-report-meta-inline">{latestReport.report_date ? new Date(latestReport.report_date).toLocaleDateString() : ""}{latestReport.meeting_date ? ` · Meeting ${new Date(latestReport.meeting_date).toLocaleDateString()}` : ""}</span>
                ) : null}
              </div>
              <div className="teaching-report-head-right">
                <span className="teaching-meta-inline">{reportingCadenceDays}d cadence</span>
                {finalGrade ? <span className="chip small">Grade: {finalGrade}</span> : null}
                <button type="button" className="ghost docs-action-btn" onClick={() => openModal("project")} title="Edit project">
                  <FontAwesomeIcon icon={faPenToSquare} />
                </button>
                {latestReport ? (
                  <button type="button" className="ghost docs-action-btn" onClick={() => openModal("report", latestReport.id)} title="Edit report">
                    <FontAwesomeIcon icon={faPenToSquare} />
                  </button>
                ) : null}
              </div>
            </div>
            {latestReport ? (
              <div className="chat-markdown teaching-markdown teaching-latest-report-content">
                {renderMarkdown(latestReport.work_done_markdown)}
              </div>
            ) : (
              <div className="teaching-empty">No progress reports yet</div>
            )}
          </div>

          {/* Objectives / Specifications — tabbed card */}
          <div className="card teaching-card">
            <div className="proposal-card-head">
              <div className="delivery-tabs teaching-inline-tabs">
                <button
                  type="button"
                  className={`delivery-tab ${overviewDocTab === "objectives" ? "active" : ""}`}
                  onClick={() => setOverviewDocTab("objectives")}
                >
                  Objectives
                </button>
                <button
                  type="button"
                  className={`delivery-tab ${overviewDocTab === "specifications" ? "active" : ""}`}
                  onClick={() => setOverviewDocTab("specifications")}
                >
                  Specifications
                </button>
              </div>
              <button
                type="button"
                className="ghost docs-action-btn"
                onClick={() => openModal(overviewDocTab === "objectives" ? "objectives" : "specifications")}
                title={`Edit ${overviewDocTab}`}
              >
                <FontAwesomeIcon icon={faPenToSquare} />
              </button>
            </div>
            <div className="chat-markdown teaching-markdown teaching-doc-content">
              {overviewDocTab === "objectives"
                ? (functionalObjectives ? renderMarkdown(functionalObjectives) : <div className="teaching-empty">No content</div>)
                : (specifications ? renderMarkdown(specifications) : <div className="teaching-empty">No content</div>)}
            </div>
          </div>

          <div className="card teaching-card">
            <div className="proposal-card-head">
              <strong>Students</strong>
              <button type="button" className="meetings-new-btn" onClick={() => openModal("student")}>
                <FontAwesomeIcon icon={faPlus} /> Add
              </button>
            </div>
            <div className="teaching-staff-strip">
              {workspace.students.map((item) => (
                <div key={item.id} className="teaching-staff-chip">
                  <span>{item.full_name}{item.email ? ` · ${item.email}` : ""}</span>
                  <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openModal("student", item.id)}><FontAwesomeIcon icon={faPenToSquare} /></button>
                  <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteEntity("student", item.id)}><FontAwesomeIcon icon={faTrash} /></button>
                </div>
              ))}
              {workspace.students.length === 0 ? <span className="teaching-empty">No students</span> : null}
            </div>
          </div>

          <div className="card teaching-card">
            <div className="proposal-card-head">
              <span className="teaching-section-label"><strong>Milestones</strong> <span className="delivery-tab-count">{workspace.milestones.length}</span></span>
              <button type="button" className="meetings-new-btn" onClick={() => openModal("milestone")}>
                <FontAwesomeIcon icon={faPlus} /> Add
              </button>
            </div>
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Label</th>
                    {hasProjectDeadlines ? <th>Due</th> : null}
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {workspace.milestones.map((item) => {
                    const overdue = hasProjectDeadlines && isOverdue(item.due_at, item.status);
                    return (
                      <tr key={item.id} className={overdue ? "teaching-row-attention red" : ""}>
                        <td><span className="chip small">{item.kind}</span></td>
                        <td><strong>{item.label}</strong></td>
                        {hasProjectDeadlines ? (
                          <td className={overdue ? "teaching-overdue-text" : ""}>
                            {item.due_at ? new Date(item.due_at).toLocaleDateString() : "-"}
                          </td>
                        ) : null}
                        <td><span className="chip small">{item.status}</span></td>
                        <td className="teaching-row-actions">
                          <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openModal("milestone", item.id)}><FontAwesomeIcon icon={faPenToSquare} /></button>
                          <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteEntity("milestone", item.id)}><FontAwesomeIcon icon={faTrash} /></button>
                        </td>
                      </tr>
                    );
                  })}
                  {workspace.milestones.length === 0 ? <tr><td colSpan={hasProjectDeadlines ? 5 : 4}>No milestones</td></tr> : null}
                </tbody>
              </table>
            </div>

            <div className="proposal-card-head" style={{ marginTop: 8 }}>
              <span className="teaching-section-label"><strong>Blockers</strong> <span className="delivery-tab-count">{openBlockers}</span></span>
              <button type="button" className="meetings-new-btn" onClick={() => openModal("blocker")}>
                <FontAwesomeIcon icon={faPlus} /> Add
              </button>
            </div>
            <div className="simple-table-wrap">
              <table className="simple-table compact-table">
                <thead><tr><th>Title</th><th>Severity</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {workspace.blockers.map((item) => (
                    <tr key={item.id} className={item.status !== "resolved" ? "teaching-row-attention yellow" : ""}>
                      <td><strong>{item.title}</strong></td>
                      <td><span className="chip small">{item.severity}</span></td>
                      <td><span className="chip small">{item.status}</span></td>
                      <td className="teaching-row-actions">
                        {item.status !== "resolved" ? (
                          <button type="button" className="ghost icon-text-button small" onClick={() => void quickResolveBlocker(item.id)}>Resolve</button>
                        ) : null}
                        <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openModal("blocker", item.id)}><FontAwesomeIcon icon={faPenToSquare} /></button>
                        <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteEntity("blocker", item.id)}><FontAwesomeIcon icon={faTrash} /></button>
                      </td>
                    </tr>
                  ))}
                  {workspace.blockers.length === 0 ? <tr><td colSpan={4}>No blockers</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>

          <ProjectResourcesPanel projectId={selectedProjectId} />
        </div>
      ) : null}

      {!loading && workspace && tab === "artifacts" ? (
        <div className="card teaching-card">
          <div className="proposal-card-head">
            <strong>Artifacts</strong>
            <div className="teaching-assessment-head-right">
              <select className="teaching-material-type-filter" value={artifactTypeFilter} onChange={(event) => setArtifactTypeFilter(event.target.value)}>
                <option value="">All Types</option>
                <option value="report">Report</option>
                <option value="repository">Repository</option>
                <option value="video">Video</option>
                <option value="slides">Slides</option>
                <option value="dataset">Dataset</option>
                <option value="other">Other</option>
              </select>
              <select className="teaching-material-type-filter" value={artifactStatusFilter} onChange={(event) => setArtifactStatusFilter(event.target.value)}>
                <option value="">All Status</option>
                <option value="missing">Missing</option>
                <option value="submitted">Submitted</option>
                <option value="accepted">Accepted</option>
                <option value="needs_revision">Needs Revision</option>
              </select>
              <button type="button" className="meetings-new-btn" onClick={() => openModal("artifact")}>
                <FontAwesomeIcon icon={faPlus} /> Add
              </button>
            </div>
          </div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead><tr><th>Label</th><th>Type</th><th>Required</th><th>Status</th><th>Link</th><th /></tr></thead>
              <tbody>
                {workspace.artifacts
                  .filter((item) => (!artifactTypeFilter || item.artifact_type === artifactTypeFilter) && (!artifactStatusFilter || item.status === artifactStatusFilter))
                  .map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.label}</strong></td>
                    <td>{item.artifact_type}</td>
                    <td>{item.required ? "yes" : "no"}</td>
                    <td><span className="chip small">{item.status}</span></td>
                    <td>
                      {item.external_url ? (
                        <a href={item.external_url} target="_blank" rel="noreferrer" className="teaching-material-link" title={item.external_url}>
                          <FontAwesomeIcon icon={faArrowUpRightFromSquare} /> open
                        </a>
                      ) : item.document_key ? (
                        <span className="chip small"><FontAwesomeIcon icon={faPaperclip} /> {documentMap.get(item.document_key)?.title || item.document_key.slice(0, 8)}</span>
                      ) : "-"}
                    </td>
                    <td className="teaching-row-actions">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openModal("artifact", item.id)}><FontAwesomeIcon icon={faPenToSquare} /></button>
                      <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteEntity("artifact", item.id)}><FontAwesomeIcon icon={faTrash} /></button>
                    </td>
                  </tr>
                ))}
                {workspace.artifacts.filter((item) => (!artifactTypeFilter || item.artifact_type === artifactTypeFilter) && (!artifactStatusFilter || item.status === artifactStatusFilter)).length === 0 ? <tr><td colSpan={6}>{workspace.artifacts.length === 0 ? "No artifacts" : "No matching artifacts"}</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {!loading && workspace && tab === "background" ? (
        <div className="card teaching-card">
          <div className="proposal-card-head">
            <strong>Background</strong>
            <button type="button" className="meetings-new-btn" onClick={() => openModal("background")}>
              <FontAwesomeIcon icon={faPlus} /> Add
            </button>
          </div>
          <div className="simple-table-wrap">
            <table className="simple-table compact-table">
              <thead><tr><th>Title</th><th>Type</th><th>Link</th><th>Notes</th><th /></tr></thead>
              <tbody>
                {workspace.background_materials.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.title}</strong></td>
                    <td><span className="chip small">{item.material_type}</span></td>
                    <td>
                      {item.bibliography_reference_id ? (
                        item.bibliography_url ? (
                          <a href={item.bibliography_url} target="_blank" rel="noreferrer" className="teaching-material-link" title={item.bibliography_url}>
                            <FontAwesomeIcon icon={faArrowUpRightFromSquare} /> open
                          </a>
                        ) : (
                          <span className="chip small"><FontAwesomeIcon icon={faPaperclip} /> {item.bibliography_title || "paper"}</span>
                        )
                      ) : item.external_url ? (
                        <a href={item.external_url} target="_blank" rel="noreferrer" className="teaching-material-link" title={item.external_url}>
                          <FontAwesomeIcon icon={faArrowUpRightFromSquare} /> open
                        </a>
                      ) : item.document_key ? (
                        <span className="chip small"><FontAwesomeIcon icon={faPaperclip} /> {documentMap.get(item.document_key)?.title || item.document_key.slice(0, 8)}</span>
                      ) : "-"}
                    </td>
                    <td>{item.notes || "-"}</td>
                    <td className="teaching-row-actions">
                      <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openModal("background", item.id)}><FontAwesomeIcon icon={faPenToSquare} /></button>
                      <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteEntity("background", item.id)}><FontAwesomeIcon icon={faTrash} /></button>
                    </td>
                  </tr>
                ))}
                {workspace.background_materials.length === 0 ? <tr><td colSpan={5}>No background material</td></tr> : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {!loading && workspace && tab === "progress" ? (
        <div className="teaching-progress-stack">
          <div className="teaching-timeline">
            {workspace.progress_reports.map((item, index) => {
              const isExpanded = index === 0 || expandedReports.has(item.id);
              const reportBlockerCount = item.blockers.filter((b) => b.status !== "resolved").length;
              const hasOpenBlockers = reportBlockerCount > 0;
              const hasFeedback = Boolean(item.supervisor_feedback_markdown);
              const attachmentCount = item.attachment_document_keys.length + item.transcript_document_keys.length;
              const reportNumber = workspace.progress_reports.length - index;
              return (
                <div key={item.id} className="teaching-timeline-entry">
                  <div className="teaching-timeline-rail">
                    <div className={`teaching-timeline-dot ${hasOpenBlockers ? "warning" : ""}`} />
                    {index < workspace.progress_reports.length - 1 ? <div className="teaching-timeline-line" /> : null}
                  </div>
                  <div className={`card teaching-card teaching-timeline-card ${isExpanded ? "expanded" : ""}`}>
                    <button type="button" className="teaching-report-header" onClick={() => toggleReport(item.id)}>
                      <div className="teaching-report-head-left">
                        <span className="teaching-report-number">#{reportNumber}</span>
                        <strong>{item.report_date ? new Date(item.report_date).toLocaleDateString() : "-"}</strong>
                        {item.meeting_date ? <span className="teaching-report-meta-inline">Meeting {new Date(item.meeting_date).toLocaleDateString()}</span> : null}
                      </div>
                      <div className="teaching-report-head-right">
                        {/* Collapsed summary indicators */}
                        {!isExpanded ? (
                          <div className="teaching-report-indicators">
                            {hasOpenBlockers ? <span className="teaching-indicator warning" title={`${reportBlockerCount} open blocker${reportBlockerCount > 1 ? "s" : ""}`}><FontAwesomeIcon icon={faCircle} /> {reportBlockerCount}</span> : null}
                            {hasFeedback ? <span className="teaching-indicator feedback" title="Has supervisor feedback"><FontAwesomeIcon icon={faComment} /></span> : null}
                            {attachmentCount > 0 ? <span className="teaching-indicator" title={`${attachmentCount} attachment${attachmentCount > 1 ? "s" : ""}`}><FontAwesomeIcon icon={faPaperclip} /> {attachmentCount}</span> : null}
                          </div>
                        ) : null}
                        <FontAwesomeIcon icon={isExpanded ? faChevronUp : faChevronDown} className="teaching-report-chevron" />
                      </div>
                    </button>
                    {isExpanded ? (
                      <div className="teaching-report-body">
                        <div className="teaching-report-stack">
                          <div>
                            <strong className="teaching-report-section-label">Work Done</strong>
                            <div className="chat-markdown teaching-markdown">{renderMarkdown(item.work_done_markdown)}</div>
                          </div>
                          {item.next_steps_markdown ? (
                            <div>
                              <strong className="teaching-report-section-label">Next Steps</strong>
                              <div className="chat-markdown teaching-markdown">{renderMarkdown(item.next_steps_markdown)}</div>
                            </div>
                          ) : null}
                          {item.blockers.length > 0 ? (
                            <div>
                              <strong className="teaching-report-section-label">Blockers</strong>
                              <div className="teaching-report-blocker-list">
                                {item.blockers.map((entry) => (
                                  <div key={entry.id} className={`teaching-report-blocker-item ${entry.status === "resolved" ? "resolved" : ""}`}>
                                    <span className={`teaching-report-blocker-severity ${entry.severity}`} title={entry.severity} />
                                    <span>{entry.title}</span>
                                    <span className="chip small">{entry.status}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : null}
                        </div>
                        {hasFeedback ? (
                          <div className="teaching-feedback-block">
                            <strong className="teaching-report-section-label">Supervisor Feedback</strong>
                            <div className="chat-markdown teaching-markdown">{renderMarkdown(item.supervisor_feedback_markdown!)}</div>
                          </div>
                        ) : null}
                        {(item.attachment_document_keys.length > 0 || item.transcript_document_keys.length > 0) ? (
                          <div className="teaching-report-files">
                            {item.attachment_document_keys.length > 0 ? (
                              <div className="teaching-report-file-group">
                                <span className="teaching-report-file-label"><FontAwesomeIcon icon={faPaperclip} /> Attachments</span>
                                <div className="teaching-attachment-list">
                                  {item.attachment_document_keys.map((documentKey) => (
                                    <span key={documentKey} className="chip small">
                                      {documentMap.get(documentKey)?.title || documentKey.slice(0, 8)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {item.transcript_document_keys.length > 0 ? (
                              <div className="teaching-report-file-group">
                                <span className="teaching-report-file-label"><FontAwesomeIcon icon={faMicrophone} /> Transcripts</span>
                                <div className="teaching-attachment-list">
                                  {item.transcript_document_keys.map((documentKey) => (
                                    <span key={documentKey} className="chip small">
                                      {documentMap.get(documentKey)?.title || documentKey.slice(0, 8)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                        <div className="teaching-report-actions">
                          <button type="button" className="ghost docs-action-btn" title="Edit" onClick={() => openModal("report", item.id)}><FontAwesomeIcon icon={faPenToSquare} /></button>
                          <button type="button" className="ghost docs-action-btn danger" title="Delete" onClick={() => void deleteEntity("report", item.id)}><FontAwesomeIcon icon={faTrash} /></button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {workspace.progress_reports.length === 0 ? <div className="card">No progress reports</div> : null}
        </div>
      ) : null}

      {!loading && workspace && tab === "assessment" ? (
        <div className="card teaching-card">
          <div className="proposal-card-head">
            <strong>Assessment</strong>
            <div className="teaching-assessment-head-right">
              <label className="teaching-grade-inline">
                Grade
                <input type="number" min={0} max={10} step={0.1} value={finalGrade} onChange={(event) => setFinalGrade(event.target.value)} />
              </label>
              <button type="button" className="meetings-new-btn" onClick={() => void saveAssessment()}>Save</button>
            </div>
          </div>
          <div className="delivery-tabs teaching-inline-tabs">
            <button
              type="button"
              className={`delivery-tab ${assessmentEditorTab === "strengths" ? "active" : ""}`}
              onClick={() => setAssessmentEditorTab("strengths")}
            >
              Strengths
            </button>
            <button
              type="button"
              className={`delivery-tab ${assessmentEditorTab === "weaknesses" ? "active" : ""}`}
              onClick={() => setAssessmentEditorTab("weaknesses")}
            >
              Weaknesses
            </button>
            <button
              type="button"
              className={`delivery-tab ${assessmentEditorTab === "rationale" ? "active" : ""}`}
              onClick={() => setAssessmentEditorTab("rationale")}
            >
              Rationale
            </button>
          </div>
          {assessmentEditorTab === "strengths" ? (
            <ProposalRichEditor value={assessmentStrengths} onChange={setAssessmentStrengths} placeholder="Strengths" />
          ) : null}
          {assessmentEditorTab === "weaknesses" ? (
            <ProposalRichEditor value={assessmentWeaknesses} onChange={setAssessmentWeaknesses} placeholder="Weaknesses" />
          ) : null}
          {assessmentEditorTab === "rationale" ? (
            <ProposalRichEditor value={assessmentRationale} onChange={setAssessmentRationale} placeholder="Rationale" />
          ) : null}
        </div>
      ) : null}

      {modal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div
            className={`modal-card ${
              modal === "student" || modal === "milestone" || modal === "blocker"
                ? ""
                : modal === "report"
                  ? "settings-modal-card teaching-report-modal"
                  : modal === "objectives" || modal === "specifications"
                    ? "settings-modal-card teaching-editor-modal"
                    : "settings-modal-card"
            }`}
          >
            <div className="modal-head">
              <h3>{modalTitle(modal, editingId)}</h3>
              <div className="modal-head-actions">
                <button type="button" onClick={() => void submitEntity()} disabled={busy}>
                  {busy ? "Saving..." : "Save"}
                </button>
                <button type="button" className="ghost docs-action-btn" onClick={() => setModal(null)} title="Close">
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>

            {modal === "project" ? (
              <div className="form-grid">
                <label>
                  Course
                  <select value={courseId} onChange={(event) => setCourseId(event.target.value)}>
                    <option value="">Select</option>
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>{course.code} · {course.title}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Academic Year
                  <input value={academicYear} onChange={(event) => setAcademicYear(event.target.value)} />
                </label>
                <label>
                  Term
                  <input value={term} onChange={(event) => setTerm(event.target.value)} />
                </label>
                <label>
                  Responsible
                  <select value={responsibleUserId} onChange={(event) => setResponsibleUserId(event.target.value)} disabled={!courseId}>
                    <option value="">Select</option>
                    {courseStaff.map((item) => (
                      <option key={item.user_id} value={item.user_id}>{item.display_name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Status
                  <select value={profileStatus} onChange={(event) => setProfileStatus(event.target.value)}>
                    <option value="draft">draft</option>
                    <option value="active">active</option>
                    <option value="at_risk">at_risk</option>
                    <option value="blocked">blocked</option>
                    <option value="completed">completed</option>
                    <option value="graded">graded</option>
                  </select>
                </label>
                <label>
                  Health
                  <select value={health} onChange={(event) => setHealth(event.target.value)}>
                    <option value="green">green</option>
                    <option value="yellow">yellow</option>
                    <option value="red">red</option>
                  </select>
                </label>
                <label>
                  Cadence Days
                  <input type="number" min={1} max={365} value={reportingCadenceDays} onChange={(event) => setReportingCadenceDays(Number(event.target.value) || 14)} />
                </label>
              </div>
            ) : null}

            {modal === "objectives" ? (
              <div className="teaching-report-editor-stack">
                <div className="card teaching-editor-card">
                  <ProposalRichEditor value={functionalObjectives} onChange={setFunctionalObjectives} placeholder="Functional objectives" />
                </div>
              </div>
            ) : null}

            {modal === "specifications" ? (
              <div className="teaching-report-editor-stack">
                <div className="card teaching-editor-card">
                  <ProposalRichEditor value={specifications} onChange={setSpecifications} placeholder="Specifications" />
                </div>
              </div>
            ) : null}

            {modal === "student" ? (
              <div className="form-grid">
                <label>
                  Name
                  <input value={studentName} onChange={(event) => setStudentName(event.target.value)} />
                </label>
                <label>
                  Email
                  <input value={studentEmail} onChange={(event) => setStudentEmail(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "background" ? (
              <div className="form-grid">
                <label>
                  Type
                  <select value={backgroundMaterialType} onChange={(event) => setBackgroundMaterialType(event.target.value)}>
                    <option value="paper">paper</option>
                    <option value="website">website</option>
                    <option value="video">video</option>
                    <option value="repository">repository</option>
                    <option value="dataset">dataset</option>
                    <option value="document">document</option>
                    <option value="other">other</option>
                  </select>
                </label>
                <label>
                  Title
                  <input value={backgroundMaterialTitle} onChange={(event) => setBackgroundMaterialTitle(event.target.value)} />
                </label>
                {backgroundMaterialType === "paper" ? (
                  <label className="full-span">
                    Bibliography
                    <select
                      value={backgroundMaterialBibliographyId}
                      onChange={(event) => {
                        const nextId = event.target.value;
                        setBackgroundMaterialBibliographyId(nextId);
                        const entry = bibliographyMap.get(nextId);
                        if (entry) {
                          setBackgroundMaterialTitle(entry.title);
                          setBackgroundMaterialExternalUrl(entry.url || "");
                        }
                      }}
                    >
                      <option value="">Select</option>
                      {bibliography.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.title}{item.year ? ` (${item.year})` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <label className="full-span">
                  Document
                  <select value={backgroundMaterialDocumentKey} onChange={(event) => setBackgroundMaterialDocumentKey(event.target.value)}>
                    <option value="">Select</option>
                    {activeDocuments.map((item) => (
                      <option key={item.document_key} value={item.document_key}>{item.title}</option>
                    ))}
                  </select>
                </label>
                <label className="full-span">
                  Upload File
                  <div className="teaching-upload-row">
                    <input type="file" onChange={(event) => setBackgroundUploadFile(event.target.files?.[0] || null)} />
                    <button type="button" className="ghost" onClick={() => void handleBackgroundUpload()} disabled={!backgroundUploadFile || backgroundUploading}>
                      {backgroundUploading ? "Uploading..." : "Upload"}
                    </button>
                  </div>
                </label>
                <label className="full-span">
                  URL
                  <input value={backgroundMaterialExternalUrl} onChange={(event) => setBackgroundMaterialExternalUrl(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={4} value={backgroundMaterialNotes} onChange={(event) => setBackgroundMaterialNotes(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "artifact" ? (
              <div className="form-grid">
                <label>
                  Label
                  <input value={artifactLabel} onChange={(event) => setArtifactLabel(event.target.value)} />
                </label>
                <label>
                  Type
                  <select value={artifactType} onChange={(event) => setArtifactType(event.target.value)}>
                    <option value="report">report</option>
                    <option value="repository">repository</option>
                    <option value="video">video</option>
                    <option value="slides">slides</option>
                    <option value="dataset">dataset</option>
                    <option value="other">other</option>
                  </select>
                </label>
                <label>
                  Status
                  <select value={artifactStatus} onChange={(event) => setArtifactStatus(event.target.value)}>
                    <option value="missing">missing</option>
                    <option value="submitted">submitted</option>
                    <option value="accepted">accepted</option>
                    <option value="needs_revision">needs_revision</option>
                  </select>
                </label>
                <label>
                  Required
                  <select value={artifactRequired ? "yes" : "no"} onChange={(event) => setArtifactRequired(event.target.value === "yes")}>
                    <option value="yes">yes</option>
                    <option value="no">no</option>
                  </select>
                </label>
                <label className="full-span">
                  Document
                  <select value={artifactDocumentKey} onChange={(event) => setArtifactDocumentKey(event.target.value)}>
                    <option value="">Select</option>
                    {activeDocuments.map((item) => (
                      <option key={item.document_key} value={item.document_key}>{item.title}</option>
                    ))}
                  </select>
                </label>
                <label className="full-span">
                  Upload File
                  <div className="teaching-upload-row">
                    <input type="file" onChange={(event) => setArtifactUploadFile(event.target.files?.[0] || null)} />
                    <button type="button" className="ghost" onClick={() => void handleArtifactUpload()} disabled={!artifactUploadFile || artifactUploading}>
                      {artifactUploading ? "Uploading..." : "Upload"}
                    </button>
                  </div>
                </label>
                <label className="full-span">
                  URL
                  <input value={artifactExternalUrl} onChange={(event) => setArtifactExternalUrl(event.target.value)} />
                </label>
                <label className="full-span">
                  Notes
                  <textarea rows={4} value={artifactNotes} onChange={(event) => setArtifactNotes(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "milestone" ? (
              <div className="form-grid">
                <label>
                  Kind
                  <select value={milestoneKind} onChange={(event) => setMilestoneKind(event.target.value)}>
                    <option value="">Select</option>
                    <option value="checkpoint">Checkpoint</option>
                    <option value="presentation">Presentation</option>
                    <option value="submission">Submission</option>
                    <option value="review">Review</option>
                    <option value="defense">Defense</option>
                  </select>
                </label>
                <label>
                  Label
                  <input value={milestoneLabel} onChange={(event) => setMilestoneLabel(event.target.value)} />
                </label>
                {hasProjectDeadlines ? (
                  <label>
                    Due
                    <input type="date" value={milestoneDueAt} onChange={(event) => setMilestoneDueAt(event.target.value)} />
                  </label>
                ) : null}
                <label>
                  Status
                  <select value={milestoneStatus} onChange={(event) => setMilestoneStatus(event.target.value)}>
                    <option value="pending">pending</option>
                    <option value="completed">completed</option>
                    <option value="missed">missed</option>
                  </select>
                </label>
              </div>
            ) : null}

            {modal === "blocker" ? (
              <div className="form-grid">
                <label>
                  Title
                  <input value={blockerTitle} onChange={(event) => setBlockerTitle(event.target.value)} />
                </label>
                <label>
                  Severity
                  <select value={blockerSeverity} onChange={(event) => setBlockerSeverity(event.target.value)}>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select>
                </label>
                <label>
                  Status
                  <select value={blockerStatus} onChange={(event) => setBlockerStatus(event.target.value)}>
                    <option value="open">open</option>
                    <option value="monitoring">monitoring</option>
                    <option value="resolved">resolved</option>
                  </select>
                </label>
                <label>
                  Source
                  <input value={blockerDetectedFrom} onChange={(event) => setBlockerDetectedFrom(event.target.value)} />
                </label>
                <label className="full-span">
                  Description
                  <textarea rows={5} value={blockerDescription} onChange={(event) => setBlockerDescription(event.target.value)} />
                </label>
              </div>
            ) : null}

            {modal === "report" ? (
              <div className="teaching-report-editor-stack">
                <div className="form-grid">
                  <label>
                    Report Date
                    <input type="date" value={reportDate} onChange={(event) => setReportDate(event.target.value)} />
                  </label>
                  <label>
                    Meeting Date
                    <input type="date" value={reportMeetingDate} onChange={(event) => setReportMeetingDate(event.target.value)} />
                  </label>
                </div>
                <div className="card teaching-editor-card">
                  <div className="proposal-card-head">
                    <strong>Attachments</strong>
                  </div>
                  <div className="teaching-upload-row">
                    <input type="file" onChange={(event) => setReportUploadFile(event.target.files?.[0] || null)} />
                    <button type="button" className="ghost" onClick={() => void handleReportUpload()} disabled={!reportUploadFile || reportUploading}>
                      {reportUploading ? "Uploading..." : "Upload"}
                    </button>
                  </div>
                  {reportAttachmentDocumentKeys.length ? (
                    <div className="teaching-attachment-list">
                      {reportAttachmentDocumentKeys.map((documentKey) => (
                        <div key={documentKey} className="teaching-attachment-chip">
                          <span className="chip small">
                            <FontAwesomeIcon icon={faPaperclip} /> {documentMap.get(documentKey)?.title || documentKey.slice(0, 8)}
                          </span>
                          <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => removeReportAttachment(documentKey)}>
                            <FontAwesomeIcon icon={faXmark} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="teaching-empty">No attachments</div>
                  )}
                </div>
                <div className="card teaching-editor-card">
                  <div className="proposal-card-head">
                    <strong>Transcripts</strong>
                  </div>
                  <div className="teaching-upload-row">
                    <input type="file" onChange={(event) => setReportTranscriptUploadFile(event.target.files?.[0] || null)} />
                    <button type="button" className="ghost" onClick={() => void handleTranscriptUpload()} disabled={!reportTranscriptUploadFile || reportTranscriptUploading}>
                      {reportTranscriptUploading ? "Uploading..." : "Upload"}
                    </button>
                  </div>
                  {reportTranscriptDocumentKeys.length ? (
                    <div className="teaching-attachment-list">
                      {reportTranscriptDocumentKeys.map((documentKey) => (
                        <div key={documentKey} className="teaching-attachment-chip">
                          <span className="chip small">
                            Transcript · {documentMap.get(documentKey)?.title || documentKey.slice(0, 8)}
                          </span>
                          <button type="button" className="ghost docs-action-btn" title="Remove" onClick={() => removeReportTranscript(documentKey)}>
                            <FontAwesomeIcon icon={faXmark} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="teaching-empty">No transcripts</div>
                  )}
                </div>
                <div className="card teaching-editor-card">
                  <div className="delivery-tabs teaching-report-tabs">
                    <button
                      type="button"
                      className={`delivery-tab ${reportEditorTab === "work_done" ? "active" : ""}`}
                      onClick={() => setReportEditorTab("work_done")}
                    >
                      Work Done
                    </button>
                    <button
                      type="button"
                      className={`delivery-tab ${reportEditorTab === "next_steps" ? "active" : ""}`}
                      onClick={() => setReportEditorTab("next_steps")}
                    >
                      Next Steps
                    </button>
                    <button
                      type="button"
                      className={`delivery-tab ${reportEditorTab === "supervisor_feedback" ? "active" : ""}`}
                      onClick={() => setReportEditorTab("supervisor_feedback")}
                    >
                      Supervisor Feedback
                    </button>
                  </div>
                  {reportEditorTab === "work_done" ? (
                    <ProposalRichEditor
                      value={reportWorkDone}
                      onChange={setReportWorkDone}
                      placeholder="Work done"
                    />
                  ) : null}
                  {reportEditorTab === "next_steps" ? (
                    <ProposalRichEditor
                      value={reportNextSteps}
                      onChange={setReportNextSteps}
                      placeholder="Next steps"
                    />
                  ) : null}
                  {reportEditorTab === "supervisor_feedback" ? (
                    <ProposalRichEditor
                      value={reportSupervisorFeedback}
                      onChange={setReportSupervisorFeedback}
                      placeholder="Supervisor feedback"
                    />
                  ) : null}
                </div>
                <div className="card teaching-editor-card">
                  <div className="proposal-card-head">
                    <strong>Blockers</strong>
                    <button type="button" className="ghost" onClick={addReportBlockerDraft} disabled={!reportBlockerTitle.trim()}>
                      Add
                    </button>
                  </div>
                  <div className="teaching-report-blockers">
                    {reportBlockers.map((item, index) => (
                      <div key={item.id || `${item.title}-${index}`} className="teaching-report-blocker-card">
                        <div className="teaching-report-blocker-row">
                          <label className="teaching-report-blocker-field teaching-report-blocker-field-title">
                            Title
                            <input value={item.title} onChange={(event) => updateReportBlockerDraft(index, { title: event.target.value })} />
                          </label>
                          <label className="teaching-report-blocker-field">
                            Severity
                            <select value={item.severity} onChange={(event) => updateReportBlockerDraft(index, { severity: event.target.value })}>
                              <option value="low">low</option>
                              <option value="medium">medium</option>
                              <option value="high">high</option>
                            </select>
                          </label>
                          <label className="teaching-report-blocker-field">
                            Status
                            <select value={item.status} onChange={(event) => updateReportBlockerDraft(index, { status: event.target.value })}>
                              <option value="open">open</option>
                              <option value="monitoring">monitoring</option>
                              <option value="resolved">resolved</option>
                            </select>
                          </label>
                        </div>
                        <label className="teaching-report-blocker-description">
                          Description
                          <textarea rows={3} value={item.description} onChange={(event) => updateReportBlockerDraft(index, { description: event.target.value })} />
                        </label>
                        <div className="row-actions">
                          <button type="button" className="ghost danger" onClick={() => removeReportBlockerDraft(index)}>Remove</button>
                        </div>
                      </div>
                    ))}
                    <div className="teaching-report-blocker-card">
                      <div className="teaching-report-blocker-row">
                        <label className="teaching-report-blocker-field teaching-report-blocker-field-title">
                          Title
                          <input value={reportBlockerTitle} onChange={(event) => setReportBlockerTitle(event.target.value)} />
                        </label>
                        <label className="teaching-report-blocker-field">
                          Severity
                          <select value={reportBlockerSeverity} onChange={(event) => setReportBlockerSeverity(event.target.value)}>
                            <option value="low">low</option>
                            <option value="medium">medium</option>
                            <option value="high">high</option>
                          </select>
                        </label>
                        <label className="teaching-report-blocker-field">
                          Status
                          <select value={reportBlockerStatus} onChange={(event) => setReportBlockerStatus(event.target.value)}>
                            <option value="open">open</option>
                            <option value="monitoring">monitoring</option>
                            <option value="resolved">resolved</option>
                          </select>
                        </label>
                      </div>
                      <label className="teaching-report-blocker-description">
                        Description
                        <textarea rows={3} value={reportBlockerDescription} onChange={(event) => setReportBlockerDescription(event.target.value)} />
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
