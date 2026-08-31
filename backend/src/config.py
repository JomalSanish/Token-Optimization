import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env file if it exists locally
load_dotenv()

class Settings(BaseModel):
    mongodb_uri: str = Field(..., alias="MONGODB_URI")
    mongodb_database: str = Field("token_optimizer", alias="MONGODB_DATABASE")
    
    # Shared secret between frontend and backend to protect normal endpoints
    application_secret: str = Field(..., alias="APPLICATION_SECRET")
    
    # Secret used to validate Bearer token for admin endpoints
    admin_auth_secret: str = Field(..., alias="ADMIN_AUTH_SECRET")
    
    cors_origins: str = Field("*", alias="CORS_ORIGINS")
    app_env: str = Field("development", alias="APP_ENV")

# Perform eager validation during startup
try:
    # Resolve aliases from raw os.environ
    raw_env = {
        "MONGODB_URI": os.environ.get("MONGODB_URI"),
        "MONGODB_DATABASE": os.environ.get("MONGODB_DATABASE", "token_optimizer"),
        "APPLICATION_SECRET": os.environ.get("APPLICATION_SECRET"),
        "ADMIN_AUTH_SECRET": os.environ.get("ADMIN_AUTH_SECRET"),
        "CORS_ORIGINS": os.environ.get("CORS_ORIGINS", "*"),
        "APP_ENV": os.environ.get("APP_ENV", "development"),
    }
    
    # Validate
    settings = Settings(**{k: v for k, v in raw_env.items() if v is not None})
except Exception as e:
    raise RuntimeError(
        f"Configuration validation failed: {str(e)}. "
        "Please ensure MONGODB_URI, APPLICATION_SECRET, and ADMIN_AUTH_SECRET are defined in environment variables."
    )
