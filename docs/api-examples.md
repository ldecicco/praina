# API JSON Examples (MVP)

## Create Project
`POST /api/v1/projects`

Request:
```json
{
  "code": "HEU-ALPHA",
  "title": "Alpha Research Program",
  "description": "AI-first coordination for a multi-partner consortium."
}
```

Response:
```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "code": "HEU-ALPHA",
  "title": "Alpha Research Program",
  "description": "AI-first coordination for a multi-partner consortium.",
  "baseline_version": 0,
  "status": "draft"
}
```

## Add Partner
`POST /api/v1/projects/{project_id}/partners`

Request:
```json
{
  "short_name": "UNIROMA",
  "legal_name": "Sapienza University of Rome"
}
```

Response:
```json
{
  "id": "11111111-1111-1111-1111-111111111111",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "short_name": "UNIROMA",
  "legal_name": "Sapienza University of Rome"
}
```

## Add Partner Member
`POST /api/v1/projects/{project_id}/members`

Request:
```json
{
  "partner_id": "11111111-1111-1111-1111-111111111111",
  "full_name": "Giulia Rossi",
  "email": "giulia.rossi@example.org",
  "role": "WP Leader"
}
```

Response:
```json
{
  "id": "33333333-3333-3333-3333-333333333333",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "partner_id": "11111111-1111-1111-1111-111111111111",
  "full_name": "Giulia Rossi",
  "email": "giulia.rossi@example.org",
  "role": "WP Leader",
  "is_active": true
}
```

## Add Work Package
`POST /api/v1/projects/{project_id}/work-packages`

Request:
```json
{
  "code": "WP1",
  "title": "Platform Foundation",
  "description": "Core platform architecture and integration.",
  "assignment": {
    "leader_organization_id": "11111111-1111-1111-1111-111111111111",
    "responsible_person_id": "33333333-3333-3333-3333-333333333333",
    "collaborating_partner_ids": [
      "11111111-1111-1111-1111-111111111111"
    ]
  }
}
```

Response:
```json
{
  "id": "44444444-4444-4444-4444-444444444444",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "code": "WP1",
  "title": "Platform Foundation",
  "description": "Core platform architecture and integration.",
  "leader_organization_id": "11111111-1111-1111-1111-111111111111",
  "responsible_person_id": "33333333-3333-3333-3333-333333333333",
  "collaborating_partner_ids": [
    "11111111-1111-1111-1111-111111111111"
  ]
}
```

## Validate Project Before Activation
`POST /api/v1/projects/{project_id}/validate`

Response:
```json
{
  "valid": false,
  "errors": [
    {
      "entity_type": "task",
      "entity_id": "55555555-5555-5555-5555-555555555555",
      "code": "RESPONSIBLE_NOT_IN_LEADER_ORG",
      "message": "Responsible person must belong to the selected leader organization."
    }
  ],
  "warnings": []
}
```

## Activate Project
`POST /api/v1/projects/{project_id}/activate`

Response:
```json
{
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "status": "active",
  "baseline_version": 1,
  "audit_event_id": "66666666-6666-6666-6666-666666666666"
}
```

## Upload Project Document (Multipart)
`POST /api/v1/projects/{project_id}/documents/upload`

Example `curl`:
```bash
curl -X POST "http://127.0.0.1:9999/api/v1/projects/{project_id}/documents/upload" \
  -F "file=@./consortium-agreement.pdf;type=application/pdf" \
  -F "scope=project" \
  -F "title=Consortium Agreement" \
  -F 'metadata_json={"category":"legal"}' \
  -F "uploaded_by_member_id=33333333-3333-3333-3333-333333333333"
```

Response:
```json
{
  "id": "77777777-7777-7777-7777-777777777777",
  "document_key": "88888888-8888-8888-8888-888888888888",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "scope": "project",
  "title": "Consortium Agreement",
  "version": 1,
  "status": "uploaded",
  "storage_uri": "/abs/path/storage/documents/...",
  "original_filename": "consortium-agreement.pdf",
  "file_size_bytes": 124000,
  "mime_type": "application/pdf",
  "metadata_json": {
    "category": "legal"
  }
}
```

## Upload New Version
`POST /api/v1/projects/{project_id}/documents/{document_key}/versions/upload`

Example `curl`:
```bash
curl -X POST "http://127.0.0.1:9999/api/v1/projects/{project_id}/documents/{document_key}/versions/upload" \
  -F "file=@./consortium-agreement-v2.pdf;type=application/pdf" \
  -F "title=Consortium Agreement (rev2)" \
  -F 'metadata_json={"category":"legal","revision":"2"}'
```

Response:
```json
{
  "id": "99999999-9999-9999-9999-999999999999",
  "document_key": "88888888-8888-8888-8888-888888888888",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "scope": "project",
  "title": "Consortium Agreement (rev2)",
  "version": 2,
  "status": "uploaded"
}
```

## Reindex One Document Version
`POST /api/v1/projects/{project_id}/documents/{document_id}/reindex?async_job=false`

Response:
```json
{
  "document_id": "99999999-9999-9999-9999-999999999999",
  "status": "indexed",
  "chunks_indexed": 14,
  "queued": false,
  "error": null
}
```
