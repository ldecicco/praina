import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


class CoherenceIssueRead(BaseModel):
    category: str
    entity_ids: list[str] = Field(default_factory=list)
    message: str
    suggestion: str = ""
    severity: str = "warning"


class CoherenceReportRead(BaseModel):
    project_id: str
    issues: list[CoherenceIssueRead] = Field(default_factory=list)
    checked_at: str = ""


@router.post("/{project_id}/coherence-check", response_model=CoherenceReportRead)
def coherence_check(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> CoherenceReportRead:
    from app.agents.coherence_agent import CoherenceAgent

    agent = CoherenceAgent()
    report = agent.check_project(project_id, db)

    return CoherenceReportRead(
        project_id=report.project_id,
        issues=[
            CoherenceIssueRead(
                category=i.category,
                entity_ids=i.entity_ids,
                message=i.message,
                suggestion=i.suggestion,
                severity=i.severity,
            )
            for i in report.issues
        ],
        checked_at=report.checked_at,
    )
