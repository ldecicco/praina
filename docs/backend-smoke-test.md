# Backend Smoke Test

Run these commands after installation and server start (`uvicorn app.main:app --reload`).

## 1) Health
```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

## 2) Create project
```bash
PROJECT=$(curl -s -X POST http://127.0.0.1:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"code":"HEU-ALPHA","title":"Alpha Research Program","description":"Smoke test"}')
echo "$PROJECT"
PROJECT_ID=$(echo "$PROJECT" | jq -r .id)
```

## 3) Add partner
```bash
PARTNER=$(curl -s -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/partners \
  -H "Content-Type: application/json" \
  -d '{"short_name":"UNIROMA","legal_name":"Sapienza University of Rome"}')
echo "$PARTNER"
ORG_ID=$(echo "$PARTNER" | jq -r .id)
```

## 4) Add team
```bash
TEAM=$(curl -s -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/teams \
  -H "Content-Type: application/json" \
  -d "{\"organization_id\":\"$ORG_ID\",\"name\":\"WP1 Engineering Team\"}")
echo "$TEAM"
TEAM_ID=$(echo "$TEAM" | jq -r .id)
```

## 5) Add member
```bash
MEMBER=$(curl -s -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/members \
  -H "Content-Type: application/json" \
  -d "{\"organization_id\":\"$ORG_ID\",\"team_id\":\"$TEAM_ID\",\"full_name\":\"Giulia Rossi\",\"email\":\"giulia.rossi@example.org\",\"role\":\"WP Leader\"}")
echo "$MEMBER"
MEMBER_ID=$(echo "$MEMBER" | jq -r .id)
```

## 6) Add work package
```bash
WP=$(curl -s -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/work-packages \
  -H "Content-Type: application/json" \
  -d "{\"code\":\"WP1\",\"title\":\"Platform Foundation\",\"description\":\"Core architecture\",\"assignment\":{\"leader_organization_id\":\"$ORG_ID\",\"responsible_person_id\":\"$MEMBER_ID\",\"collaborating_team_ids\":[\"$TEAM_ID\"]}}")
echo "$WP"
```

## 7) Validate and activate
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/validate
curl -s -X POST http://127.0.0.1:8000/api/v1/projects/$PROJECT_ID/activate
```

