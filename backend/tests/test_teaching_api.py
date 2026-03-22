def test_teaching_project_workspace_flow(client):
    create_resp = client.post(
        "/api/v1/projects",
        json={
            "code": "MSC-TH-1",
            "title": "Teaching Project",
            "description": "MSc supervised project",
            "project_mode": "execution",
            "project_kind": "teaching",
            "start_date": "2026-03-01",
            "duration_months": 6,
            "reporting_dates": ["2026-03-15", "2026-03-29"],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    project = create_resp.json()
    assert project["project_kind"] == "teaching"

    project_id = project["id"]

    workspace_resp = client.get(f"/api/v1/projects/{project_id}/teaching")
    assert workspace_resp.status_code == 200, workspace_resp.text
    workspace = workspace_resp.json()
    assert workspace["profile"]["project_id"] == project_id
    assert workspace["profile"]["status"] == "draft"

    profile_resp = client.put(
        f"/api/v1/projects/{project_id}/teaching/profile",
        json={
            "course_code": "CS-701",
            "course_name": "Advanced AI Systems",
            "academic_year": "2025/2026",
            "term": "spring",
            "functional_objectives_markdown": "Build a working prototype.",
            "specifications_markdown": "Use a public repository.",
            "status": "active",
            "health": "yellow",
            "reporting_cadence_days": 14,
        },
    )
    assert profile_resp.status_code == 200, profile_resp.text
    assert profile_resp.json()["course_code"] == "CS-701"

    student_resp = client.post(
        f"/api/v1/projects/{project_id}/teaching/students",
        json={"full_name": "Alice Example", "email": "alice@example.com"},
    )
    assert student_resp.status_code == 201, student_resp.text

    artifact_resp = client.post(
        f"/api/v1/projects/{project_id}/teaching/artifacts",
        json={
            "artifact_type": "repository",
            "label": "Code",
            "required": True,
            "status": "submitted",
            "external_url": "https://github.com/example/repo",
        },
    )
    assert artifact_resp.status_code == 201, artifact_resp.text

    report_resp = client.post(
        f"/api/v1/projects/{project_id}/teaching/progress-reports",
        json={
            "period_start": "2026-03-01",
            "period_end": "2026-03-14",
            "summary_markdown": "Implemented the first iteration.",
            "completed_work": ["Prototype ready"],
            "current_blockers": ["Need more evaluation data"],
            "next_steps": ["Run experiments"],
            "requested_support": ["Access to the lab cluster"],
            "status_confidence": "medium",
        },
    )
    assert report_resp.status_code == 201, report_resp.text

    blocker_resp = client.post(
        f"/api/v1/projects/{project_id}/teaching/blockers",
        json={"title": "Dataset gap", "severity": "high", "status": "open"},
    )
    assert blocker_resp.status_code == 201, blocker_resp.text

    milestone_resp = client.post(
        f"/api/v1/projects/{project_id}/teaching/milestones",
        json={"kind": "midterm_review", "label": "Midterm Review", "due_at": "2026-04-01", "status": "pending"},
    )
    assert milestone_resp.status_code == 201, milestone_resp.text

    assessment_resp = client.put(
        f"/api/v1/projects/{project_id}/teaching/assessment",
        json={
            "grade": 8.5,
            "strengths_markdown": "Good implementation quality.",
            "weaknesses_markdown": "Evaluation depth is limited.",
            "grading_rationale_markdown": "Strong practical result with some validation gaps.",
        },
    )
    assert assessment_resp.status_code == 200, assessment_resp.text
    assert assessment_resp.json()["grade"] == 8.5

    final_workspace = client.get(f"/api/v1/projects/{project_id}/teaching")
    assert final_workspace.status_code == 200, final_workspace.text
    payload = final_workspace.json()
    assert len(payload["students"]) == 1
    assert len(payload["artifacts"]) == 1
    assert len(payload["progress_reports"]) == 1
    assert len(payload["blockers"]) == 1
    assert len(payload["milestones"]) == 1
    assert payload["assessment"]["grade"] == 8.5
