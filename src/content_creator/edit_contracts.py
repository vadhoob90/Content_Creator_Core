"""Define author-edit requests and exact-content claim review decisions."""

from typing import Literal

from pydantic import BaseModel, Field

from .domain import ResearchBrief


class AuthorEditRequest(BaseModel):
    """Describe one idempotent adoption of author-supplied Markdown."""

    draft: str = Field(min_length=1)
    expected_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1)
    baseline: str | None = None
    research: ResearchBrief | None = None


class ClaimReviewDecision(BaseModel):
    """Bind an explicit claim review to the exact text and supporting research."""

    schema_version: Literal["1.0"] = "1.0"
    draft_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    research_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    approved_by: str = Field(min_length=1)
    notes: str = Field(min_length=1)
