from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.ledger import get_balance

router = APIRouter(prefix="/merchants", tags=["Merchants"])


@router.post("/register", response_model=schemas.MerchantOut)
def register(payload: schemas.MerchantCreate, db: Session = Depends(get_db)):
    merchant = models.Merchant(
        business_name=payload.business_name,
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


@router.get("/{merchant_id}/balance")
def merchant_balance(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).get(merchant_id)
    if not merchant:
        raise HTTPException(404, "Merchant not found")
    return {
        "merchant_id": merchant_id,
        "settled_balance": get_balance(db, "merchant", merchant_id),
    }
