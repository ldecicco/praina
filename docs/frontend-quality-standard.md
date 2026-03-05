# Frontend Quality Standard

## Product Bar
The frontend must match the quality level expected from established project management tools.

## Non-Negotiable Standards
- Consistent design system: spacing, typography, color, and component behavior
- Strong information hierarchy for dense project data
- Reliable responsiveness for desktop and mobile
- Fast perceived performance and clear loading/empty/error states
- Accessible interactions (keyboard navigation, focus states, contrast)

## UX Requirements
- Assignment workflows prevent invalid states by design.
- High-impact actions require confirmation with clear consequences.
- Tables and boards support filtering, sorting, and quick scan.
- Document views emphasize source traceability and version context.
- Audit and status changes are visible and easy to understand.

## UI Engineering Requirements
- Reusable component primitives (forms, tables, drawers, dialogs, badges)
- State patterns that avoid inconsistent UI behavior
- Strict linting and design token usage
- Visual regression checks on key screens

## Acceptance Criteria for MVP Screens
- Onboarding wizard: no ambiguous steps, no hidden validation errors
- Assignment matrix: invalid assignments impossible to submit
- Document library: easy upload, clear scope tagging, searchable list
- Assistant chat: citations always visible with direct evidence links
- Audit log: readable timeline with actor, action, target, timestamp

Detailed screen structure is documented in [Frontend IA (MVP)](/home/luca/dev/code/agentic-project-management/docs/frontend-ia-mvp.md).
Component-level contracts are documented in [Frontend Component Contracts](/home/luca/dev/code/agentic-project-management/docs/frontend-component-contracts.md).
