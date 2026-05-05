from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse
from app.utils.jwt_utils import create_access_token
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.post("/signup", response_model=TokenResponse)
async def signup(body: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        name=body.name,
        hashed_password=pwd_context.hash(body.password),
    )
    db.add(user)
    await db.commit()
    token = create_access_token({"sub": user.id})
    return {"access_token": token}

@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": user.id})
    return {"access_token": token}

@router.get("/me", response_model=UserResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(lambda: None),
):
    pass
