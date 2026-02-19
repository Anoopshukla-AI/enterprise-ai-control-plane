"""Model router: dispatches prompts to OpenAI or Ollama backends."""
from __future__ import annotations

import time
from typing import Any, Dict

import httpx
import openai

from app.config import get_settings
from app.models import GenerateRequest, GenerateResponse

settings = get_settings()

# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------
_OPENAI_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
}


def _is_openai_model(model: str) -> bool:
    """Return True if *model* should be routed to OpenAI."""
    return model in _OPENAI_MODELS or model.startswith("gpt-")


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------
async def _call_openai(req: GenerateRequest) -> Dict[str, Any]:
    """Forward *req* to the OpenAI chat completions endpoint."""
    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=req.model,
        messages=[{"role": "user", "content": req.prompt}],
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    choice = response.choices[0]
    usage = response.usage
    return {
        "text": choice.message.content or "",
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------
async def _call_ollama(req: GenerateRequest) -> Dict[str, Any]:
    """Forward *req* to the local Ollama /api/generate endpoint."""
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": False,
        "options": {
            "num_predict": req.max_tokens,
            "temperature": req.temperature,
        },
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    text: str = data.get("response", "")
    # Ollama does not return token counts in non-stream mode consistently
    prompt_tokens: int = data.get("prompt_eval_count", 0)
    completion_tokens: int = data.get("eval_count", 0)
    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


# ---------------------------------------------------------------------------
# Public dispatch function
# ---------------------------------------------------------------------------
async def dispatch(req: GenerateRequest) -> GenerateResponse:
    """Route *req* to the appropriate backend and return a GenerateResponse."""
    t0 = time.perf_counter()

    if _is_openai_model(req.model):
        result = await _call_openai(req)
        provider = "openai"
    else:
        result = await _call_ollama(req)
        provider = "ollama"

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return GenerateResponse(
        text=result["text"],
        model=req.model,
        provider=provider,
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
        total_tokens=result["total_tokens"],
        latency_ms=latency_ms,
    )
