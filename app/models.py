"""
Pydantic models for request/response validation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    """Payload sent to POST /generate."""
    prompt: str = Field(..., min_length=1, max_length=32_000, description="User prompt")
    model: Optional[str] = Field(None, description="Target model. Defaults to role-based default.")
    max_tokens: Optional[int] = Field(None, ge=1, le=8000, description="Max tokens to generate")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    system_prompt: Optional[str] = Field(None, max_length=4000, description="Optional system message")


class GenerateResponse(BaseModel):
    """Payload returned from POST /generate."""
    request_id: str
    model_used: str
    content: str
    tokens_in: int
    tokens_out: int
    estimated_cost_usd: float
    latency_ms: int


class ErrorResponse(BaseModel):
    """Standard error envelope."""
    request_id: str
    error: str
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    """Used to issue a JWT for testing/demo purposes."""
    email: EmailStr
    role: str = Field(..., pattern="^(admin|employee|analyst)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Admin / Dashboard schemas
# ---------------------------------------------------------------------------

class RequestSummary(BaseModel):
    total_requests: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float


class RequestByRole(BaseModel):
    role: str
    count: int
    total_cost_usd: float


class ModelUsage(BaseModel):
    model_used: str
    count: int
    total_tokens: int
    total_cost_usd: float


# ---------------------------------------------------------------------------
# DB row representation
# ---------------------------------------------------------------------------

class AuditRecord(BaseModel):
    """Mirrors the ai_requests table row."""
    id: int
    request_id: str
    user_email: str
    role: str
    model_used: str
    tokens_in: int
    tokens_out: int
    estimated_cost: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
