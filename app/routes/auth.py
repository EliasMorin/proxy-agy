import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import auth_manager, check_auth_async

logger = logging.getLogger("proxy_agy.routes.auth")
router = APIRouter()


class TokenSubmissionRequest(BaseModel):
    token: Optional[str] = None
    code: Optional[str] = None


class AuthStatusResponse(BaseModel):
    authenticated: bool
    status: str
    login_url: Optional[str] = None
    message: Optional[str] = None


class AuthSessionResponse(BaseModel):
    success: bool
    login_url: Optional[str] = None
    message: str


@router.get("/v1/auth/status", response_model=AuthStatusResponse)
async def get_auth_status():
    """Get current authentication status."""
    is_auth = await check_auth_async(force_recheck=False)
    return AuthStatusResponse(
        authenticated=is_auth,
        status="authenticated" if is_auth else "unauthenticated",
        login_url=auth_manager.current_oauth_url,
        message=auth_manager.login_message,
    )


@router.get("/v1/auth/session", response_model=AuthSessionResponse)
@router.post("/v1/auth/session", response_model=AuthSessionResponse)
async def get_or_create_auth_session():
    """
    Trigger an interactive agy CLI process to generate a real-time dynamic Google OAuth2 URL.
    """
    loop = asyncio.get_running_loop()
    success, oauth_url, msg = await loop.run_in_executor(None, auth_manager.start_auth_session)
    if not success or not oauth_url:
        raise HTTPException(
            status_code=500,
            detail={"message": msg, "type": "oauth_session_creation_failed"}
        )
    return AuthSessionResponse(
        success=True,
        login_url=oauth_url,
        message=msg
    )


@router.post("/v1/auth/login")
async def submit_auth_code(req: TokenSubmissionRequest):
    """
    Submit authorization code to the active agy CLI process via PTY stdin.
    """
    auth_code = (req.code or req.token or "").strip()
    if not auth_code:
        raise HTTPException(
            status_code=400,
            detail={"message": "Authorization code 不能为空", "type": "missing_code"}
        )

    loop = asyncio.get_running_loop()
    success, msg = await loop.run_in_executor(None, auth_manager.submit_auth_code, auth_code)
    if not success:
        raise HTTPException(
            status_code=400,
            detail={"message": msg, "type": "auth_verification_failed"}
        )
    return {"status": "ok", "message": msg, "authenticated": True}


@router.post("/v1/auth/reset")
async def reset_auth_session():
    """Reset and cancel active auth login session."""
    auth_manager.close_active_session()
    return {"status": "ok", "message": "Auth session reset"}
