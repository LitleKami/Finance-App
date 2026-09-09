"""
FastAPI dependencies that turn a session cookie into a real, authenticated
User or Merchant. Any endpoint that takes `current_user` or
`current_merchant` as a parameter is now protected — a request with no
valid session gets a 401 before the endpoint body ever runs.
"""
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from app import models
from app.database import get_db

USER_COOKIE = "user_session"
MERCHANT_COOKIE = "merchant_session"


def _resolve_session(db: DBSession, token: str, subject_type: str):
    if not token:
        return None
    sess = (
        db.query(models.Session)
        .filter(models.Session.token == token, models.Session.subject_type == subject_type)
        .first()
    )
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        db.delete(sess)
        db.commit()
        return None
    return sess


def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> models.User:
    sess = _resolve_session(db, request.cookies.get(USER_COOKIE), "user")
    if not sess:
        raise HTTPException(401, "Not logged in")
    user = db.query(models.User).get(sess.subject_id)
    if not user or user.is_suspended:
        raise HTTPException(401, "Not logged in")
    return user


def get_current_merchant(request: Request, db: DBSession = Depends(get_db)) -> models.Merchant:
    sess = _resolve_session(db, request.cookies.get(MERCHANT_COOKIE), "merchant")
    if not sess:
        raise HTTPException(401, "Not logged in")
    merchant = db.query(models.Merchant).get(sess.subject_id)
    if not merchant or merchant.is_suspended:
        raise HTTPException(401, "Not logged in")
    return merchant
