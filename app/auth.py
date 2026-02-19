"""JWT Authentication middleware for Enterprise AI Control Plane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.models import TokenData, UserRole

settings = get_settings()

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# JWT bearer scheme
# ---------------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=True)


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain* text password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------
def create_access_token(
    subject: str,
    role: UserRole,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create and return a signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "role": role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Token verification / dependency
# ---------------------------------------------------------------------------
def _decode_token(token: str) -> TokenData:
    """Decode JWT and return TokenData; raise 401 on any failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: Optional[str] = payload.get("sub")
        role_str: Optional[str] = payload.get("role")
        if username is None or role_str is None:
            raise credentials_exception
        return TokenData(username=username, role=UserRole(role_str))
    except (JWTError, ValueError):
        raise credentials_exception


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> TokenData:
    """FastAPI dependency: validate Bearer token and return parsed TokenData."""
    return _decode_token(credentials.credentials)


def require_role(*allowed_roles: UserRole):
    """Return a FastAPI dependency that enforces *allowed_roles*."""

    def _checker(
        current_user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted for this endpoint.",
            )
        return current_user

    return _checker


# Convenience pre-built role guards
require_admin = require_role(UserRole.ADMIN)
require_any = require_role(UserRole.ADMIN, UserRole.DEVELOPER, UserRole.VIEWER)
