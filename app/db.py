"""
Database layer — async SQLAlchemy + PostgreSQL.

Tables created on startup:
    ai_requests  — full audit log of every inference call
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ai_requests table
# ---------------------------------------------------------------------------

class AIRequest(Base):
    __tablename__ = "ai_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, unique=True, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    role = Column(String(64), nullable=False, index=True)
    model_used = Column(String(128), nullable=False, index=True)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float, nullable=False, default=0.0)
    status = Column(String(32), nullable=False, default="success")  # success | error | blocked
    prompt_preview = Column(Text, nullable=True)   # first 200 chars only
    error_detail = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a scoped async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Audit write helper
# ---------------------------------------------------------------------------

async def log_request(
    db: AsyncSession,
    *,
    request_id: str,
    user_email: str,
    role: str,
    model_used: str,
    tokens_in: int,
    tokens_out: int,
    estimated_cost: float,
    status: str,
    prompt_preview: str | None = None,
    error_detail: str | None = None,
    latency_ms: int | None = None,
) -> AIRequest:
    record = AIRequest(
        request_id=request_id,
        user_email=user_email,
        role=role,
        model_used=model_used,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        estimated_cost=estimated_cost,
        status=status,
        prompt_preview=prompt_preview,
        error_detail=error_detail,
        latency_ms=latency_ms,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Dashboard query helpers
# ---------------------------------------------------------------------------

async def get_summary(db: AsyncSession) -> dict:
    result = await db.execute(
        text(
            """
            SELECT
                COUNT(*)           AS total_requests,
                COALESCE(SUM(tokens_in), 0)   AS total_tokens_in,
                COALESCE(SUM(tokens_out), 0)  AS total_tokens_out,
                COALESCE(SUM(estimated_cost), 0.0) AS total_cost_usd
            FROM ai_requests
            """
        )
    )
    row = result.mappings().one()
    return dict(row)


async def get_requests_by_role(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT
                role,
                COUNT(*)                          AS count,
                COALESCE(SUM(estimated_cost), 0)  AS total_cost_usd
            FROM ai_requests
            GROUP BY role
            ORDER BY count DESC
            """
        )
    )
    return [dict(r) for r in result.mappings()]


async def get_model_usage(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT
                model_used,
                COUNT(*)                                   AS count,
                COALESCE(SUM(tokens_in + tokens_out), 0)   AS total_tokens,
                COALESCE(SUM(estimated_cost), 0)           AS total_cost_usd
            FROM ai_requests
            GROUP BY model_used
            ORDER BY count DESC
            """
        )
    )
    return [dict(r) for r in result.mappings()]


async def get_recent_requests(db: AsyncSession, limit: int = 50) -> list[AIRequest]:
    result = await db.execute(
        select(AIRequest).order_by(AIRequest.created_at.desc()).limit(limit)
    )
    return list(result.scalars())
