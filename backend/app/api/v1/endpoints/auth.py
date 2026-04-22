from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_async_session
from app.core.limiter import rate_limit
from app.core.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from app.models.user import User, UserCreate, UserRead

router = APIRouter()

_REFRESH_COOKIE = "refresh_token"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@rate_limit("5/minute")
async def register(
    request: Request,
    user_in: UserCreate,
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Register a new user account. Rate limited: 5 requests/min per IP."""
    result = await session.exec(select(User).where(User.email == user_in.email))
    if result.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login")
@rate_limit("10/minute")
async def login(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Authenticate and return a JWT access token. Rate limited: 10 requests/min per IP.

    Also sets an HttpOnly ``refresh_token`` cookie (7 days) so the frontend
    can silently renew the 60-min access token via ``POST /auth/refresh``.
    """
    result = await session.exec(select(User).where(User.email == form_data.username))
    user = result.first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    # Store refresh token in an HttpOnly cookie — inaccessible to JavaScript.
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=settings.PRODUCTION,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/api/v1/auth",
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh")
@rate_limit("20/minute")
async def refresh_access_token(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    refresh_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
):
    """Issue a new 60-min access token from a valid 7-day refresh token cookie.

    Rate limited: 20 requests/min per IP.
    The refresh token must be present in the HttpOnly cookie set by ``/login``.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided.",
        )

    user_id = verify_token(refresh_token, token_type="refresh")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token. Please log in again.",
        )

    result = await session.exec(select(User).where(User.id == user_id))
    user = result.first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive.",
        )

    new_access_token = create_access_token(subject=str(user.id))
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    """Clear the refresh token cookie to fully log the user out server-side."""
    response.delete_cookie(key=_REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return the currently authenticated user's profile."""
    return current_user
