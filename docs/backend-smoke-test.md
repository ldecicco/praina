# Backend Smoke Test

Run these commands after installation and server start (`uvicorn app.main:app --reload`).
Load backend env variables first:

```bash
cd backend
set -a && source .env && set +a
```

## 1) Health
```bash
curl -s "http://$APP_HOST:$APP_PORT/api/v1/health"
```

## 2) Create project
```bash
PROJECT=$(curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects" \
  -H "Content-Type: application/json" \
  -d '{"code":"HEU-ALPHA","title":"Alpha Research Program","description":"Smoke test"}')
echo "$PROJECT"
PROJECT_ID=$(echo "$PROJECT" | jq -r .id)
```

## 3) Add partner
```bash
PARTNER=$(curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/partners" \
  -H "Content-Type: application/json" \
  -d '{"short_name":"UNIROMA","legal_name":"Sapienza University of Rome"}')
echo "$PARTNER"
ORG_ID=$(echo "$PARTNER" | jq -r .id)
```

## 4) Add member
```bash
MEMBER=$(curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/members" \
  -H "Content-Type: application/json" \
  -d "{\"partner_id\":\"$ORG_ID\",\"full_name\":\"Giulia Rossi\",\"email\":\"giulia.rossi@example.org\",\"role\":\"WP Leader\"}")
echo "$MEMBER"
MEMBER_ID=$(echo "$MEMBER" | jq -r .id)
```

## 5) Add work package
```bash
WP=$(curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/work-packages" \
  -H "Content-Type: application/json" \
  -d "{\"code\":\"WP1\",\"title\":\"Platform Foundation\",\"description\":\"Core architecture\",\"assignment\":{\"leader_organization_id\":\"$ORG_ID\",\"responsible_person_id\":\"$MEMBER_ID\",\"collaborating_partner_ids\":[\"$ORG_ID\"]}}")
echo "$WP"
```

## 6) Validate and activate
```bash
curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/validate"
curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/activate"
```

## 7) Upload project document
```bash
DOC_V1=$(curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents/upload" \
  -F "file=@./README.md;type=text/markdown" \
  -F "scope=project" \
  -F "title=Project Proposal" \
  -F 'metadata_json={"category":"proposal"}' \
  -F "uploaded_by_member_id=$MEMBER_ID")
echo "$DOC_V1"
DOC_ID=$(echo "$DOC_V1" | jq -r .id)
DOC_KEY=$(echo "$DOC_V1" | jq -r .document_key)
```

## 8) Upload a new version
```bash
DOC_V2=$(curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents/$DOC_KEY/versions/upload" \
  -F "file=@./README.md;type=text/markdown" \
  -F "title=Project Proposal v2" \
  -F 'metadata_json={"category":"proposal","revision":"2"}')
echo "$DOC_V2"
```

## 9) List latest documents
```bash
curl -s "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents"
```

## 10) Fetch one document version and full version history
```bash
curl -s "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents/$DOC_ID"
curl -s "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents/by-key/$DOC_KEY/versions"
```

## 11) Reindex latest document version
```bash
DOC_LATEST_ID=$(curl -s "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents" | jq -r '.items[0].latest_document_id')
curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects/$PROJECT_ID/documents/$DOC_LATEST_ID/reindex?async_job=false"
```
