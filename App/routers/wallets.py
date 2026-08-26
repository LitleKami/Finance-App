from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.ledger import get_balance, post_entry
from app.models import EntryType

router = APIRouter(prefix="/wallets", tags=["Wallets"])


def _to_out(db: Session, wallet: models.Wallet) -> dict:
    balance = get_balance(db, "wallet", wallet.id)
    progress = None
    if wallet.target_amount and wallet.target_amount > 0:
        progress = round(min(balance / wallet.target_amount, 1.0) * 100, 1)
    return {
        "id": wallet.id,
        "user_id": wallet.user_id,
        "category": wallet.category,
        "target_amount": wallet.target_amount,
        "frequency": wallet.frequency,
        "target_date": wallet.target_date,
        "balance": balance,
        "progress_pct": progress,
    }


@router.post("", response_model=schemas.WalletOut)
def create_wallet(payload: schemas.WalletCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).get(payload.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.kyc_status != models.KYCStatus.verified:
        raise HTTPException(403, "User must complete KYC before creating a wallet")

    wallet = models.Wallet(
        user_id=payload.user_id,
        category=payload.category,
        target_amount=payload.target_amount,
        frequency=payload.frequency,
        target_date=payload.target_date,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return _to_out(db, wallet)


@router.get("/{wallet_id}", response_model=schemas.WalletOut)
def get_wallet(wallet_id: str, db: Session = Depends(get_db)):
    wallet = db.query(models.Wallet).get(wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    return _to_out(db, wallet)


@router.get("/user/{user_id}", response_model=list[schemas.WalletOut])
def list_user_wallets(user_id: str, db: Session = Depends(get_db)):
    wallets = db.query(models.Wallet).filter(models.Wallet.user_id == user_id).all()
    return [_to_out(db, w) for w in wallets]


@router.post("/{wallet_id}/fund", response_model=schemas.WalletOut)
def fund_wallet(wallet_id: str, payload: schemas.FundWallet, db: Session = Depends(get_db)):
    """
    Simulated funding — stands in for 'approved funding method' in the real
    flow. Credits the wallet and debits a platform suspense account so the
    ledger still nets to zero (the fake money has to come from somewhere,
    even in a simulator).
    """
    wallet = db.query(models.Wallet).get(wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    post_entry(db, "wallet", wallet_id, EntryType.credit, payload.amount,
               memo=payload.source_memo)
    post_entry(db, "platform_suspense", "SUSPENSE", EntryType.debit, payload.amount,
               memo=f"funding source for wallet {wallet_id}")
    db.commit()
    return _to_out(db, wallet)
