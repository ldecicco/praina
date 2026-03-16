"""Tests for the RetrievalAgent."""

import uuid


def _setup_project_with_document(client):
    """Create a project with a partner, member, WP, and a document with content."""
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "RET-TEST",
            "title": "Retrieval Test",
            "description": "Testing retrieval agent",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    ).json()
    pid = project["id"]

    org = client.post(
        f"/api/v1/projects/{pid}/partners",
        json={"short_name": "ACME", "legal_name": "Acme Corp"},
    ).json()
    org_id = org["id"]

    member = client.post(
        f"/api/v1/projects/{pid}/members",
        json={"partner_id": org_id, "full_name": "Alice Test", "email": "alice@test.org", "role": "WP Lead"},
    ).json()
    member_id = member["id"]

    wp = client.post(
        f"/api/v1/projects/{pid}/work-packages",
        json={
            "code": "WP1",
            "title": "Core Platform",
            "description": "Core architecture and infrastructure",
            "start_month": 1,
            "end_month": 12,
            "assignment": {
                "leader_organization_id": org_id,
                "responsible_person_id": member_id,
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    return pid, org_id, member_id, wp["id"]


def test_retrieval_agent_returns_empty_for_empty_project(client, db_engine):
    """RetrievalAgent should return empty results for a project with no documents."""
    from sqlalchemy.orm import Session
    from app.agents.retrieval_agent import RetrievalAgent

    pid, _, _, _ = _setup_project_with_document(client)

    with Session(db_engine) as db:
        agent = RetrievalAgent(db)
        results = agent.retrieve(query="anything", project_id=uuid.UUID(pid))
        assert results == []


def test_retrieval_agent_finds_matching_document_chunks(client, db_engine):
    """RetrievalAgent should find chunks that match the query."""
    from sqlalchemy.orm import Session
    from app.agents.retrieval_agent import RetrievalAgent
    from app.models.document import DocumentChunk, DocumentStatus, DocumentScope, ProjectDocument

    pid, _, member_id, _ = _setup_project_with_document(client)
    project_uuid = uuid.UUID(pid)

    with Session(db_engine) as db:
        doc = ProjectDocument(
            project_id=project_uuid,
            document_key="DOC-001",
            scope=DocumentScope.project,
            title="Architecture Document",
            storage_uri="file:///test/arch.pdf",
            original_filename="arch.pdf",
            file_size_bytes=1024,
            mime_type="application/pdf",
            status=DocumentStatus.indexed,
            version=1,
            uploaded_by_member_id=uuid.UUID(member_id),
        )
        db.add(doc)
        db.flush()

        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content="The system uses a microservices architecture with event-driven communication between services.",
        )
        db.add(chunk)
        db.commit()

        agent = RetrievalAgent(db)
        results = agent.retrieve(query="microservices architecture", project_id=project_uuid)
        assert len(results) >= 1
        assert "microservices" in results[0].content.lower()


def test_retrieval_agent_deduplicates_results(client, db_engine):
    """RetrievalAgent should not return duplicate chunks."""
    from sqlalchemy.orm import Session
    from app.agents.retrieval_agent import RetrievalAgent
    from app.models.document import DocumentChunk, DocumentStatus, DocumentScope, ProjectDocument

    pid, _, member_id, _ = _setup_project_with_document(client)
    project_uuid = uuid.UUID(pid)

    with Session(db_engine) as db:
        doc = ProjectDocument(
            project_id=project_uuid,
            document_key="DOC-002",
            scope=DocumentScope.project,
            title="Duplicate Test",
            storage_uri="file:///test/dup.pdf",
            original_filename="dup.pdf",
            file_size_bytes=512,
            mime_type="application/pdf",
            status=DocumentStatus.indexed,
            version=1,
            uploaded_by_member_id=uuid.UUID(member_id),
        )
        db.add(doc)
        db.flush()

        for i in range(3):
            db.add(DocumentChunk(document_id=doc.id, chunk_index=i, content="Quantum computing is the next frontier of technology innovation."))
        db.commit()

        agent = RetrievalAgent(db)
        results = agent.retrieve(query="quantum computing", project_id=project_uuid, top_k=10)
        # All chunks have the same content but different indices — all should appear (no source_id+chunk_index collision)
        source_keys = set()
        for r in results:
            key = (r.source_id, r.chunk_index)
            assert key not in source_keys, f"Duplicate result: {key}"
            source_keys.add(key)
