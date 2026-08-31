from fastapi import Header, HTTPException, Depends
from src.config import settings

async def validate_shared_secret(x_shared_secret: str = Header(..., alias="X-Shared-Secret")):
    """
    Validates the shared secret passed from the frontend for all normal endpoints.
    """
    if x_shared_secret != settings.application_secret:
        raise HTTPException(status_code=401, detail="Invalid application secret header.")
    return x_shared_secret
