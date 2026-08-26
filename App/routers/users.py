import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/users", tags=["Users"])


def hash_pin(pin: str) -> str:
    # Demo-only hashing. Real product: use a proper KDF (bcrypt/argon2) and
    # never store or log the raw PIN, even transiently.
    return hashlib.sha256(pin.encode()).hexdigest()


@router.post("/register", response_model=schemas.UserOut)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    user = models.User(full_name=payload.full_name, email=payload.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/kyc/verify", response_model=schemas.UserOut)
def simulate_kyc(user_id: str, approve: bool = True, db: Session = Depends(get_db)):
    """
    Simulated KYC step. In the real product this calls an identity
    verification provider; here it's a manual toggle so the demo can show
    both the happy path and the rejection loop from the flow chart.
    """
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
    user.pin_hash = hash_pin(payload.pin)
    db.commit()
    return {"status": "pin set"}


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user
