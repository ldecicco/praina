export type Project = {
  id: string;
  code: string;
  title: string;
  description: string | null;
  start_date: string;
  duration_months: number;
  reporting_dates: string[];
  baseline_version: number;
  status: string;
  language: string;
  project_mode: "proposal" | "execution";
  project_kind: "funded" | "research" | "teaching" | string;
  coordinator_partner_id: string | null;
  principal_investigator_id: string | null;
  proposal_template_id: string | null;
};

export type Course = {
  id: string;
  code: string;
  title: string;
  description: string | null;
  is_active: boolean;
  has_project_deadlines: boolean;
  teacher: CourseStaffUser | null;
  teaching_assistants: CourseStaffUser[];
  materials: CourseMaterial[];
  created_at: string;
  updated_at: string;
};

export type CourseStaffUser = {
  user_id: string;
  display_name: string;
  email: string;
};

export type CourseMaterial = {
  id: string;
  course_id: string;
  material_type: string;
  title: string;
  content_markdown: string | null;
  external_url: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectProfile = {
  id: string;
  project_id: string;
  course_id: string | null;
  course_code: string | null;
  course_title: string | null;
  academic_year: string | null;
  term: string | null;
  functional_objectives_markdown: string | null;
  specifications_markdown: string | null;
  responsible_user_id: string | null;
  responsible_user: CourseStaffUser | null;
  status: string;
  health: string;
  reporting_cadence_days: number;
  final_grade: number | null;
  finalized_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectStudent = {
  id: string;
  project_id: string;
  full_name: string;
  email: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectArtifact = {
  id: string;
  project_id: string;
  artifact_type: string;
  label: string;
  required: boolean;
  status: string;
  document_key: string | null;
  external_url: string | null;
  notes: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectBackgroundMaterial = {
  id: string;
  project_id: string;
  material_type: string;
  title: string;
  bibliography_reference_id: string | null;
  bibliography_title: string | null;
  bibliography_url: string | null;
  bibliography_attachment_filename: string | null;
  document_key: string | null;
  external_url: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingProgressReport = {
  id: string;
  project_id: string;
  report_date: string | null;
  meeting_date: string | null;
  work_done_markdown: string;
  next_steps_markdown: string;
  blockers: TeachingProjectBlocker[];
  supervisor_feedback_markdown: string | null;
  attachment_document_keys: string[];
  transcript_document_keys: string[];
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectMilestone = {
  id: string;
  project_id: string;
  kind: string;
  label: string;
  due_at: string | null;
  completed_at: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectAssessment = {
  id: string;
  project_id: string;
  grade: number | null;
  strengths_markdown: string | null;
  weaknesses_markdown: string | null;
  grading_rationale_markdown: string | null;
  grader_user_id: string | null;
  graded_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingProjectBlocker = {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  severity: string;
  status: string;
  detected_from: string | null;
  opened_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingWorkspace = {
  profile: TeachingProjectProfile;
  students: TeachingProjectStudent[];
  artifacts: TeachingProjectArtifact[];
  background_materials: TeachingProjectBackgroundMaterial[];
  progress_reports: TeachingProgressReport[];
  milestones: TeachingProjectMilestone[];
  blockers: TeachingProjectBlocker[];
  assessment: TeachingProjectAssessment | null;
};

export type ResourceOwner = {
  user_id: string;
  display_name: string;
  email: string;
};

export type LabStaffAssignment = {
  id: string;
  lab_id: string;
  user_id: string;
  role: string;
  user: ResourceOwner;
  created_at: string;
  updated_at: string;
};

export type Lab = {
  id: string;
  name: string;
  building: string | null;
  room: string | null;
  notes: string | null;
  responsible_user_id: string | null;
  responsible: ResourceOwner | null;
  staff: LabStaffAssignment[];
  is_active: boolean;
  equipment_count: number;
  created_at: string;
  updated_at: string;
};

export type LabClosure = {
  id: string;
  lab_id: string;
  start_at: string;
  end_at: string;
  reason: string;
  notes: string | null;
  created_by_user_id: string | null;
  cancelled_booking_count: number;
  lab: Lab;
  created_at: string;
  updated_at: string;
};

export type Equipment = {
  id: string;
  name: string;
  category: string | null;
  model: string | null;
  serial_number: string | null;
  description: string | null;
  location: string | null;
  lab_id: string | null;
  lab: Lab | null;
  owner_user_id: string | null;
  owner: ResourceOwner | null;
  status: string;
  usage_mode: string;
  access_notes: string | null;
  booking_notes: string | null;
  maintenance_notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type EquipmentMaterial = {
  id: string;
  equipment_id: string;
  material_type: string;
  title: string;
  external_url: string | null;
  attachment_filename: string | null;
  attachment_url: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type EquipmentRequirement = {
  id: string;
  project_id: string;
  equipment_id: string;
  priority: string;
  purpose: string;
  notes: string | null;
  created_by_user_id: string | null;
  equipment: Equipment;
  created_at: string;
  updated_at: string;
};

export type EquipmentBooking = {
  id: string;
  equipment_id: string;
  project_id: string;
  requester_user_id: string | null;
  approved_by_user_id: string | null;
  start_at: string;
  end_at: string;
  status: string;
  purpose: string;
  notes: string | null;
  equipment: Equipment;
  requester: ResourceOwner | null;
  approver: ResourceOwner | null;
  created_at: string;
  updated_at: string;
};

export type EquipmentDowntime = {
  id: string;
  equipment_id: string;
  start_at: string;
  end_at: string;
  reason: string;
  notes: string | null;
  created_by_user_id: string | null;
  equipment: Equipment;
  created_at: string;
  updated_at: string;
};

export type EquipmentBlocker = {
  id: string;
  project_id: string;
  equipment_id: string;
  booking_id: string | null;
  started_at: string;
  ended_at: string | null;
  blocked_days: number;
  reason: string;
  status: string;
  equipment: Equipment;
  created_at: string;
  updated_at: string;
};

export type EquipmentConflict = {
  equipment_id: string;
  equipment_name: string;
  conflict_type: string;
  booking_id: string | null;
  conflicting_booking_id: string | null;
  downtime_id: string | null;
  project_id: string | null;
  conflicting_project_id: string | null;
  start_at: string;
  end_at: string;
  detail: string;
};

export type ProjectResourcesWorkspace = {
  requirements: EquipmentRequirement[];
  bookings: EquipmentBooking[];
  blockers: EquipmentBlocker[];
};

export type Partner = {
  id: string;
  project_id: string;
  short_name: string;
  legal_name: string;
  partner_type: string;
  country: string | null;
  expertise: string | null;
};

export type Member = {
  id: string;
  project_id: string;
  partner_id: string;
  user_account_id: string | null;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  temporary_password?: string | null;
};

export type WorkEntity = {
  id: string;
  project_id: string;
  code: string;
  title: string;
  description: string | null;
  wp_id: string | null;
  wp_ids: string[];
  start_month: number | null;
  end_month: number | null;
  due_month: number | null;
  execution_status: string | null;
  completed_at: string | null;
  completed_by_member_id: string | null;
  completion_note: string | null;
  workflow_status: string | null;
  review_due_month: number | null;
  review_owner_member_id: string | null;
  is_trashed: boolean;
  trashed_at: string | null;
  leader_organization_id: string;
  responsible_person_id: string;
  collaborating_partner_ids: string[];
};

export type TrashedWorkEntity = {
  entity_type: "work_package" | "task" | "milestone" | "deliverable" | string;
  entity: WorkEntity;
};

export type AssignmentMatrixRow = {
  entity_type: "work_package" | "task" | "milestone" | "deliverable";
  entity_id: string;
  code: string;
  title: string;
  wp_id: string | null;
  leader_organization_id: string;
  responsible_person_id: string;
  collaborating_partner_ids: string[];
};

export type DocumentListItem = {
  latest_document_id: string;
  document_key: string;
  project_id: string;
  scope: "project" | "wp" | "task" | "deliverable" | "milestone";
  title: string;
  status: "uploaded" | "indexed" | "failed" | string;
  latest_version: number;
  versions_count: number;
  wp_id: string | null;
  task_id: string | null;
  deliverable_id: string | null;
  milestone_id: string | null;
  uploaded_by_member_id: string | null;
  indexed_at: string | null;
  ingestion_error: string | null;
  source_url: string | null;
  source_type: string | null;
  proposal_section_id: string | null;
  updated_at: string;
};

export type DocumentVersion = {
  id: string;
  document_key: string;
  project_id: string;
  scope: "project" | "wp" | "task" | "deliverable" | "milestone";
  title: string;
  storage_uri: string;
  original_filename: string;
  file_size_bytes: number;
  mime_type: string;
  status: "uploaded" | "indexed" | "failed" | string;
  version: number;
  metadata_json: Record<string, unknown>;
  wp_id: string | null;
  task_id: string | null;
  deliverable_id: string | null;
  milestone_id: string | null;
  uploaded_by_member_id: string | null;
  indexed_at: string | null;
  ingestion_error: string | null;
  source_url: string | null;
  source_type: string | null;
  proposal_section_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ProposalTemplateSection = {
  id: string;
  template_id: string;
  key: string;
  title: string;
  guidance: string | null;
  position: number;
  required: boolean;
  scope_hint: string;
  created_at: string;
  updated_at: string;
};

export type ProposalTemplate = {
  id: string;
  call_library_entry_id: string | null;
  name: string;
  funding_program: string;
  description: string | null;
  is_active: boolean;
  sections: ProposalTemplateSection[];
  created_at: string;
  updated_at: string;
};

export type ProjectProposalSection = {
  id: string;
  project_id: string;
  template_section_id: string | null;
  key: string;
  title: string;
  guidance: string | null;
  position: number;
  required: boolean;
  scope_hint: string;
  status: string;
  owner_member_id: string | null;
  reviewer_member_id: string | null;
  due_date: string | null;
  notes: string | null;
  content: string | null;
  has_collab_state: boolean;
  linked_documents_count: number;
  created_at: string;
  updated_at: string;
};

export type ProposalCallBrief = {
  id: string | null;
  project_id: string;
  source_call_id: string | null;
  source_version: number | null;
  copied_by_user_id: string | null;
  copied_at: string | null;
  call_title: string | null;
  funder_name: string | null;
  programme_name: string | null;
  reference_code: string | null;
  submission_deadline: string | null;
  source_url: string | null;
  summary: string | null;
  eligibility_notes: string | null;
  budget_notes: string | null;
  scoring_notes: string | null;
  requirements_text: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ProposalCallLibraryEntry = {
  id: string;
  call_title: string;
  funder_name: string | null;
  programme_name: string | null;
  reference_code: string | null;
  submission_deadline: string | null;
  source_url: string | null;
  summary: string | null;
  eligibility_notes: string | null;
  budget_notes: string | null;
  scoring_notes: string | null;
  requirements_text: string | null;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ProposalCallLibraryDocument = {
  id: string;
  library_entry_id: string;
  original_filename: string;
  category: string;
  status: string;
  indexing_status: string;
  mime_type: string;
  file_size_bytes: number;
  storage_path: string;
  extracted_text: string | null;
  indexed_at: string | null;
  ingestion_error: string | null;
  created_at: string;
  updated_at: string;
};

export type ProposalCallDocumentReindexResult = {
  document_id: string;
  status: string;
  chunks_indexed: number;
  queued: boolean;
  error: string | null;
};

export type ProposalCallIngestJob = {
  id: string;
  library_entry_id: string;
  document_id: string;
  created_by_user_id: string | null;
  status: string;
  stage: string;
  progress_current: number;
  progress_total: number | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  stream_text: string | null;
  created_at: string;
  updated_at: string;
};

export type ProposalCallAnswerCitation = {
  library_entry_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  snippet: string;
  score: number;
};

export type ProposalCallAnswerDebug = {
  library_entry_id: string;
  document_id: string;
  document_title: string;
  chunk_index: number;
  snippet: string;
  score: number;
  lexical_score: number;
  vector_score: number;
  combined_score: number;
};

export type ProposalCallAnswer = {
  answer: string;
  grounded: boolean;
  insufficient_reason: string | null;
  citations: ProposalCallAnswerCitation[];
  retrieval_debug: ProposalCallAnswerDebug[];
};

export type ProposalSubmissionItem = {
  id: string;
  project_id: string;
  requirement_id: string;
  partner_id: string | null;
  assignee_member_id: string | null;
  status: string;
  latest_uploaded_document_id: string | null;
  submitted_at: string | null;
  notes: string | null;
  partner_name: string | null;
  assignee_name: string | null;
  latest_uploaded_document_title: string | null;
  created_at: string;
  updated_at: string;
};

export type ProposalSubmissionRequirement = {
  id: string;
  project_id: string;
  template_id: string | null;
  title: string;
  description: string | null;
  document_type: string;
  format_hint: string;
  required: boolean;
  position: number;
  items: ProposalSubmissionItem[];
  created_at: string;
  updated_at: string;
};

export type ProposalReviewFinding = {
  id: string;
  project_id: string;
  proposal_section_id: string | null;
  review_kind: string;
  finding_type: string;
  status: string;
  source: string;
  scope: string;
  summary: string;
  details: string | null;
  anchor_text: string | null;
  anchor_prefix: string | null;
  anchor_suffix: string | null;
  start_offset: number | null;
  end_offset: number | null;
  created_by_member_id: string | null;
  parent_finding_id: string | null;
  created_by_display_name: string | null;
  replies: ProposalReviewFinding[];
  created_at: string;
  updated_at: string;
};

export type ProposalImage = {
  id: string;
  url: string;
};

export type DocumentVersionList = {
  document_key: string;
  versions: DocumentVersion[];
};

export type ReindexResult = {
  document_id: string;
  status: string;
  chunks_indexed: number;
  queued: boolean;
  error: string | null;
};

export type Paginated<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type ChatCitation = {
  source_type?: string | null;
  document_id: string;
  document_key: string;
  title: string;
  version: number;
  chunk_index: number;
  snippet: string;
};

export type ChatCard = {
  type: string;
  title: string;
  body: string;
  action_label: string | null;
  action_prompt: string | null;
};

export type ChatConversation = {
  id: string;
  project_id: string;
  title: string;
  created_by_member_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  project_id: string;
  role: "user" | "assistant" | "system" | string;
  content: string;
  citations: ChatCitation[];
  cards: ChatCard[];
  created_by_member_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatMessageExchange = {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  platform_role: "super_admin" | "user" | string;
  is_active: boolean;
  can_access_research: boolean;
  can_access_teaching: boolean;
  temporary_password?: string | null;
  job_title: string | null;
  organization: string | null;
  phone: string | null;
  avatar_url: string | null;
  telegram_linked: boolean;
  telegram_notifications_enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type TelegramLinkState = {
  linked: boolean;
  notifications_enabled: boolean;
  bot_username: string | null;
  chat_id: string | null;
  pending_chat_id: string | null;
  telegram_username: string | null;
  telegram_first_name: string | null;
  pending_code: string | null;
  pending_code_expires_at: string | null;
};

export type TelegramDiscoveryStart = {
  code: string;
  expires_at: string;
  bot_username: string | null;
  start_url: string | null;
};

export type ProjectMembership = {
  id: string;
  project_id: string;
  user_id: string;
  role: "project_owner" | "project_manager" | "partner_lead" | "partner_member" | "reviewer" | "viewer" | string;
  created_at: string;
  updated_at: string;
};

export type MembershipWithUser = {
  membership: ProjectMembership;
  user: AuthUser;
};

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in_seconds: number;
};

export type MeResponse = {
  user: AuthUser;
  memberships: ProjectMembership[];
};

export type ProjectChatRoom = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  scope_type: string;
  scope_ref_id: string | null;
  is_archived: boolean;
  member_user_ids: string[];
  created_at: string;
  updated_at: string;
};

export type ProjectChatMessage = {
  id: string;
  project_id: string;
  room_id: string;
  sender_user_id: string;
  sender_display_name: string;
  content: string;
  reply_to_message_id: string | null;
  reply_to_message: {
    id: string;
    sender_user_id: string;
    sender_display_name: string;
    content: string;
    deleted_at: string | null;
    created_at: string;
  } | null;
  reactions: Array<{
    emoji: string;
    count: number;
    user_ids: string[];
  }>;
  edited_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type StudyChatRoom = {
  project_id: string;
  room_id: string;
  room_name: string;
  member_user_ids: string[];
};

export type StudyChatReaction = {
  emoji: string;
  count: number;
  user_ids: string[];
};

export type StudyChatReplyPreview = {
  id: string;
  sender_user_id: string;
  sender_display_name: string;
  content: string;
  deleted_at: string | null;
  created_at: string;
};

export type StudyChatMessage = {
  id: string;
  collection_id: string;
  sender_user_id: string;
  sender_display_name: string;
  content: string;
  reply_to_message_id: string | null;
  reply_to_message: StudyChatReplyPreview | null;
  reactions: StudyChatReaction[];
  edited_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectBroadcast = {
  id: string;
  project_id: string | null;
  lab_id?: string | null;
  author_user_id: string;
  author_display_name: string;
  title: string;
  body: string;
  severity: "info" | "important" | "urgent" | string;
  deliver_telegram: boolean;
  recipient_count: number;
  sent_at: string;
  created_at: string;
  updated_at: string;
};

export type ProjectValidationError = {
  entity_type: string;
  entity_id: string;
  code: string;
  message: string;
};

export type ProjectValidationResult = {
  valid: boolean;
  errors: ProjectValidationError[];
  warnings: ProjectValidationError[];
};

export type ProjectActivationResult = {
  project_id: string;
  status: string;
  baseline_version: number;
  audit_event_id: string;
};

export type AuditEvent = {
  id: string;
  project_id: string;
  actor_id: string | null;
  actor_name: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ProjectRisk = {
  id: string;
  project_id: string;
  code: string;
  title: string;
  description: string | null;
  mitigation_plan: string | null;
  status: string;
  probability: string;
  impact: string;
  due_month: number | null;
  owner_partner_id: string;
  owner_member_id: string;
  created_at: string;
  updated_at: string;
};


export type MeetingRecord = {
  id: string;
  project_id: string;
  title: string;
  starts_at: string;
  source_type: "minutes" | "transcript" | string;
  source_url: string | null;
  participants: string[];
  content_text: string;
  summary: string | null;
  external_calendar_event_id: string | null;
  import_batch_id: string | null;
  indexing_status: string;
  original_filename: string | null;
  linked_document_id: string | null;
  created_by_member_id: string | null;
  created_at: string;
  updated_at: string;
};

export type MeetingActionItem = {
  id: string;
  project_id: string;
  meeting_id: string;
  description: string;
  assignee_name: string | null;
  assignee_member_id: string | null;
  due_date: string | null;
  priority: string;
  status: string;
  source: string;
  linked_task_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type CalendarIntegration = {
  id: string;
  project_id: string;
  provider: string;
  connected_account_email: string | null;
  token_expires_at: string | null;
  last_synced_at: string | null;
  sync_status: string;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type CalendarImportBatch = {
  id: string;
  project_id: string;
  filename: string;
  imported_count: number;
  updated_count: number;
  created_at: string;
  updated_at: string;
};


export type CoherenceIssue = {
  category: string;
  entity_ids: string[];
  message: string;
  suggestion: string;
  severity: string;
};

export type CoherenceReport = {
  project_id: string;
  issues: CoherenceIssue[];
  checked_at: string;
};

export type ReviewFinding = {
  id: string;
  project_id: string;
  deliverable_id: string;
  document_id: string | null;
  finding_type: string;
  status: string;
  source: string;
  section_ref: string | null;
  summary: string;
  details: string | null;
  created_by_member_id: string | null;
  created_at: string;
  updated_at: string;
};

export type DashboardHealth = {
  scope_type: string;
  scope_ref_id: string | null;
  validation_error_details: DashboardHealthIssue[];
  validation_warning_details: DashboardHealthIssue[];
  coherence_issue_details: DashboardHealthIssue[];
  validation_errors: number;
  validation_warnings: number;
  coherence_issues: number;
  action_items_pending: number;
  risks_open: number;
  overdue_deliverables: number;
  health_score: "green" | "yellow" | "red" | string;
};

export type DashboardHealthIssue = {
  issue_key: string;
  source: string;
  severity: string;
  category: string;
  entity_type: string | null;
  entity_id: string | null;
  message: string;
  suggestion: string | null;
  status: string;
  snoozed_until: string | null;
  rationale: string | null;
  primary_action: {
    type: string;
    label: string;
    view?: string | null;
  } | null;
};

export type ProjectInboxItem = {
  id: string;
  project_id: string;
  title: string;
  details: string | null;
  status: string;
  priority: string;
  source_type: string;
  source_key: string | null;
  assignee_member_id: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectTodo = {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  creator_member_id: string | null;
  assignee_member_id: string | null;
  wp_id: string | null;
  task_id: string | null;
  due_date: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type DashboardHealthSnapshot = {
  id: string;
  health_score: "green" | "yellow" | "red" | string;
  validation_errors: number;
  validation_warnings: number;
  coherence_issues: number;
  action_items_pending: number;
  risks_open: number;
  overdue_deliverables: number;
  created_at: string;
};

export type DashboardRecurringIssue = {
  issue_key: string;
  category: string;
  count: number;
  message: string;
};

export type DashboardScopeOption = {
  id: string;
  label: string;
};

export type DashboardScopeOptions = {
  work_packages: DashboardScopeOption[];
  tasks: DashboardScopeOption[];
  deliverables: DashboardScopeOption[];
  milestones: DashboardScopeOption[];
};

export type MyWorkItem = {
  item_type: string;
  entity_id: string;
  project_id: string;
  project_code: string;
  project_title: string;
  code: string | null;
  title: string;
  status: string;
  role: string;
  priority: string | null;
  due_date: string | null;
  due_month: number | null;
};

export type MyWorkProjectGroup = {
  project_id: string;
  project_code: string;
  project_title: string;
  project_mode: string;
  items: MyWorkItem[];
};

export type MyWorkResponse = {
  groups: MyWorkProjectGroup[];
  total_items: number;
};

export type SearchResultItem = {
  source_type: string;
  source_id: string;
  source_key: string;
  title: string;
  version: number;
  chunk_index: number;
  content: string;
  score: number;
};

export type SearchResponse = {
  query: string;
  results: SearchResultItem[];
  total: number;
};

export type AppNotification = {
  id: string;
  user_id: string;
  project_id: string | null;
  channel: string;
  status: string;
  title: string;
  body: string;
  link_type: string | null;
  link_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ResearchSpace = {
  id: string;
  title: string;
  focus: string | null;
  linked_project_id: string | null;
  owner_user_id: string;
  created_at: string;
  updated_at: string;
};

// ── Research Workspace ────────────────────────────────────────────────

export type ResearchCollection = {
  id: string;
  research_space_id: string | null;
  project_id: string | null;
  title: string;
  description: string | null;
  hypothesis: string | null;
  open_questions: string[];
  status: string;
  tags: string[];
  overleaf_url: string | null;
  paper_motivation: string | null;
  target_output_title: string | null;
  target_venue: string | null;
  registration_deadline: string | null;
  submission_deadline: string | null;
  decision_date: string | null;
  study_iterations: ResearchStudyIteration[];
  study_results: ResearchStudyResult[];
  paper_authors: ResearchPaperAuthor[];
  paper_questions: ResearchPaperQuestion[];
  paper_claims: ResearchPaperClaim[];
  paper_sections: ResearchPaperSection[];
  output_status: string;
  created_by_member_id: string | null;
  ai_synthesis: string | null;
  ai_synthesis_at: string | null;
  reference_count: number;
  note_count: number;
  member_count: number;
  created_at: string;
  updated_at: string;
};

export type ResearchPaperQuestion = {
  id: string;
  text: string;
  note_ids: string[];
};

export type ResearchPaperAuthor = {
  id: string;
  member_id: string;
  display_name: string;
  is_corresponding: boolean;
};

export type ResearchStudyIteration = {
  id: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  note_ids: string[];
  reference_ids: string[];
  file_ids: string[];
  result_ids: string[];
  summary: string | null;
  what_changed: string[];
  improvements: string[];
  regressions: string[];
  unclear_points: string[];
  next_actions: string[];
  user_comments: string | null;
  reviewed_at: string | null;
};

export type ResearchStudyResult = {
  id: string;
  iteration_id: string | null;
  title: string;
  note_ids: string[];
  reference_ids: string[];
  file_ids: string[];
  summary: string | null;
  what_changed: string[];
  improvements: string[];
  regressions: string[];
  unclear_points: string[];
  next_actions: string[];
  user_comments: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ResearchResultComparison = {
  summary: string;
  likely_improvements: string[];
  likely_regressions: string[];
  likely_causes: string[];
  next_experiment_changes: string[];
  compared_result_ids: string[];
};

export type ResearchPaperClaim = {
  id: string;
  text: string;
  question_ids: string[];
  reference_ids: string[];
  note_ids: string[];
  result_ids: string[];
  file_ids: string[];
  status: string;
  audit_status: string | null;
  audit_summary: string | null;
  supporting_reference_ids: string[];
  supporting_note_ids: string[];
  missing_evidence: string[];
  audit_confidence: number | null;
  audited_at: string | null;
};

export type ResearchPaperSection = {
  id: string;
  title: string;
  question_ids: string[];
  claim_ids: string[];
  reference_ids: string[];
  note_ids: string[];
  result_ids: string[];
  file_ids: string[];
  status: string;
};

export type ResearchCollectionMeeting = {
  id: string;
  title: string;
  starts_at: string;
  source_type: string;
  summary: string | null;
};

export type ResearchCollectionDetail = ResearchCollection & {
  members: ResearchCollectionMember[];
  wp_ids: string[];
  task_ids: string[];
  deliverable_ids: string[];
  meetings: ResearchCollectionMeeting[];
};

export type ResearchCollectionMember = {
  id: string;
  member_id: string;
  user_id: string | null;
  member_name: string;
  organization_short_name: string;
  avatar_url: string | null;
  role: string;
  created_at: string;
  updated_at: string;
};

export type ResearchReference = {
  id: string;
  research_space_id: string | null;
  project_id: string | null;
  bibliography_reference_id: string | null;
  collection_id: string | null;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  url: string | null;
  abstract: string | null;
  document_key: string | null;
  tags: string[];
  bibliography_visibility: string | null;
  bibliography_attachment_filename: string | null;
  bibliography_attachment_url: string | null;
  reading_status: string;
  added_by_member_id: string | null;
  ai_summary: string | null;
  ai_summary_at: string | null;
  note_count: number;
  annotation_count: number;
  created_at: string;
  updated_at: string;
};

export type BibliographyReference = {
  id: string;
  source_project_id: string | null;
  document_key: string | null;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  doi: string | null;
  url: string | null;
  abstract: string | null;
  bibtex_raw: string | null;
  tags: string[];
  concepts: string[];
  visibility: string;
  created_by_user_id: string | null;
  attachment_filename: string | null;
  attachment_url: string | null;
  document_status: string | null;
  warning: string | null;
  linked_project_count: number;
  note_count: number;
  reading_status: string;
  ai_summary: string | null;
  ai_summary_at: string | null;
  semantic_evidence: BibliographySemanticEvidence[];
  created_at: string;
  updated_at: string;
};

export type BibliographySemanticEvidence = {
  text: string;
  similarity: number | null;
};

export type BibliographyDuplicateMatch = {
  match_reason: string;
  reference: BibliographyReference;
};

export type BibliographyGraphNode = {
  id: string;
  label: string;
  node_type:
    | "paper"
    | "author"
    | "concept"
    | "tag"
    | "bibliography_collection"
    | "research_collection"
    | "research_project"
    | "teaching_project"
    | string;
  ref_id: string | null;
};

export type BibliographyGraphEdge = {
  id: string;
  source: string;
  target: string;
  edge_type:
    | "written_by"
    | "mentions_concept"
    | "tagged"
    | "semantic"
    | "in_bibliography_collection"
    | "linked_to_research_collection"
    | "used_in_teaching_project"
    | "contains_collection"
    | string;
  weight: number | null;
};

export type BibliographyGraph = {
  nodes: BibliographyGraphNode[];
  edges: BibliographyGraphEdge[];
};

export type BibliographyIdentifierImportResult = {
  created: BibliographyReference[];
  reused: BibliographyReference[];
  errors: string[];
};

export type BibliographyCollection = {
  id: string;
  title: string;
  description: string | null;
  visibility: string;
  owner_user_id: string;
  reference_count: number;
  created_at: string;
  updated_at: string;
};

export type BibliographyNote = {
  id: string;
  bibliography_reference_id: string;
  user_id: string;
  user_display_name: string;
  content: string;
  note_type: string;
  visibility: string;
  created_at: string;
  updated_at: string;
};

export type BibliographyTag = {
  id: string;
  label: string;
  slug: string;
  created_at: string;
  updated_at: string;
};

export type ResearchNote = {
  id: string;
  research_space_id: string | null;
  project_id: string | null;
  collection_id: string | null;
  author_member_id: string | null;
  author_name: string | null;
  title: string;
  content: string;
  lane: string | null;
  note_type: string;
  tags: string[];
  linked_reference_ids: string[];
  linked_file_ids: string[];
  created_at: string;
  updated_at: string;
};

export type ResearchStudyFile = {
  id: string;
  research_space_id: string | null;
  project_id: string | null;
  collection_id: string;
  uploaded_by_user_id: string | null;
  uploaded_by_name: string | null;
  original_filename: string;
  mime_type: string | null;
  file_size_bytes: number;
  download_url: string | null;
  created_at: string;
  updated_at: string;
};
