"""Admin dashboard router — aggregated stats from the ai_requests audit table."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.db import get_db
from app.models import (
    AdminStats,
    ModelUsageStat,
    RoleUsageStat,
    TokenData,
)

router = APIRouter()


@router.get("/stats", response_model=AdminStats)
async def get_stats(
    current_user: TokenData = Depends(require_admin),
    db=Depends(get_db),
) -> AdminStats:
    """Return aggregated request statistics (admin-only)."""
    # Total requests
    total_row = await db.fetchrow("SELECT COUNT(*) AS cnt FROM ai_requests")
    total_requests: int = total_row["cnt"] if total_row else 0

    # Total tokens & cost
    agg_row = await db.fetchrow(
        """
        SELECT
            COALESCE(SUM(total_tokens), 0)          AS total_tokens,
            COALESCE(SUM(estimated_cost_usd), 0.0)  AS total_cost
        FROM ai_requests
        """
    )
    total_tokens: int = int(agg_row["total_tokens"]) if agg_row else 0
    total_cost: float = float(agg_row["total_cost"]) if agg_row else 0.0

    # By role
    role_rows = await db.fetch(
        """
        SELECT role, COUNT(*) AS cnt
        FROM ai_requests
        GROUP BY role
        ORDER BY cnt DESC
        """
    )
    by_role: List[RoleUsageStat] = [
        RoleUsageStat(role=r["role"], request_count=r["cnt"]) for r in role_rows
    ]

    # By model
    model_rows = await db.fetch(
        """
        SELECT
            model,
            provider,
            COUNT(*)                                AS request_count,
            COALESCE(SUM(total_tokens), 0)          AS total_tokens,
            COALESCE(SUM(estimated_cost_usd), 0.0)  AS total_cost
        FROM ai_requests
        GROUP BY model, provider
        ORDER BY request_count DESC
        """
    )
    by_model: List[ModelUsageStat] = [
        ModelUsageStat(
            model=m["model"],
            provider=m["provider"],
            request_count=m["request_count"],
            total_tokens=int(m["total_tokens"]),
            total_cost_usd=float(m["total_cost"]),
        )
        for m in model_rows
    ]

    return AdminStats(
        total_requests=total_requests,
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 6),
        by_role=by_role,
        by_model=by_model,
    )


@router.get("/requests", tags=["Admin"])
async def list_requests(
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_admin),
    db=Depends(get_db),
) -> list:
    """Paginated raw audit log (admin-only)."""
    rows = await db.fetch(
        """
        SELECT id, created_at, username, role, model, provider,
               prompt_tokens, completion_tokens, total_tokens,
               latency_ms, estimated_cost_usd
        FROM ai_requests
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [dict(r) for r in rows]
