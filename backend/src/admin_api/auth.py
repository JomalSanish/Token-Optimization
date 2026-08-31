from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings

security = HTTPBearer()

async def validate_admin_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Validates that the request has a Bearer token matching ADMIN_AUTH_SECRET.
    """
    token = credentials.credentials
    if token != settings.admin_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing administrator credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token
