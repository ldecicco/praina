import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import UserAccount
from app.models.project import Project
from app.models.work import Task, WorkPackage
from app.services.project_chat_service import ProjectChatService
from app.services.project_chatops_service import ProjectChatOpsService


def _create_project(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-CHAT",
            "title": "Chat Project",
            "description": "Chat API test",
            "start_date": "2026-01-01",
            "duration_months": 18,
            "reporting_dates": [],
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_project_chat_reply_and_reaction_toggle(client):
    project_id = _create_project(client)

    rooms_resp = client.get(f"/api/v1/projects/{project_id}/rooms")
    assert rooms_resp.status_code == 200
    room_id = rooms_resp.json()["items"][0]["id"]

    first_msg_resp = client.post(
        f"/api/v1/projects/{project_id}/rooms/{room_id}/messages",
        json={"content": "First message"},
    )
    assert first_msg_resp.status_code == 200
    first_message = first_msg_resp.json()

    reply_resp = client.post(
        f"/api/v1/projects/{project_id}/rooms/{room_id}/messages",
        json={"content": "Reply message", "reply_to_message_id": first_message["id"]},
    )
    assert reply_resp.status_code == 200
    reply_message = reply_resp.json()
    assert reply_message["reply_to_message_id"] == first_message["id"]
    assert reply_message["reply_to_message"]["id"] == first_message["id"]
    assert reply_message["reply_to_message"]["content"] == "First message"

    reaction_add_resp = client.post(
        f"/api/v1/projects/{project_id}/rooms/{room_id}/messages/{reply_message['id']}/reactions",
        json={"emoji": "👍"},
    )
    assert reaction_add_resp.status_code == 200
    reaction_added = reaction_add_resp.json()
    assert reaction_added["reactions"][0]["emoji"] == "👍"
    assert reaction_added["reactions"][0]["count"] == 1
    assert reply_message["sender_user_id"] in reaction_added["reactions"][0]["user_ids"]

    reaction_remove_resp = client.post(
        f"/api/v1/projects/{project_id}/rooms/{room_id}/messages/{reply_message['id']}/reactions",
        json={"emoji": "👍"},
    )
    assert reaction_remove_resp.status_code == 200
    reaction_removed = reaction_remove_resp.json()
    assert reaction_removed["reactions"] == []

    list_resp = client.get(f"/api/v1/projects/{project_id}/rooms/{room_id}/messages?page=1&page_size=100")
    assert list_resp.status_code == 200
    rows = list_resp.json()["items"]
    assert len(rows) == 2
    listed_reply = rows[1]
    assert listed_reply["reply_to_message_id"] == first_message["id"]
    assert listed_reply["reply_to_message"]["id"] == first_message["id"]


def test_project_chatops_llm_action_proposal_and_confirm(client, db_engine, monkeypatch):
    project_id = _create_project(client)

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
            "full_name": "Gioacchino Manfredi",
            "email": "gioacchino.manfredi@poliba.it",
            "role": "Researcher",
        },
    )
    assert member_resp.status_code == 200
    member_id = member_resp.json()["id"]

    wp_resp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Platform",
            "description": "Core platform",
            "start_month": 5,
            "end_month": 14,
            "assignment": {
                "leader_organization_id": partner_id,
                "responsible_person_id": member_id,
                "collaborating_partner_ids": [],
            },
        },
    )
    assert wp_resp.status_code == 200

    rooms_resp = client.get(f"/api/v1/projects/{project_id}/rooms")
    assert rooms_resp.status_code == 200
    room_id = rooms_resp.json()["items"][0]["id"]

    project_uuid = uuid.UUID(project_id)
    room_uuid = uuid.UUID(room_id)
    with Session(db_engine) as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "test-admin@example.com"))
        assert user is not None

        context_service = ProjectChatService(db)
        context = context_service.project_context_for_agent(project_uuid)
        chatops = ProjectChatOpsService(db)

        monkeypatch.setattr(
            chatops.chat_service,
            "_parse_natural_language_action",
            lambda *_args, **_kwargs: (
                {
                    "action_type": "create",
                    "entity_type": "task",
                    "fields": {
                        "code": "T1.2",
                        "title": "Architecture",
                        "leader": "POLIBA",
                        "responsible": "Gioacchino Manfredi",
                        "wp": "WP1",
                        "start_month": "5",
                        "end_month": "14",
                    },
                },
                None,
            ),
        )

        proposal_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt='please add task T1.2 titled "Architecture" lead by "Gioacchino Manfredi" of POLIBA team. The task belongs to WP1.',
            project_context=context,
        )
        assert proposal_reply is not None
        assert "Pending action created." in proposal_reply

        match = re.search(r"Proposal ID:\s*([0-9a-f-]{36})", proposal_reply)
        assert match is not None
        proposal_id = match.group(1)

        confirm_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt=f"confirm {proposal_id}",
            project_context=context,
        )
        assert confirm_reply is not None
        assert "processed successfully" in confirm_reply

        created_task = db.scalar(select(Task).where(Task.project_id == project_uuid, Task.code == "T1.2"))
        assert created_task is not None
        assert created_task.start_month == 5
        assert created_task.end_month == 14


def test_project_chatops_non_action_request_returns_none(client, db_engine, monkeypatch):
    project_id = _create_project(client)
    rooms_resp = client.get(f"/api/v1/projects/{project_id}/rooms")
    assert rooms_resp.status_code == 200
    room_id = rooms_resp.json()["items"][0]["id"]

    with Session(db_engine) as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "test-admin@example.com"))
        assert user is not None
        project_uuid = uuid.UUID(project_id)
        room_uuid = uuid.UUID(room_id)

        context = ProjectChatService(db).project_context_for_agent(project_uuid)
        chatops = ProjectChatOpsService(db)
        monkeypatch.setattr(
            chatops.chat_service,
            "_parse_natural_language_action",
            lambda *_args, **_kwargs: (None, None),
        )

        reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt="can you summarize this project status?",
            project_context=context,
        )
        assert reply is None


def test_project_chatops_batch_proposal_creates_wp_then_tasks(client, db_engine, monkeypatch):
    project_id = _create_project(client)

    partner_resp = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "POLIBA", "legal_name": "Politecnico di Bari"},
    )
    assert partner_resp.status_code == 200
    partner_id = partner_resp.json()["id"]

    saverio_resp = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner_id,
            "full_name": "Saverio Mascolo",
            "email": "saverio.mascolo@poliba.it",
            "role": "WP Lead",
        },
    )
    assert saverio_resp.status_code == 200
    gioacchino_resp = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner_id,
            "full_name": "Gioacchino Manfredi",
            "email": "gioacchino.manfredi@poliba.it",
            "role": "Researcher",
        },
    )
    assert gioacchino_resp.status_code == 200

    rooms_resp = client.get(f"/api/v1/projects/{project_id}/rooms")
    assert rooms_resp.status_code == 200
    room_id = rooms_resp.json()["items"][0]["id"]

    project_uuid = uuid.UUID(project_id)
    room_uuid = uuid.UUID(room_id)
    with Session(db_engine) as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "test-admin@example.com"))
        assert user is not None

        context = ProjectChatService(db).project_context_for_agent(project_uuid)
        chatops = ProjectChatOpsService(db)
        monkeypatch.setattr(
            chatops.chat_service,
            "_parse_natural_language_action",
            lambda *_args, **_kwargs: (
                {
                    "batch_actions": [
                        {
                            "action_type": "create",
                            "entity_type": "work_package",
                            "fields": {
                                "code": "WP2",
                                "title": "Chatbot",
                                "start_month": "6",
                                "end_month": "12",
                                "leader": "POLIBA",
                                "responsible": "Saverio Mascolo",
                            },
                        },
                        {
                            "action_type": "create",
                            "entity_type": "task",
                            "fields": {
                                "code": "T2.1",
                                "title": "Chatbot design",
                                "start_month": "6",
                                "end_month": "8",
                                "leader": "POLIBA",
                                "responsible": "Gioacchino Manfredi",
                                "wp": "WP2",
                            },
                        },
                        {
                            "action_type": "create",
                            "entity_type": "task",
                            "fields": {
                                "code": "T2.2",
                                "title": "Chatbot testing",
                                "start_month": "7",
                                "end_month": "12",
                                "leader": "POLIBA",
                                "responsible": "Gioacchino Manfredi",
                                "wp": "WP2",
                            },
                        },
                    ]
                },
                None,
            ),
        )

        proposal_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt='Please create WP2 "Chatbot" (M6-M12) led by partner POLIBA ("Saverio Mascolo") and two tasks all led by "Gioacchino Manfredi" of POLIBA T2.1 "Chatbot design" (M6-M8) and T2.2 "Chatbot testing" (M7-M12)',
            project_context=context,
        )
        assert proposal_reply is not None
        assert "Execute ordered batch" in proposal_reply

        match = re.search(r"Proposal ID:\s*([0-9a-f-]{36})", proposal_reply)
        assert match is not None
        proposal_id = match.group(1)

        confirm_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt=f"confirm {proposal_id}",
            project_context=context,
        )
        assert confirm_reply is not None
        assert "Batch processed successfully" in confirm_reply

        created_wp = db.scalar(select(WorkPackage).where(WorkPackage.project_id == project_uuid, WorkPackage.code == "WP2"))
        created_task_1 = db.scalar(select(Task).where(Task.project_id == project_uuid, Task.code == "T2.1"))
        created_task_2 = db.scalar(select(Task).where(Task.project_id == project_uuid, Task.code == "T2.2"))
        assert created_wp is not None
        assert created_task_1 is not None
        assert created_task_2 is not None
        assert created_task_1.wp_id == created_wp.id
        assert created_task_2.wp_id == created_wp.id


def test_project_chatops_project_settings_update_requires_confirm_and_applies(client, db_engine, monkeypatch):
    project_id = _create_project(client)

    rooms_resp = client.get(f"/api/v1/projects/{project_id}/rooms")
    assert rooms_resp.status_code == 200
    room_id = rooms_resp.json()["items"][0]["id"]

    project_uuid = uuid.UUID(project_id)
    room_uuid = uuid.UUID(room_id)
    with Session(db_engine) as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "test-admin@example.com"))
        assert user is not None

        context = ProjectChatService(db).project_context_for_agent(project_uuid)
        chatops = ProjectChatOpsService(db)
        monkeypatch.setattr(
            chatops.chat_service,
            "_parse_natural_language_action",
            lambda *_args, **_kwargs: (
                {
                    "action_type": "update",
                    "entity_type": "project",
                    "fields": {
                        "duration_months": "30",
                        "reporting_dates": "2026-12-31,2027-12-31",
                    },
                },
                None,
            ),
        )

        proposal_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt="Please update the project duration to 30 months and set reporting dates to 2026-12-31 and 2027-12-31.",
            project_context=context,
        )
        assert proposal_reply is not None
        assert "Pending action created." in proposal_reply
        assert "Update project" in proposal_reply

        match = re.search(r"Proposal ID:\s*([0-9a-f-]{36})", proposal_reply)
        assert match is not None
        proposal_id = match.group(1)

        confirm_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt=f"confirm {proposal_id}",
            project_context=context,
        )
        assert confirm_reply is not None
        assert "Project `HEU-CHAT` processed successfully." in confirm_reply

        updated_project = db.scalar(select(Project).where(Project.id == project_uuid))
        assert updated_project is not None
        assert updated_project.duration_months == 30
        assert updated_project.reporting_dates == ["2026-12-31", "2027-12-31"]


def test_project_chatops_project_reporting_period_markers_are_normalized(client, db_engine, monkeypatch):
    project_id = _create_project(client)

    rooms_resp = client.get(f"/api/v1/projects/{project_id}/rooms")
    assert rooms_resp.status_code == 200
    room_id = rooms_resp.json()["items"][0]["id"]

    project_uuid = uuid.UUID(project_id)
    room_uuid = uuid.UUID(room_id)
    with Session(db_engine) as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "test-admin@example.com"))
        assert user is not None

        context = ProjectChatService(db).project_context_for_agent(project_uuid)
        chatops = ProjectChatOpsService(db)
        monkeypatch.setattr(
            chatops.chat_service,
            "_parse_natural_language_action",
            lambda *_args, **_kwargs: (
                {
                    "action_type": "update",
                    "entity_type": "project",
                    "fields": {
                        "reporting_dates": "M6,M12,M18",
                    },
                },
                None,
            ),
        )

        proposal_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt="Set the reporting dates to M6, M12, and M18.",
            project_context=context,
        )
        assert proposal_reply is not None
        assert "2026-06-30" in proposal_reply
        assert "2026-12-31" in proposal_reply
        assert "2027-06-30" in proposal_reply

        match = re.search(r"Proposal ID:\s*([0-9a-f-]{36})", proposal_reply)
        assert match is not None
        proposal_id = match.group(1)

        confirm_reply = chatops.handle_mentioned_message(
            project_id=project_uuid,
            room_id=room_uuid,
            sender_user_id=user.id,
            prompt=f"confirm {proposal_id}",
            project_context=context,
        )
        assert confirm_reply is not None
        assert "Project `HEU-CHAT` processed successfully." in confirm_reply

        updated_project = db.scalar(select(Project).where(Project.id == project_uuid))
        assert updated_project is not None
        assert updated_project.reporting_dates == ["2026-06-30", "2026-12-31", "2027-06-30"]
