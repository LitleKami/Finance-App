from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_merchant
from app.ledger import get_balance
from app.security import hash_secret

router = APIRouter(prefix="/merchants", tags=["Merchants"])


@router.post("/register", response_model=schemas.MerchantOut)
def register(payload: schemas.MerchantCreate, db: Session = Depends(get_db)):
    if db.query(models.Merchant).filter(models.Merchant.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    merchant = models.Merchant(
        business_name=payload.business_name,
        email=payload.email,
        password_hash=hash_secret(payload.password),
        category=payload.category,
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.get("", response_model=list[schemas.MerchantOut])
def list_merchants(category: Optional[models.Category] = None,
                    approved_only: bool = True,
                    db: Session = Depends(get_db)):
    q = db.query(models.Merchant)
    if category:
        q = q.filter(models.Merchant.category == category)
    if approved_only:
        q = q.filter(models.Merchant.status == models.MerchantStatus.approved,
                      models.Merchant.is_suspended == False)  # noqa: E712
    return q.all()


@router.get("/{merchant_id}", response_model=schemas.MerchantOut)
def get_merchant(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).get(merchant_id)
    if not merchant:
        raise HTTPException(404, "Merchant not found")
    return merchant


@router.get("/{merchant_id}/balance")
def merchant_balance(merchant_id: str, db: Session = Depends(get_db),
                      current_merchant: models.Merchant = Depends(get_current_merchant)):
    if merchant_id != current_merchant.id:
        raise HTTPException(403, "Not authorized to view this merchant's balance")
    return {
        "merchant_id": merchant_id,
        "settled_balance": get_balance(db, "merchant", merchant_id),
    }
