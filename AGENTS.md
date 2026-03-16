# Agent Rules

1. Never add subtitles, taglines, descriptive helper text, or marketing-style secondary headings in the UI.
2. Use only direct labels and actionable text for controls and sections.
3. Add explanatory subtitle text only if the user explicitly asks for it in that specific request.

## Repo Context

- Any UI implementation or modification MUST follow `frontend/DESIGN_GUIDELINES.md` exactly. This is a hard requirement for all frontend work in this repo.
- The research page is already wired into the main app as a first-class view, not a placeholder. See `frontend/src/App.tsx` for the `research` view registration, sidebar entry, and notification deep-link mapping.
- The main research UI lives in `frontend/src/components/ResearchWorkspace.tsx`. Current shipped UI supports:
  - collection list and selection
  - create, archive, delete collection
  - reference list with status filter, text search, manual add, BibTeX import, delete, AI summarize
  - note list with type filter, create, delete
  - collection overview with members and AI synthesis
- The backend research API is implemented in `backend/app/api/v1/routes/research.py` and covers collections, members, WBS links, references, notes, BibTeX import, reference summarization, PDF metadata extraction, and collection synthesis.
- The research data model and migration exist already:
  - ORM models: `backend/app/models/research.py`
  - migration: `backend/alembic/versions/20260311_0036_research_workspace.py`
  - tables include collections, collection members, WBS link junctions, references, notes, note-reference links, annotations, and research chunks for retrieval.
- Research content is connected to search/retrieval:
  - chunking and embedding: `backend/app/services/research_ai_service.py`
  - embedding backfill support: `backend/app/services/embedding_service.py`
  - retrieval scope includes `research`: `backend/app/agents/retrieval_agent.py`

## Research Gaps

- Collections are conceptually topic containers. The intended UX is: create collection -> select collection -> add/manage references and notes inside that selected collection.
- The frontend currently does not expose edit flows for collections, references, or notes even though backend update endpoints exist.
- The frontend does not expose WBS linking, note-to-reference linking, reference move between collections, PDF metadata extraction, annotations, or member role editing, even though backend support exists for most of these.
- Research AI features depend on Ollama-backed chat and embedding settings in backend config. If Ollama is unavailable, summarization/synthesis/embedding will degrade or fail.
- I did not find dedicated backend tests for the research routes or `ResearchWorkspace`; coverage appears absent or minimal for this slice.
