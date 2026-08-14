import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import database
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


async def _find_user_by_email(email: str) -> User | None:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    user = await User.find_one(User.email == normalized)
    if user:
        return user
    return await User.find_one(
        {"email": {"$regex": f"^{re.escape(normalized)}$", "$options": "i"}}
    )


def _password_matches(password: str, hashed: str | None) -> bool:
    if not password or not hashed:
        return False
    try:
        return bool(pwd_context.verify(password, hashed))
    except Exception:
        return False


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None

    @field_validator("email")
    @classmethod
    def _normalize_register_email(cls, value: str) -> str:
        email = _normalize_email(value)
        if not email:
            raise ValueError("Email is required")
        return email


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_login_email(cls, value: str) -> str:
        email = _normalize_email(value)
        if not email:
            raise ValueError("Email is required")
        return email


class RefreshRequest(BaseModel):
    refresh_token: str


def _create_token(subject: str, token_type: str, ttl: timedelta) -> str:
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": datetime.now(timezone.utc) + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: RegisterRequest):
    try:
        existing = await _find_user_by_email(payload.email)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Please try again in a moment.",
        ) from exc
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=pwd_context.hash(payload.password),
        full_name=payload.full_name,
    )
    try:
        await user.insert()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create account right now. Please try again.",
        ) from exc

    user_id = str(user.id)
    access_token = _create_token(user_id, "access", timedelta(hours=24))
    refresh_token = _create_token(user_id, "refresh", timedelta(days=30))

    try:
        await database["refresh_tokens"].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "refresh_token": refresh_token,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not complete signup right now. Please try again.",
        ) from exc

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {"id": user_id, "email": user.email, "full_name": user.full_name},
    }


@router.post("/login")
async def login(payload: LoginRequest):
    try:
        user = await _find_user_by_email(payload.email)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Please try again in a moment.",
        ) from exc
    if not user or not _password_matches(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(user.id)
    access_token = _create_token(user_id, "access", timedelta(hours=24))
    refresh_token = _create_token(user_id, "refresh", timedelta(days=30))

    try:
        await database["refresh_tokens"].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "refresh_token": refresh_token,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not complete sign in right now. Please try again.",
        ) from exc

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/refresh")
async def refresh_access_token(payload: RefreshRequest):
    try:
        decoded = jwt.decode(payload.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    token_doc = await database["refresh_tokens"].find_one({"user_id": user_id})
    if not token_doc or token_doc.get("refresh_token") != payload.refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token mismatch")

    access_token = _create_token(user_id, "access", timedelta(hours=24))
    new_refresh_token = _create_token(user_id, "refresh", timedelta(days=30))
    await database["refresh_tokens"].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "refresh_token": new_refresh_token,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
            }
        },
    )
    return {"access_token": access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
    }
