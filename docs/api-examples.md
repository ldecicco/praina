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

## Add Team
`POST /api/v1/projects/{project_id}/teams`

Request:
```json
{
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "name": "WP1 Engineering Team"
}
```

Response:
```json
{
  "id": "22222222-2222-2222-2222-222222222222",
  "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "name": "WP1 Engineering Team"
}
```

## Add Team Member
`POST /api/v1/projects/{project_id}/members`

Request:
```json
{
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "team_id": "22222222-2222-2222-2222-222222222222",
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
  "organization_id": "11111111-1111-1111-1111-111111111111",
  "team_id": "22222222-2222-2222-2222-222222222222",
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
    "collaborating_team_ids": [
      "22222222-2222-2222-2222-222222222222"
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
  "collaborating_team_ids": [
    "22222222-2222-2222-2222-222222222222"
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
