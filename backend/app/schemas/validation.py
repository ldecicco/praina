"""Schemas for validation, coherence, and governance responses."""

from __future__ import annotations

from pydantic import BaseModel


class GovernanceDecisionRead(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    policy_refs: list[str] = []
