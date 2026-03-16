# Project Proposal Component Plan

## Goal

Build a template-driven proposal management module that works across EU, national, and custom funding lines without hardcoding one structure.

## 1. Domain Model

Add a proposal layer separate from workplan entities.

Core entities:
- `ProposalTemplate`
- `ProposalTemplateSection`
- `ProjectProposalSection`

Responsibilities:
- `ProposalTemplate`: reusable funding-line structure
- `ProposalTemplateSection`: ordered section definitions inside a template
- `ProjectProposalSection`: instantiated section state for a specific project

Project linkage:
- Add `proposal_template_id` to `projects`
- Add `proposal_section_id` to `project_documents`

## 2. Backend API

Expose two API groups.

Template management:
- list templates
- get template
- create/update template
- create/update/delete template sections

Project proposal management:
- assign/unassign template to project
- list project proposal sections
- update project proposal section state

Document integration:
- allow uploads and linked Google Docs to target a `proposal_section_id`
- preserve proposal-section linkage across document versions and refreshes

## 3. Template Behavior

Define how templates apply to projects.

Rules:
- assigning a template creates `ProjectProposalSection` rows from template sections
- updating a template propagates structural changes to assigned projects
- removing a template from a project removes instantiated proposal sections
- project sections can store workflow state without changing the template

Template section fields:
- `key`
- `title`
- `guidance`
- `position`
- `required`
- `scope_hint`

## 4. Project Proposal Workspace

Create a dedicated project UI for proposal work.

Main capabilities:
- select current template
- view all instantiated sections
- set section status
- assign section owner
- assign section reviewer
- set due date
- edit notes
- see linked document count per section

Suggested statuses:
- `not_started`
- `drafting`
- `in_review`
- `changes_requested`
- `approved`
- `final`

## 5. Template Editor

Create an admin-facing template editor.

Capabilities:
- create funding-line templates
- define ordered sections
- edit section structure
- mark sections required/optional
- set scope hints
- activate/deactivate templates

This should be generic enough for:
- Horizon Europe
- regional calls
- ministry grants
- private foundation applications
- internal call-for-proposal formats

## 6. Document Workflow

Make documents part of proposal execution.

Support:
- upload section-specific files
- link Google Docs to proposal sections
- upload new versions without losing section linkage
- refresh linked Google Docs into new versions
- show section-linked document counts in the proposal workspace

## 7. Project Setup Integration

Extend project setup/settings so proposal structure is first-class.

Add:
- template selection in project creation/update
- proposal section instantiation when template is assigned
- template reassignment support

## 8. Validation and Readiness

Add proposal-specific readiness checks after the base workflow is stable.

Checks:
- no template assigned
- required sections missing owners
- required sections missing reviewers
- required sections missing linked documents
- overdue section due dates
- sections stuck in draft near submission

This should be proposal validation, separate from workplan validation.

## 9. Assistant Integration

Use the existing chat/document/coherence stack to support drafting.

Planned capabilities:
- summarize section status
- find sections with no evidence/docs
- compare section-linked docs against project structure
- suggest owners/reviewers
- flag stale documents or inconsistent narratives

## 10. Frontend Navigation

Add two views:
- `Proposal`
- `Templates`

Separation:
- `Proposal`: project-specific execution workspace
- `Templates`: reusable funding-line design workspace

## 11. Delivery Order

Recommended implementation sequence:

1. Migration and models
2. Schemas and services
3. Proposal routes
4. Project-template assignment flow
5. Document-section linkage
6. Proposal workspace UI
7. Template editor UI
8. Validation/readiness layer
9. Assistant/coherence integration

## 12. MVP Acceptance Criteria

The first complete version is done when:

- a super admin can create a template with sections
- a project can be assigned a template
- project proposal sections are created automatically
- owners/reviewers/status/due dates can be managed per section
- documents can be linked to proposal sections
- Google Docs can be linked and refreshed for those sections
- the proposal workspace shows section progress and linked docs
- template changes sync to assigned projects safely

## 13. Call Compliance

Add structured target-call context and a dedicated compliance review mode.

Implementation steps:
- DONE: add a project-level `ProposalCallBrief` model for structured call data
- DONE: expose API endpoints to read and update the call brief
- DONE: add a dedicated call-compliance review run powered by the proposal review service
- DONE: separate general review findings from `call_compliance` findings with `review_kind`
- DONE: add proposal workspace UI to edit call data and run section/proposal call checks

Next steps:
- import call data from uploaded source documents
- extract atomic requirements and scoring criteria from source material
- link findings to exact call passages and proposal passages
- add requirement-by-requirement coverage status instead of only freeform findings

## 14. Call Repository

Store calls centrally and let projects work on independent copies.

Implementation steps:
- DONE: add a shared `ProposalCallLibraryEntry` repository model
- DONE: keep project call briefs as local copies with `source_call_id`, `source_version`, `copied_at`, and `copied_by`
- DONE: link proposal templates to repository calls so templates live under a specific call
- DONE: add API endpoints to list, create, and update call library entries
- DONE: add API support to copy a repository call into a project
- DONE: add proposal workspace UI to browse the repository and copy a call into the project

Next steps:
- add dedicated admin screens for repository curation outside the proposal workspace
- support repository version comparison against a project copy
- DONE: ingest call PDFs and populate repository entries automatically

## 15. Proposal Onboarding Flow

Proposal-mode navigation should follow the coordinator's setup order.

Implementation steps:
- DONE: make `Call` the first proposal-mode navigation step
- DONE: remove `Templates` as a separate main proposal navigation item
- DONE: keep template selection inside the call flow
- DONE: disable later proposal-mode nav items until call and template setup are completed

Next steps:
- start the new proposal-project flow directly in the `Call` step
- replace the remaining project settings template selector with a call-scoped flow
- align the standalone template editor around an explicit call-first selection

## 16. Submission Package

Track the full set of documents required for proposal submission, not only the main proposal narrative.

Implementation steps:
- DONE: add `ProposalSubmissionRequirement` and `ProposalSubmissionItem` models for required submission documents and their tracked project instances
- DONE: support `project` and `per_partner` submission document types
- DONE: support `online` and `upload` format hints
- DONE: instantiate one tracked item per partner for `per_partner` requirements
- DONE: expose API endpoints to list/create/update submission requirements and update submission item state
- DONE: add a first-class `Submission` proposal-mode view
- DONE: add coordinator UI to define submission requirements and track items through `not_started`, `in_preparation`, `completed`, and `submitted`

Next steps:
- DONE: connect uploaded project documents directly to submission items
- allow partners to view and update only their assigned per-partner submission items
- add submission readiness checks to proposal review and final export flows
