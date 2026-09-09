from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
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


def _get_owned_wallet(db: Session, wallet_id: str, user: models.User) -> models.Wallet:
    """404 (not 403) on someone else's wallet — don't confirm it exists to a non-owner."""
    wallet = db.query(models.Wallet).get(wallet_id)
    if not wallet or wallet.user_id != user.id:
        raise HTTPException(404, "Wallet not found")
    return wallet


@router.post("", response_model=schemas.WalletOut)
def create_wallet(payload: schemas.WalletCreate, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    if current_user.kyc_status != models.KYCStatus.verified:
        raise HTTPException(403, "User must complete KYC before creating a wallet")

    wallet = models.Wallet(
        user_id=current_user.id,
        category=payload.category,
        target_amount=payload.target_amount,
        frequency=payload.frequency,
        target_date=payload.target_date,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return _to_out(db, wallet)


@router.get("/mine", response_model=list[schemas.WalletOut])
def list_my_wallets(db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    wallets = db.query(models.Wallet).filter(models.Wallet.user_id == current_user.id).all()
    return [_to_out(db, w) for w in wallets]


@router.get("/{wallet_id}", response_model=schemas.WalletOut)
def get_wallet(wallet_id: str, db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    wallet = _get_owned_wallet(db, wallet_id, current_user)
    return _to_out(db, wallet)


@router.post("/{wallet_id}/fund", response_model=schemas.WalletOut)
def fund_wallet(wallet_id: str, payload: schemas.FundWallet, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    wallet = _get_owned_wallet(db, wallet_id, current_user)
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    post_entry(db, "wallet", wallet_id, EntryType.credit, payload.amount,
               memo=payload.source_memo)
    post_entry(db, "platform_suspense", "SUSPENSE", EntryType.debit, payload.amount,
               memo=f"funding source for wallet {wallet_id}")
    db.commit()
    return _to_out(db, wallet)
