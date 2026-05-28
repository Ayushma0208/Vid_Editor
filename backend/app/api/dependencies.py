from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.models.user import User


security = HTTPBearer()


def _decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return user_id


def resolve_user_id_from_token(token: str = "", request: Request | None = None) -> str:
    """Accept JWT from ?token= query param or Authorization: Bearer header."""
    resolved = token.strip()
    if not resolved and request is not None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            resolved = auth_header.split(" ", 1)[1].strip()
    if not resolved:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")
    return _decode_access_token(resolved)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    return _decode_access_token(credentials.credentials)


async def get_current_user(user_id: str = Depends(get_current_user_id)) -> User:
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
