from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import database
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


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
    existing = await User.find_one(User.email == payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=pwd_context.hash(payload.password),
        full_name=payload.full_name,
    )
    await user.insert()

    user_id = str(user.id)
    access_token = _create_token(user_id, "access", timedelta(hours=24))
    refresh_token = _create_token(user_id, "refresh", timedelta(days=30))

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

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {"id": user_id, "email": user.email, "full_name": user.full_name},
    }


@router.post("/login")
async def login(payload: LoginRequest):
    user = await User.find_one(User.email == payload.email)
    if not user or not pwd_context.verify(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(user.id)
    access_token = _create_token(user_id, "access", timedelta(hours=24))
    refresh_token = _create_token(user_id, "refresh", timedelta(days=30))

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
