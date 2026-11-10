"""Account endpoints. The session is an httpOnly cookie holding a signed token."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import client_ip, current_user
from ..models import User
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import COOKIE_NAME, RateLimiter, create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = RateLimiter(get_settings().auth_rate_limit_per_minute)
# Checked when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser")


def _throttle(request: Request) -> None:
    if not limiter.allow(client_ip(request)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a minute and try again."
        )


def _start_session(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_token(user.id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn, response: Response, db: Session = Depends(get_db), _=Depends(_throttle)
):
    user = User(
        email=body.email.lower(), name=body.name, password_hash=hash_password(body.password)
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        ) from None
    _start_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db), _=Depends(_throttle)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    _start_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Delete the account and everything it owns."""
    db.delete(user)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
