from pydantic import BaseModel


class ChatOpsCommandRequest(BaseModel):
    project_id: str
    user_id: str
    text: str


class ChatOpsProposal(BaseModel):
    proposal_id: str
    summary: str
    requires_confirmation: bool = True
    structured_action: dict


class ChatOpsConfirmationRequest(BaseModel):
    proposal_id: str
    confirmed: bool
    reason: str | None = None

