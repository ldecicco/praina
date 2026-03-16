import uuid

from sqlalchemy.orm import Session

from app.agents.chat_assistant_agent import ChatAssistantAgent
from app.services.project_chat_service import ProjectChatService


def _create_project_partner_member(client):
    project_resp = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-CHATDOC",
            "title": "Chat Documents Project",
            "description": "Chat document reference test",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    partner_resp = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "POLIBA", "legal_name": "Politecnico di Bari"},
    )
    assert partner_resp.status_code == 200
    partner_id = partner_resp.json()["id"]

    member_resp = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner_id,
            "full_name": "Laura Verdi",
            "email": "laura.verdi@example.org",
            "role": "Knowledge Manager",
        },
    )
    assert member_resp.status_code == 200
    return project_id, member_resp.json()["id"]


def _upload_and_index_document(client, project_id: str, member_id: str, title: str, content: str) -> dict:
    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/upload",
        data={
            "scope": "project",
            "title": title,
            "uploaded_by_member_id": member_id,
        },
        files={"file": (f"{title.lower().replace(' ', '-')}.txt", content.encode("utf-8"), "text/plain")},
    )
    assert upload_resp.status_code == 200
    document = upload_resp.json()

    reindex_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/{document['id']}/reindex?async_job=false"
    )
    assert reindex_resp.status_code == 200
    assert reindex_resp.json()["status"] == "indexed"
    return document


def test_assistant_chat_document_reference_filters_citations(client, monkeypatch):
    project_id, member_id = _create_project_partner_member(client)
    _upload_and_index_document(
        client,
        project_id,
        member_id,
        "WP4 Architecture Document",
        "WP4 focuses on architecture choices, component decomposition, and interface contracts.",
    )
    _upload_and_index_document(
        client,
        project_id,
        member_id,
        "WP2 Data Document",
        "WP2 focuses on data management and repository setup.",
    )

    conv_resp = client.post(f"/api/v1/projects/{project_id}/chat/conversations", json={"title": "Docs"})
    assert conv_resp.status_code == 200
    conversation_id = conv_resp.json()["id"]

    monkeypatch.setattr(ChatAssistantAgent, "generate", lambda *args, **kwargs: "Filtered summary")

    message_resp = client.post(
        f"/api/v1/projects/{project_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "Can you summarize from #wp4 the content of WP4?"},
    )
    assert message_resp.status_code == 200
    assistant_message = message_resp.json()["assistant_message"]
    citations = assistant_message["citations"]
    assert citations
    assert all(item["title"] == "WP4 Architecture Document" for item in citations)


def test_project_chat_service_document_reference_resolution_and_filtering(client, db_engine):
    project_id, member_id = _create_project_partner_member(client)
    doc_wp4 = _upload_and_index_document(
        client,
        project_id,
        member_id,
        "WP4 Architecture Document",
        "WP4 architecture covers orchestration and module integration.",
    )
    _upload_and_index_document(
        client,
        project_id,
        member_id,
        "General Proposal",
        "This proposal covers governance, exploitation, and dissemination.",
    )

    with Session(db_engine) as db:
        service = ProjectChatService(db)
        refs = service.extract_document_references(uuid.UUID(project_id), "Summarize #wp4 and focus on WP4.")
        assert refs["titles"] == ["WP4 Architecture Document"]
        assert refs["unresolved_tokens"] == []

        citations = service.retrieve_citations(uuid.UUID(project_id), "Summarize #wp4 and focus on WP4.")
        assert citations
        assert all(item["title"] == "WP4 Architecture Document" for item in citations)
        assert all(item["document_key"] == doc_wp4["document_key"] for item in citations)
