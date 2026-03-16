from pydantic import BaseModel


class MyWorkItem(BaseModel):
    item_type: str
    entity_id: str
    project_id: str
    project_code: str
    project_title: str
    code: str | None = None
    title: str
    status: str
    role: str
    priority: str | None = None
    due_date: str | None = None
    due_month: int | None = None


class MyWorkProjectGroup(BaseModel):
    project_id: str
    project_code: str
    project_title: str
    project_mode: str
    items: list[MyWorkItem]


class MyWorkResponse(BaseModel):
    groups: list[MyWorkProjectGroup]
    total_items: int
