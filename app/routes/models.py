import logging
import time
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Depends

from app.config import settings
from app.schemas import ModelCard, ModelListResponse
from app.agy_adapter import agy_adapter

logger = logging.getLogger("proxy_agy.routes.models")
router = APIRouter()


async def verify_auth(authorization: Optional[str] = Header(None)):
    """Verify Bearer token if API_KEY is configured in settings."""
    if not settings.API_KEY:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/v1/models", response_model=ModelListResponse)
async def list_models(authorization: Optional[str] = Header(None, dependencies=[Depends(verify_auth)])):
    """List available models dynamically based on AGY CLI account tier capabilities."""
    cards = []
    current_time = int(time.time())

    cli_models = await agy_adapter.get_available_cli_models()

    # Curated models list for clean presentation in LiteLLM / OpenClaw
    curated_models = [
        ("gemini-3.8-flash", "Gemini 3.8 Flash (High)"),
        ("gemini-3.8-flash-low", "Gemini 3.8 Flash (Low)"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 (Thinking)"),
        ("claude-opus-4-6", "Claude Opus 4.6 (Thinking)"),
        ("gpt-oss-120b", "GPT-OSS 120B (Medium)"),
    ]

    # Dynamically include Argon only if recognized by account
    if any("argon" in m.lower() for m in cli_models):
        curated_models.append(("gemini-4-argon", "Gemini 4 Argon"))

    for model_id, root_model in curated_models:
        cards.append(
            ModelCard(
                id=model_id,
                created=current_time,
                owned_by="antigravity",
                root=root_model
            )
        )

    return ModelListResponse(data=cards)


@router.get("/v1/models/{model_id}", response_model=ModelCard)
async def get_model(model_id: str, authorization: Optional[str] = Header(None, dependencies=[Depends(verify_auth)])):
    """Get details for a specific model."""
    resolved = settings.resolve_model(model_id)
    return ModelCard(
        id=model_id,
        created=int(time.time()),
        owned_by="antigravity",
        root=resolved
    )
