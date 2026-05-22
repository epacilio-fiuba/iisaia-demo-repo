import os
from fastapi import Header, HTTPException, status


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("DEMO_BEARER_TOKEN", "changeme-in-real-env")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid bearer token")
