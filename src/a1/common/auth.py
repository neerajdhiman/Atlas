import hashlib

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

security = HTTPBearer(auto_error=False)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> str:
    """Verify API key from Bearer token. Returns the key if valid."""
    # If no API keys configured, allow all (dev mode)
    if not settings.api_keys:
        return "dev"

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing API key")

    key = credentials.credentials
    if key not in settings.api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return key
