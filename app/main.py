"""Enterprise AI Control Plane - FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    require_any,
    verify_password,
)
from app.config import get_settings
from app.db import close_db, get_db, init_db
from app.models import (
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    TokenResponse,
    TokenData,
    UserRole,
)
from app.policy import enforce_model_access, enforce_token_limit
from app.router import dispatch
from app import admin as admin_router

settings = get_settings()

# ---------------------------------------------------------------------------
# Demo in-memory user store (replace with DB in production)
# ---------------------------------------------------------------------------
_DEMO_USERS: dict = {
    "admin": {
        "hashed_password": hash_password("admin123"),
        "role": UserRole.ADMIN,
    },
    "dev": {
        "hashed_password": hash_password("dev123"),
        "role": UserRole.DEVELOPER,
    },
    "viewer": {
        "hashed_password": hash_password("viewer123"),
        "role": UserRole.VIEWER,
    },
}


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield
    await close_db()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Enterprise AI Control Plane",
    description="Centralized AI gateway with JWT auth, RBAC, audit logging, and cost tracking.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount admin sub-application
app.include_router(admin_router.router, prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    """Liveness probe — no auth required."""
    return HealthResponse(status="ok", version=app.version)


# ---------------------------------------------------------------------------
# Auth: issue JWT
# ---------------------------------------------------------------------------
@app.post("/auth/token", response_model=TokenResponse, tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Exchange username + password for a JWT access token."""
    user = _DEMO_USERS.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=form_data.username, role=user["role"])
    return TokenResponse(access_token=token, token_type="bearer", role=user["role"].value)


# ---------------------------------------------------------------------------
# Generate endpoint
# ---------------------------------------------------------------------------
@app.post("/generate", response_model=GenerateResponse, tags=["Gateway"])
async def generate(
    req: GenerateRequest,
    current_user: TokenData = Depends(require_any),
    db=Depends(get_db),
) -> GenerateResponse:
    """Route a prompt to the appropriate LLM and return the response."""
    # Policy checks
    enforce_model_access(current_user.role, req.model)
    enforce_token_limit(current_user.role, req.max_tokens)

    # Dispatch to backend
    response = await dispatch(req)

    # Audit log
    await db.execute(
        """
        INSERT INTO ai_requests
            (username, role, model, provider, prompt_tokens, completion_tokens,
             total_tokens, latency_ms, estimated_cost_usd)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
        current_user.username,
        current_user.role.value,
        response.model,
        response.provider,
        response.prompt_tokens,
        response.completion_tokens,
        response.total_tokens,
        response.latency_ms,
        _estimate_cost(response.provider, response.model, response.total_tokens),
    )

    return response


def _estimate_cost(provider: str, model: str, total_tokens: int) -> float:
    """Very rough cost estimate in USD based on provider / model."""
    rates: dict = {
        "gpt-4o": 5.00 / 1_000_000,
        "gpt-4o-mini": 0.15 / 1_000_000,
        "gpt-4-turbo": 10.00 / 1_000_000,
        "gpt-4": 30.00 / 1_000_000,
        "gpt-3.5-turbo": 0.50 / 1_000_000,
    }
    if provider == "ollama":
        return 0.0
    return rates.get(model, 1.00 / 1_000_000) * total_tokens
