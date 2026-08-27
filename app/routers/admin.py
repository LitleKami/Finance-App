from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.ledger import system_wide_reconciliation, post_entry, get_balance
from app.models import EntryType, TxnStatus, DisputeStatus

from app.routers.users import hash_pin

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---- Merchant approval ----
@router.post("/merchants/{merchant_id}/verify", response_model=schemas.MerchantOut)
def verify_merchant(merchant_id: str, approve: bool = True, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).get(merchant_id)
    if not merchant:
        raise HTTPException(404, "Merchant not found")
    merchant.status = models.MerchantStatus.approved if approve else models.MerchantStatus.rejected
    db.commit()
    db.refresh(merchant)
    return merchant


@router.post("/merchants/{merchant_id}/suspend", response_model=schemas.MerchantOut)
def suspend_merchant(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(models.Merchant).get(merchant_id)
    if not merchant:
        raise HTTPException(404, "Merchant not found")
    merchant.is_suspended = True
    db.commit()
    db.refresh(merchant)
    return merchant


# ---- User management ----
@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@router.post("/users/{user_id}/suspend", response_model=schemas.UserOut)
def suspend_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.is_suspended = True
    db.commit()
    db.refresh(user)
    return user


# ---- Transaction monitoring ----
@router.get("/transactions", response_model=list[schemas.TransactionOut])
def list_transactions(status: TxnStatus = None, db: Session = Depends(get_db)):
    q = db.query(models.Transaction)
    if status:
        q = q.filter(models.Transaction.status == status)
    return q.order_by(models.Transaction.created_at.desc()).all()


# ---- Financial monitoring / reconciliation ----
@router.get("/reconcile")
def reconcile(db: Session = Depends(get_db)):
    """
    The single most important admin endpoint in a ledger-based system:
    proves total system-wide debits equal total credits. If this ever
    reports reconciled=false, money-movement code has a bug — stop and
    fix it before anything else.
    """
    return system_wide_reconciliation(db)


# ---- Disputes ----
@router.get("/disputes", response_model=list[schemas.DisputeOut])
def list_disputes(db: Session = Depends(get_db)):
    return db.query(models.Dispute).all()


@router.post("/disputes", response_model=schemas.DisputeOut)
def create_dispute(payload: schemas.DisputeCreate, db: Session = Depends(get_db)):
    txn = db.query(models.Transaction).get(payload.txn_id)
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.status != TxnStatus.settled:
        raise HTTPException(400, "Only settled transactions can be disputed")
    dispute = models.Dispute(
        txn_id=payload.txn_id, raised_by=payload.raised_by, reason=payload.reason
    )
    txn.status = TxnStatus.disputed
    db.add(dispute)
    db.commit()
    db.refresh(dispute)
    return dispute


@router.post("/disputes/{dispute_id}/resolve", response_model=schemas.DisputeOut)
def resolve_dispute(dispute_id: str, payload: schemas.DisputeResolve, db: Session = Depends(get_db)):
    """
    Resolving a dispute in the user's favor after settlement means clawing
    money back from the merchant — this is exactly the settlement/dispute
    timing gap flagged in the architecture red-team. Modeled here as a
    reversing ledger entry, since the original entries are never edited or
    deleted (immutable log).
    """
    dispute = db.query(models.Dispute).get(dispute_id)
    if not dispute:
        raise HTTPException(404, "Dispute not found")
    txn = db.query(models.Transaction).get(dispute.txn_id)

    if payload.uphold:
        post_entry(db, "merchant", txn.merchant_id, EntryType.debit, txn.amount,
                   txn_id=txn.id, memo=f"dispute clawback for dispute {dispute.id}")
        post_entry(db, "wallet", txn.wallet_id, EntryType.credit, txn.amount,
                   txn_id=txn.id, memo=f"dispute refund for dispute {dispute.id}")
        dispute.status = DisputeStatus.resolved_upheld
        txn.status = TxnStatus.failed_reversed
    else:
        dispute.status = DisputeStatus.resolved_rejected
        txn.status = TxnStatus.settled

    dispute.resolution_note = payload.resolution_note
    db.commit()
    db.refresh(dispute)
    return dispute


@router.post("/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == "ada@example.com").first()
    if existing:
        return {"status": "already seeded", "user_id": existing.id}

    user = models.User(full_name="Ada Eze", email="ada@example.com",
                        kyc_status=models.KYCStatus.verified,
                        pin_hash=hash_pin("1234"))
    db.add(user)
    db.flush()

    wallet = models.Wallet(user_id=user.id, category=models.Category.groceries,
                            target_amount=20000, frequency="weekly")
    db.add(wallet)
    db.flush()

    post_entry(db, "wallet", wallet.id, EntryType.credit, 5000, memo="seed funding")
    post_entry(db, "platform_suspense", "SUSPENSE", EntryType.debit, 5000, memo="seed funding source")

    m1 = models.Merchant(business_name="GreenBasket Stores", category=models.Category.groceries,
                          status=models.MerchantStatus.approved)
    m2 = models.Merchant(business_name="FastCab Rides", category=models.Category.transport,
                          status=models.MerchantStatus.approved)
    db.add(m1)
    db.add(m2)
    db.flush()

    txn = models.Transaction(wallet_id=wallet.id, merchant_id=m1.id, amount=1500,
                              status=models.TxnStatus.settled)
    db.add(txn)
    db.flush()

    post_entry(db, "wallet", wallet.id, EntryType.debit, 1500, txn_id=txn.id, memo="seed payment")
    post_entry(db, "merchant", m1.id, EntryType.credit, 1500, txn_id=txn.id, memo="seed settlement")

    db.commit()
    return {
        "status": "seeded",
        "user_id": user.id,
        "wallet_id": wallet.id,
        "merchant_groceries": m1.id,
        "merchant_transport": m2.id,
    }
