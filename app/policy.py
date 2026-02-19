"""YAML-based policy engine for role-based model access control."""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Dict, List

import yaml
from fastapi import HTTPException, status

from app.models import UserRole

# Default policy file location (can be overridden via env)
_DEFAULT_POLICY_PATH = Path(__file__).parent.parent / "policies" / "policy.yaml"


@functools.lru_cache(maxsize=1)
def _load_policy(policy_path: str = str(_DEFAULT_POLICY_PATH)) -> Dict:
    """Load and cache the YAML policy file from *policy_path*."""
    path = Path(policy_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_allowed_models(role: UserRole) -> List[str]:
    """Return list of model IDs allowed for *role* according to policy.yaml."""
    policy = _load_policy()
    roles_cfg: Dict = policy.get("roles", {})
    role_cfg: Dict = roles_cfg.get(role.value, {})
    return role_cfg.get("allowed_models", [])


def get_max_tokens(role: UserRole) -> int:
    """Return the max token limit for *role* according to policy.yaml."""
    policy = _load_policy()
    roles_cfg: Dict = policy.get("roles", {})
    role_cfg: Dict = roles_cfg.get(role.value, {})
    return int(role_cfg.get("max_tokens", 512))


def enforce_model_access(role: UserRole, model: str) -> None:
    """Raise HTTP 403 if *role* is not permitted to use *model*."""
    allowed = get_allowed_models(role)
    # Empty list means no models allowed at all
    if not allowed or model not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{role.value}' is not permitted to access model '{model}'. "
                f"Allowed models: {allowed or 'none'}"
            ),
        )


def enforce_token_limit(role: UserRole, requested_tokens: int) -> None:
    """Raise HTTP 400 if *requested_tokens* exceeds the role limit."""
    limit = get_max_tokens(role)
    if requested_tokens > limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested max_tokens={requested_tokens} exceeds the limit of "
                f"{limit} for role '{role.value}'."
            ),
        )


def reload_policy() -> None:
    """Invalidate the cached policy so the next call reloads from disk."""
    _load_policy.cache_clear()
