def test_onboarding_happy_path_and_activation(client):
    project_resp = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-ALPHA",
            "title": "Alpha Program",
            "description": "Integration test",
            "start_date": "2026-01-01",
            "duration_months": 36,
            "reporting_dates": ["2026-12-31", "2027-12-31"],
        },
    )
    assert project_resp.status_code == 200
    project = project_resp.json()
    project_id = project["id"]
    assert project["baseline_version"] == 0
    assert project["status"] == "draft"

    partner_resp = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "UNIROMA", "legal_name": "Sapienza University of Rome"},
    )
    assert partner_resp.status_code == 200
    org_id = partner_resp.json()["id"]

    member_resp = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": org_id,
            "full_name": "Giulia Rossi",
            "email": "giulia.rossi@example.org",
            "role": "WP Lead",
        },
    )
    assert member_resp.status_code == 200
    member_id = member_resp.json()["id"]

    wp_resp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Platform Foundation",
            "description": "Core architecture",
            "start_month": 1,
            "end_month": 12,
            "assignment": {
                "leader_organization_id": org_id,
                "responsible_person_id": member_id,
                "collaborating_partner_ids": [org_id],
            },
        },
    )
    assert wp_resp.status_code == 200

    validate_resp = client.post(f"/api/v1/projects/{project_id}/validate")
    assert validate_resp.status_code == 200
    validation = validate_resp.json()
    assert validation["valid"] is True
    assert validation["errors"] == []

    activate_resp = client.post(f"/api/v1/projects/{project_id}/activate")
    assert activate_resp.status_code == 200
    activation = activate_resp.json()
    assert activation["status"] == "active"
    assert activation["baseline_version"] == 1


def test_assignment_validation_rejects_responsible_from_different_organization(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-BETA",
            "title": "Beta Program",
            "description": "Validation test",
            "start_date": "2026-01-01",
            "duration_months": 36,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    org1 = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORG1", "legal_name": "Organization One"},
    ).json()
    org2 = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORG2", "legal_name": "Organization Two"},
    ).json()

    member2 = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": org2["id"],
            "full_name": "Marco Bianchi",
            "email": "marco.bianchi@example.org",
            "role": "Researcher",
        },
    ).json()

    wp_resp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Invalid Assignment WP",
            "description": "Should fail",
            "start_month": 1,
            "end_month": 8,
            "assignment": {
                "leader_organization_id": org1["id"],
                "responsible_person_id": member2["id"],
                "collaborating_partner_ids": [org1["id"]],
            },
        },
    )
    assert wp_resp.status_code == 400
    assert "leader partner" in wp_resp.json()["detail"].lower()


def test_deliverable_requires_existing_wp(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-GAMMA",
            "title": "Gamma Program",
            "description": "Deliverable WP guard",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGX", "legal_name": "Organization X"},
    ).json()

    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Alice Neri",
            "email": "alice.neri@example.org",
            "role": "Lead",
        },
    ).json()

    bad_resp = client.post(
        f"/api/v1/projects/{project_id}/deliverables",
        json={
            "wp_id": "00000000-0000-0000-0000-000000000000",
            "code": "D1.1",
            "title": "Invalid Deliverable",
            "description": "Should fail",
            "due_month": 12,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert bad_resp.status_code == 404
    assert "work package not found" in bad_resp.json()["detail"].lower()


def test_timeline_validation_task_and_deliverable_windows(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-DELTA",
            "title": "Delta Program",
            "description": "Timeline guards",
            "start_date": "2026-01-01",
            "duration_months": 18,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGY", "legal_name": "Organization Y"},
    ).json()

    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Luca Nero",
            "email": "luca.nero@example.org",
            "role": "Lead",
        },
    ).json()

    wp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Core",
            "description": "Core WP",
            "start_month": 1,
            "end_month": 6,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    bad_task = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "wp_id": wp["id"],
            "code": "T1",
            "title": "Outside Task",
            "description": "Too long",
            "start_month": 5,
            "end_month": 9,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert bad_task.status_code == 400
    assert "inside the parent work package window" in bad_task.json()["detail"].lower()

    bad_deliverable = client.post(
        f"/api/v1/projects/{project_id}/deliverables",
        json={
            "wp_id": wp["id"],
            "code": "D1.1",
            "title": "Late Deliverable",
            "description": "Too late",
            "due_month": 10,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert bad_deliverable.status_code == 400
    assert "cannot be after the end month" in bad_deliverable.json()["detail"].lower()


def test_create_deliverable_happy_path(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-THETA",
            "title": "Theta Program",
            "description": "Deliverable create path",
            "start_date": "2026-01-01",
            "duration_months": 18,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGTH", "legal_name": "Organization Theta"},
    ).json()

    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Paolo Neri",
            "email": "paolo.neri@example.org",
            "role": "Lead",
        },
    ).json()

    wp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Foundation",
            "description": "Core",
            "start_month": 1,
            "end_month": 12,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    deliverable_resp = client.post(
        f"/api/v1/projects/{project_id}/deliverables",
        json={
            "wp_ids": [wp["id"]],
            "code": "D1.1",
            "title": "Initial Deliverable",
            "description": "Report",
            "due_month": 6,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert deliverable_resp.status_code == 200
    deliverable = deliverable_resp.json()
    assert deliverable["code"] == "D1.1"
    assert deliverable["wp_ids"] == [wp["id"]]


def test_trash_and_restore_work_entities(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-IOTA",
            "title": "Iota Program",
            "description": "Trash flow",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGI", "legal_name": "Organization Iota"},
    ).json()

    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Franco Berti",
            "email": "franco.berti@example.org",
            "role": "Lead",
        },
    ).json()

    wp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Core WP",
            "description": "Core",
            "start_month": 1,
            "end_month": 12,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    task = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "wp_id": wp["id"],
            "code": "T1",
            "title": "Task 1",
            "description": "Task",
            "start_month": 2,
            "end_month": 6,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    deliverable = client.post(
        f"/api/v1/projects/{project_id}/deliverables",
        json={
            "wp_ids": [wp["id"]],
            "code": "D1.1",
            "title": "Deliverable 1",
            "description": "Doc",
            "due_month": 6,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    milestone = client.post(
        f"/api/v1/projects/{project_id}/milestones",
        json={
            "wp_ids": [wp["id"]],
            "code": "MS1",
            "title": "Milestone 1",
            "description": "Gate",
            "due_month": 7,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    trash_wp_resp = client.post(f"/api/v1/projects/{project_id}/work-packages/{wp['id']}/trash")
    assert trash_wp_resp.status_code == 200
    assert trash_wp_resp.json()["is_trashed"] is True

    tasks_after_trash = client.get(f"/api/v1/projects/{project_id}/tasks?page=1&page_size=100").json()
    deliverables_after_trash = client.get(f"/api/v1/projects/{project_id}/deliverables?page=1&page_size=100").json()
    milestones_after_trash = client.get(f"/api/v1/projects/{project_id}/milestones?page=1&page_size=100").json()
    assert tasks_after_trash["total"] == 0
    assert deliverables_after_trash["total"] == 0
    assert milestones_after_trash["total"] == 0

    trash_list = client.get(f"/api/v1/projects/{project_id}/trash?page=1&page_size=100")
    assert trash_list.status_code == 200
    assert trash_list.json()["total"] >= 4

    blocked_restore_task = client.post(f"/api/v1/projects/{project_id}/tasks/{task['id']}/restore")
    assert blocked_restore_task.status_code == 400

    restore_wp_resp = client.post(f"/api/v1/projects/{project_id}/work-packages/{wp['id']}/restore")
    assert restore_wp_resp.status_code == 200
    assert restore_wp_resp.json()["is_trashed"] is False

    restore_task_resp = client.post(f"/api/v1/projects/{project_id}/tasks/{task['id']}/restore")
    assert restore_task_resp.status_code == 200
    assert restore_task_resp.json()["is_trashed"] is False

    restore_deliverable_resp = client.post(f"/api/v1/projects/{project_id}/deliverables/{deliverable['id']}/restore")
    assert restore_deliverable_resp.status_code == 200
    assert restore_deliverable_resp.json()["is_trashed"] is False

    restore_milestone_resp = client.post(f"/api/v1/projects/{project_id}/milestones/{milestone['id']}/restore")
    assert restore_milestone_resp.status_code == 200
    assert restore_milestone_resp.json()["is_trashed"] is False


def test_project_update_baseline_fields(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-EPSILON",
            "title": "Epsilon Program",
            "description": "Original",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": ["2026-12-31"],
        },
    ).json()
    project_id = project["id"]

    update_resp = client.patch(
        f"/api/v1/projects/{project_id}",
        json={
            "title": "Epsilon Program Updated",
            "description": "Updated description",
            "start_date": "2026-02-01",
            "duration_months": 30,
            "reporting_dates": ["2026-12-31", "2027-12-31"],
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["title"] == "Epsilon Program Updated"
    assert updated["description"] == "Updated description"
    assert updated["start_date"] == "2026-02-01"
    assert updated["duration_months"] == 30
    assert updated["reporting_dates"] == ["2026-12-31", "2027-12-31"]


def test_project_update_duration_rejects_existing_month_usage(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-ZETA",
            "title": "Zeta Program",
            "description": "Duration guard",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGZ", "legal_name": "Organization Z"},
    ).json()
    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Ada Neri",
            "email": "ada.neri@example.org",
            "role": "Coordinator",
        },
    ).json()

    wp_resp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Core",
            "description": "Core WP",
            "start_month": 1,
            "end_month": 18,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert wp_resp.status_code == 200

    update_resp = client.patch(f"/api/v1/projects/{project_id}", json={"duration_months": 12})
    assert update_resp.status_code == 400
    assert "cannot be less than m18" in update_resp.json()["detail"].lower()


def test_work_package_update_requires_task_window_consistency(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-ETA",
            "title": "Eta Program",
            "description": "WP update guards",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGA", "legal_name": "Organization A"},
    ).json()
    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Maria Verdi",
            "email": "maria.verdi@example.org",
            "role": "Lead",
        },
    ).json()

    wp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Core WP",
            "description": "Core",
            "start_month": 1,
            "end_month": 12,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    task_resp = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "wp_id": wp["id"],
            "code": "T1.1",
            "title": "Task 1",
            "description": "Task",
            "start_month": 8,
            "end_month": 10,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert task_resp.status_code == 200

    bad_update = client.patch(
        f"/api/v1/projects/{project_id}/work-packages/{wp['id']}",
        json={
            "code": "WP1",
            "title": "Core WP Updated",
            "description": "Core",
            "start_month": 1,
            "end_month": 7,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert bad_update.status_code == 400
    assert "outside the new wp window" in bad_update.json()["detail"].lower()


def test_task_update_inside_wp_window(client):
    project = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-THETA",
            "title": "Theta Program",
            "description": "Task update",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    ).json()
    project_id = project["id"]

    partner = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "ORGB", "legal_name": "Organization B"},
    ).json()
    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "partner_id": partner["id"],
            "full_name": "Piero Neri",
            "email": "piero.neri@example.org",
            "role": "Lead",
        },
    ).json()

    wp = client.post(
        f"/api/v1/projects/{project_id}/work-packages",
        json={
            "code": "WP1",
            "title": "Core",
            "description": "Core",
            "start_month": 1,
            "end_month": 12,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    task = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "wp_id": wp["id"],
            "code": "T1",
            "title": "Task 1",
            "description": "Task",
            "start_month": 2,
            "end_month": 4,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    ).json()

    update_resp = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}",
        json={
            "code": "T1",
            "title": "Task 1 Updated",
            "description": "Updated",
            "start_month": 3,
            "end_month": 6,
            "assignment": {
                "leader_organization_id": partner["id"],
                "responsible_person_id": member["id"],
                "collaborating_partner_ids": [],
            },
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Task 1 Updated"
