from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, get_current_merchant
from app.ledger import get_balance, post_entry
from app.models import EntryType, TxnStatus, HOLD_DURATION_MINUTES
from app.security import verify_secret

router = APIRouter(prefix="/payments", tags=["Payments"])


def _active_holds_total(db: Session, wallet_id: str) -> float:
    active = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.wallet_id == wallet_id,
            models.Transaction.status.in_([
                TxnStatus.balance_reserved, TxnStatus.auth_confirmed
            ]),
        )
        .all()
    )
    return sum(t.amount for t in active)


def _expire_stale_holds(db: Session, wallet_id: str):
    stale = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.wallet_id == wallet_id,
            models.Transaction.status == TxnStatus.balance_reserved,
            models.Transaction.hold_expires_at < datetime.utcnow(),
        )
        .all()
    )
    for t in stale:
        t.status = TxnStatus.failed_pending
        t.updated_at = datetime.utcnow()
    if stale:
        db.commit()


@router.post("/initiate", response_model=schemas.TransactionOut)
def initiate_payment(payload: schemas.PaymentInitiate, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    wallet = db.query(models.Wallet).get(payload.wallet_id)
    if not wallet or wallet.user_id != current_user.id:
        raise HTTPException(404, "Wallet not found")
    merchant = db.query(models.Merchant).get(payload.merchant_id)
    if not merchant:
        raise HTTPException(404, "Merchant not found")
    if merchant.status != models.MerchantStatus.approved or merchant.is_suspended:
        raise HTTPException(403, "Merchant is not approved to accept payments")

    _expire_stale_holds(db, wallet.id)

    if merchant.category != wallet.category:
        txn = models.Transaction(
            wallet_id=wallet.id, merchant_id=merchant.id, amount=payload.amount,
            status=TxnStatus.rejected_purpose_mismatch,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        raise HTTPException(
            400,
            f"Purpose mismatch: wallet is for '{wallet.category.value}', "
            f"merchant is '{merchant.category.value}'. Transaction {txn.id} logged as rejected.",
        )

    available = get_balance(db, "wallet", wallet.id) - _active_holds_total(db, wallet.id)
    if payload.amount > available:
        txn = models.Transaction(
            wallet_id=wallet.id, merchant_id=merchant.id, amount=payload.amount,
            status=TxnStatus.rejected_insufficient_funds,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        raise HTTPException(
            400,
            f"Insufficient funds: available {available}, requested {payload.amount}. "
            f"Transaction {txn.id} logged as rejected.",
        )

    txn = models.Transaction(
        wallet_id=wallet.id,
        merchant_id=merchant.id,
        amount=payload.amount,
        status=TxnStatus.balance_reserved,
        hold_expires_at=datetime.utcnow() + timedelta(minutes=HOLD_DURATION_MINUTES),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/{txn_id}/confirm", response_model=schemas.TransactionOut)
def confirm_payment(txn_id: str, payload: schemas.PaymentConfirm, db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    txn = db.query(models.Transaction).get(txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")

    wallet = db.query(models.Wallet).get(txn.wallet_id)
    if not wallet or wallet.user_id != current_user.id:
        # Same 404 as "doesn't exist" — don't reveal that a txn ID belongs to someone else
        raise HTTPException(404, "Transaction not found")

    _expire_stale_holds(db, txn.wallet_id)
    db.refresh(txn)

    if txn.status != TxnStatus.balance_reserved:
        raise HTTPException(
            409, f"Transaction is '{txn.status.value}', not confirmable "
                 f"(hold may have expired — see /payments/{txn.id})"
        )

    if not verify_secret(payload.pin, current_user.pin_hash):
        raise HTTPException(401, "PIN verification failed")

    txn.status = TxnStatus.auth_confirmed
    txn.updated_at = datetime.utcnow()
    db.commit()

    post_entry(db, "wallet", txn.wallet_id, EntryType.debit, txn.amount,
               txn_id=txn.id, memo=f"payment to merchant {txn.merchant_id}")
    post_entry(db, "merchant", txn.merchant_id, EntryType.credit, txn.amount,
               txn_id=txn.id, memo=f"settlement from wallet {txn.wallet_id}")

    txn.status = TxnStatus.settled
    txn.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/{txn_id}/simulate_failure", response_model=schemas.TransactionOut)
def simulate_failure(txn_id: str, reversed: bool = False, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    txn = db.query(models.Transaction).get(txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    wallet = db.query(models.Wallet).get(txn.wallet_id)
    if not wallet or wallet.user_id != current_user.id:
        raise HTTPException(404, "Transaction not found")
    if txn.status not in (TxnStatus.balance_reserved, TxnStatus.auth_confirmed):
        raise HTTPException(409, f"Cannot fail a transaction in status '{txn.status.value}'")
    txn.status = TxnStatus.failed_reversed if reversed else TxnStatus.failed_pending
    txn.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(txn)
    return txn


@router.get("/{txn_id}", response_model=schemas.TransactionOut)
def get_transaction(txn_id: str, db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    txn = db.query(models.Transaction).get(txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    wallet = db.query(models.Wallet).get(txn.wallet_id)
    if not wallet or wallet.user_id != current_user.id:
        raise HTTPException(404, "Transaction not found")
    return txn


@router.get("/wallet/{wallet_id}", response_model=list[schemas.TransactionOut])
def wallet_transactions(wallet_id: str, db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    wallet = db.query(models.Wallet).get(wallet_id)
    if not wallet or wallet.user_id != current_user.id:
        raise HTTPException(404, "Wallet not found")
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.wallet_id == wallet_id)
        .order_by(models.Transaction.created_at.desc())
        .all()
    )


@router.get("/merchant/{merchant_id}", response_model=list[schemas.TransactionOut])
def merchant_transactions(merchant_id: str, db: Session = Depends(get_db),
                           current_merchant: models.Merchant = Depends(get_current_merchant)):
    """Powers the merchant dashboard's activity list — merchants can only see their own."""
    if merchant_id != current_merchant.id:
        raise HTTPException(403, "Not authorized to view this merchant's transactions")
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.merchant_id == merchant_id)
        .order_by(models.Transaction.created_at.desc())
        .all()
    )
