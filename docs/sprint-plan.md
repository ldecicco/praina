# MVP Sprint Plan

## Sprint 1: Foundations and Onboarding
- Implement core entities and relational constraints.
- Build onboarding flow APIs: consortium, structure, assignments, validation, activation.
- Enforce assignment rule: leader organization + responsible person.
- Create immutable baseline `v1` on activation.

## Sprint 2: Documents and Cited Assistant
- Build document ingestion API and metadata confirmation flow.
- Index document chunks and embeddings in `pgvector`.
- Implement scoped retrieval with citations.
- Expose assistant query endpoint with evidence payload.

## Sprint 3: Governance and Coherence
- Implement deliverable lifecycle workflow.
- Add cross-deliverable coherence checks.
- Implement ChatOps propose-confirm-apply flow.
- Implement append-only audit log APIs and timeline views.

## Sprint 4: Collaboration and Meetings
- Add user-to-user project chat (collaborative chat between project members).
- Ingest user-to-user project chat exchanges into the project knowledge base.
- Add meeting notes management with structured storage and retrieval.
- Add meeting scheduling in project calendar.
- Add invitation sending for meeting participants.
