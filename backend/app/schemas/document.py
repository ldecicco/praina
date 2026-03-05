from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    project_id: str
    scope: str
    title: str
    storage_uri: str
    mime_type: str
    wp_id: str | None = None
    task_id: str | None = None
    deliverable_id: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class DocumentRead(BaseModel):
    id: str
    project_id: str
    scope: str
    title: str
    status: str
    version: int
