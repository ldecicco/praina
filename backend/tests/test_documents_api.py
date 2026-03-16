import io
import zipfile


def _create_project_partner_member(client):
    project_resp = client.post(
        "/api/v1/projects",
        json={
            "code": "HEU-DOCS",
            "title": "Documents Project",
            "description": "Documents API test",
            "start_date": "2026-01-01",
            "duration_months": 24,
            "reporting_dates": [],
        },
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    partner_resp = client.post(
        f"/api/v1/projects/{project_id}/partners",
        json={"short_name": "DOCORG", "legal_name": "Document Organization"},
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
    member_id = member_resp.json()["id"]
    return project_id, partner_id, member_id


def test_document_upload_list_get_and_new_version(client):
    project_id, _, member_id = _create_project_partner_member(client)

    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/upload",
        data={
            "scope": "project",
            "title": "Consortium Agreement",
            "metadata_json": '{"category":"legal"}',
            "uploaded_by_member_id": member_id,
        },
        files={"file": ("consortium-agreement.txt", b"v1 contents", "text/plain")},
    )
    assert upload_resp.status_code == 200
    uploaded = upload_resp.json()
    assert uploaded["scope"] == "project"
    assert uploaded["version"] == 1
    assert uploaded["status"] == "uploaded"
    document_id = uploaded["id"]
    document_key = uploaded["document_key"]

    list_resp = client.get(f"/api/v1/projects/{project_id}/documents")
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["document_key"] == document_key
    assert list_payload["items"][0]["latest_version"] == 1
    assert list_payload["items"][0]["versions_count"] == 1

    get_resp = client.get(f"/api/v1/projects/{project_id}/documents/{document_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Consortium Agreement"

    v2_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/{document_key}/versions/upload",
        data={
            "title": "Consortium Agreement Updated",
            "metadata_json": '{"category":"legal","revision":"2"}',
            "uploaded_by_member_id": member_id,
        },
        files={"file": ("consortium-agreement-v2.txt", b"v2 contents", "text/plain")},
    )
    assert v2_resp.status_code == 200
    assert v2_resp.json()["version"] == 2
    assert v2_resp.json()["document_key"] == document_key
    assert v2_resp.json()["title"] == "Consortium Agreement Updated"

    versions_resp = client.get(f"/api/v1/projects/{project_id}/documents/by-key/{document_key}/versions")
    assert versions_resp.status_code == 200
    versions_payload = versions_resp.json()
    assert len(versions_payload["versions"]) == 2
    assert versions_payload["versions"][0]["version"] == 2
    assert versions_payload["versions"][1]["version"] == 1

    list_latest_resp = client.get(f"/api/v1/projects/{project_id}/documents")
    assert list_latest_resp.status_code == 200
    latest_item = list_latest_resp.json()["items"][0]
    assert latest_item["latest_version"] == 2
    assert latest_item["versions_count"] == 2
    assert latest_item["title"] == "Consortium Agreement Updated"


def test_document_scope_validation(client):
    project_id, _, member_id = _create_project_partner_member(client)
    bad_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/upload",
        data={
            "scope": "wp",
            "title": "WP note without wp_id",
            "uploaded_by_member_id": member_id,
        },
        files={"file": ("missing-wp.txt", b"content", "text/plain")},
    )
    assert bad_resp.status_code == 400
    assert "wp_id is required" in bad_resp.json()["detail"]


def test_document_reindex_changes_status_and_creates_chunks(client):
    project_id, _, member_id = _create_project_partner_member(client)

    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/upload",
        data={
            "scope": "project",
            "title": "Proposal",
            "uploaded_by_member_id": member_id,
        },
        files={"file": ("proposal.txt", b"Alpha Beta Gamma Delta " * 120, "text/plain")},
    )
    assert upload_resp.status_code == 200
    document = upload_resp.json()
    assert document["status"] == "uploaded"

    reindex_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/{document['id']}/reindex?async_job=false"
    )
    assert reindex_resp.status_code == 200
    body = reindex_resp.json()
    assert body["queued"] is False
    assert body["status"] == "indexed"
    assert body["chunks_indexed"] > 0

    get_resp = client.get(f"/api/v1/projects/{project_id}/documents/{document['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "indexed"


def test_docx_document_reindex_extracts_text(client):
    project_id, _, member_id = _create_project_partner_member(client)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>First paragraph.</w:t></w:r></w:p>
    <w:p><w:r><w:t>Second paragraph.</w:t></w:r></w:p>
  </w:body>
</w:document>""",
        )
    docx_bytes = buffer.getvalue()

    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/upload",
        data={
            "scope": "project",
            "title": "Technical Note",
            "uploaded_by_member_id": member_id,
        },
        files={
            "file": (
                "technical-note.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_resp.status_code == 200
    document = upload_resp.json()

    reindex_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/{document['id']}/reindex?async_job=false"
    )
    assert reindex_resp.status_code == 200
    body = reindex_resp.json()
    assert body["status"] == "indexed"
    assert body["chunks_indexed"] > 0


def test_pdf_document_reindex_extracts_text(client):
    project_id, _, member_id = _create_project_partner_member(client)

    pdf_bytes = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 67 >>
stream
BT
/F1 12 Tf
72 200 Td
(Project proposal technical objectives) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000063 00000 n 
0000000122 00000 n 
0000000248 00000 n 
0000000365 00000 n 
trailer
<< /Root 1 0 R /Size 6 >>
startxref
435
%%EOF
"""

    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/upload",
        data={
            "scope": "project",
            "title": "Project Proposal",
            "uploaded_by_member_id": member_id,
        },
        files={
            "file": (
                "project-proposal.pdf",
                pdf_bytes,
                "application/pdf",
            )
        },
    )
    assert upload_resp.status_code == 200
    document = upload_resp.json()

    reindex_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/{document['id']}/reindex?async_job=false"
    )
    assert reindex_resp.status_code == 200
    body = reindex_resp.json()
    assert body["status"] == "indexed"
    assert body["chunks_indexed"] > 0
