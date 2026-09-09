from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.security import hash_secret

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/register", response_model=schemas.UserOut)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_secret(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/kyc/verify", response_model=schemas.UserOut)
def simulate_kyc(user_id: str, approve: bool = True, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.kyc_status = models.KYCStatus.verified if approve else models.KYCStatus.rejected
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/pin")
def set_pin(user_id: str, payload: schemas.SetPin, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.kyc_status != models.KYCStatus.verified:
        raise HTTPException(403, "KYC must be verified before setting a PIN")
    user.pin_hash = hash_secret(payload.pin)
    db.commit()
    return {"status": "pin set"}


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user
