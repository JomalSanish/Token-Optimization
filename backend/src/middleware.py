from typing import Optional
from fastapi import Header, HTTPException
from src.config import settings

async def validate_shared_secret(
    x_shared_secret: Optional[str] = Header(None, alias="X-Shared-Secret"),
    x_app_secret: Optional[str] = Header(None, alias="X-App-Secret"),
):
    """
    Validates the shared secret passed from the frontend for all normal endpoints.
    Accepts either X-Shared-Secret or X-App-Secret.
    """
    secret = x_shared_secret or x_app_secret
    if not secret:
        raise HTTPException(status_code=422, detail="Missing required application secret header.")
    if secret != settings.application_secret:
        raise HTTPException(status_code=401, detail="Invalid application secret header.")
    return secret
