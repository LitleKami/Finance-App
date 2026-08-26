from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.ledger import get_balance, post_entry
from app.models import EntryType, TxnStatus, HOLD_DURATION_MINUTES
from app.routers.users import hash_pin

router = APIRouter(prefix="/payments", tags=["Payments"])


def _active_holds_total(db: Session, wallet_id: str) -> float:
    """Sum of amounts currently reserved (not yet settled/failed/reversed)."""
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
    """
    Mirrors the flow chart's vague 'pending or reversed' branch: anything
    reserved past its hold window auto-resolves to failed_pending so it
    can't lock a user's funds indefinitely. This is exactly the ambiguity
    the real architecture prompt was told to pin down — here it's pinned
    down as: holds expire, funds are released back to available balance.
    """
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
def initiate_payment(payload: schemas.PaymentInitiate, db: Session = Depends(get_db)):
    wallet = db.query(models.Wallet).get(payload.wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    merchant = db.query(models.Merchant).get(payload.merchant_id)
    if not merchant:
        raise HTTPException(404, "Merchant not found")
    if merchant.status != models.MerchantStatus.approved or merchant.is_suspended:
        raise HTTPException(403, "Merchant is not approved to accept payments")

    _expire_stale_holds(db, wallet.id)

    # --- purpose match check (flow step 10) ---
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

    # --- balance check (flow step 13) ---
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
def confirm_payment(txn_id: str, payload: schemas.PaymentConfirm, db: Session = Depends(get_db)):
    """Flow steps 14-21: PIN/OTP confirmation, processing, settlement."""
    txn = db.query(models.Transaction).get(txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")

    _expire_stale_holds(db, txn.wallet_id)
    db.refresh(txn)

    if txn.status != TxnStatus.balance_reserved:
        raise HTTPException(
            409, f"Transaction is '{txn.status.value}', not confirmable "
                 f"(hold may have expired — see /payments/{txn.id})"
        )

    wallet = db.query(models.Wallet).get(txn.wallet_id)
    user = db.query(models.User).get(wallet.user_id)

    if not user.pin_hash or hash_pin(payload.pin) != user.pin_hash:
        # NOTE: a real system must rate-limit/lockout here to stop PIN
        # brute-forcing. Omitted in the MVP for simplicity — call this out
        # explicitly if this demo goes anywhere near production.
        raise HTTPException(401, "PIN verification failed")

    txn.status = TxnStatus.auth_confirmed
    txn.updated_at = datetime.utcnow()
    db.commit()

    # --- settlement (merchant flow step 10, kept immediate for MVP; the
    # real product treats this as a separately scheduled batch) ---
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
def simulate_failure(txn_id: str, reversed: bool = False, db: Session = Depends(get_db)):
    """
    Demo-only endpoint standing in for a payment-rail failure (flow step 16).
    reversed=False -> failed_pending (funds released, no ledger entries ever posted).
    reversed=True  -> failed_reversed (same outcome here since nothing settled yet;
                       kept as a distinct status because a real processor can fail
                       AFTER debiting, requiring an explicit reversing entry).
    """
    txn = db.query(models.Transaction).get(txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.status not in (TxnStatus.balance_reserved, TxnStatus.auth_confirmed):
        raise HTTPException(409, f"Cannot fail a transaction in status '{txn.status.value}'")
    txn.status = TxnStatus.failed_reversed if reversed else TxnStatus.failed_pending
    txn.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(txn)
    return txn


@router.get("/{txn_id}", response_model=schemas.TransactionOut)
def get_transaction(txn_id: str, db: Session = Depends(get_db)):
    txn = db.query(models.Transaction).get(txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return txn


@router.get("/wallet/{wallet_id}", response_model=list[schemas.TransactionOut])
def wallet_transactions(wallet_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.wallet_id == wallet_id)
        .order_by(models.Transaction.created_at.desc())
        .all()
    )
