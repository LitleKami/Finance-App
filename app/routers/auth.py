import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session as DBSession

from app import models, schemas
from app.database import get_db
from app.security import verify_secret, hash_secret
from app.deps import (
    get_current_user, get_current_merchant, get_current_admin,
    USER_COOKIE, MERCHANT_COOKIE, ADMIN_COOKIE,
)
from app.models import SESSION_DURATION_DAYS

router = APIRouter(prefix="/auth", tags=["Auth"])

# secure=False so this also works over plain http on localhost during
# development. Once this is only ever served over https (which Railway
# already does), flip this to True so the cookie is never sent over an
# unencrypted connection.
COOKIE_SECURE = False


def _create_session(db: DBSession, subject_type: str, subject_id: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(models.Session(
        token=token, subject_type=subject_type, subject_id=subject_id,
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DURATION_DAYS),
    ))
    db.commit()
    return token


def _clear_session(db: DBSession, token: str, subject_type: str):
    if token:
        db.query(models.Session).filter(
            models.Session.token == token, models.Session.subject_type == subject_type
        ).delete()
        db.commit()


# ---- User auth ----
@router.post("/login", response_model=schemas.UserOut)
def user_login(payload: schemas.LoginRequest, response: Response, db: DBSession = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if user.is_suspended:
        raise HTTPException(403, "This account has been suspended")
    token = _create_session(db, "user", user.id)
    response.set_cookie(
        USER_COOKIE, token, httponly=True, samesite="lax", secure=COOKIE_SECURE,
        max_age=SESSION_DURATION_DAYS * 86400, path="/",
    )
    return user


@router.post("/logout")
def user_logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    _clear_session(db, request.cookies.get(USER_COOKIE), "user")
    response.delete_cookie(USER_COOKIE, path="/")
    return {"status": "logged out"}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ---- Merchant auth ----
@router.post("/merchant-login", response_model=schemas.MerchantOut)
def merchant_login(payload: schemas.LoginRequest, response: Response, db: DBSession = Depends(get_db)):
    merchant = db.query(models.Merchant).filter(models.Merchant.email == payload.email).first()
    if not merchant or not verify_secret(payload.password, merchant.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if merchant.is_suspended:
        raise HTTPException(403, "This merchant account has been suspended")
    token = _create_session(db, "merchant", merchant.id)
    response.set_cookie(
        MERCHANT_COOKIE, token, httponly=True, samesite="lax", secure=COOKIE_SECURE,
        max_age=SESSION_DURATION_DAYS * 86400, path="/",
    )
    return merchant


@router.post("/merchant-logout")
def merchant_logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    _clear_session(db, request.cookies.get(MERCHANT_COOKIE), "merchant")
    response.delete_cookie(MERCHANT_COOKIE, path="/")
    return {"status": "logged out"}


@router.get("/merchant-me", response_model=schemas.MerchantOut)
def merchant_me(current_merchant: models.Merchant = Depends(get_current_merchant)):
    return current_merchant


# ---- Admin auth ----
@router.get("/admin-exists")
def admin_exists(db: DBSession = Depends(get_db)):
    """Lets the admin page decide whether to show 'set up' or 'sign in'."""
    return {"exists": db.query(models.Admin).count() > 0}


@router.post("/admin-bootstrap", response_model=schemas.AdminOut)
def admin_bootstrap(payload: schemas.AdminBootstrap, db: DBSession = Depends(get_db)):
    """
    Creates the first (and only, via this route) admin account. Refuses to
    run a second time once any admin exists — there's deliberately no
    general admin-registration endpoint, since anyone finding one would be
    able to grant themselves full control of the platform.
    """
    if db.query(models.Admin).count() > 0:
        raise HTTPException(403, "An admin account already exists — bootstrap can only run once")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    admin = models.Admin(email=payload.email, password_hash=hash_secret(payload.password))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.post("/admin-login", response_model=schemas.AdminOut)
def admin_login(payload: schemas.LoginRequest, response: Response, db: DBSession = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.email == payload.email).first()
    if not admin or not verify_secret(payload.password, admin.password_hash):
        raise HTTPException(401, "Invalid email or password")
    token = _create_session(db, "admin", admin.id)
    response.set_cookie(
        ADMIN_COOKIE, token, httponly=True, samesite="lax", secure=COOKIE_SECURE,
        max_age=SESSION_DURATION_DAYS * 86400, path="/",
    )
    return admin


@router.post("/admin-logout")
def admin_logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    _clear_session(db, request.cookies.get(ADMIN_COOKIE), "admin")
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"status": "logged out"}


@router.get("/admin-me", response_model=schemas.AdminOut)
def admin_me(current_admin: models.Admin = Depends(get_current_admin)):
    return current_admin
