"""
Shared ledger helpers. Central rule for the whole app:

    NEVER trust a stored balance column. ALWAYS derive it by summing
    ledger entries at read time.

This is the one non-negotiable habit worth carrying from this MVP into the
real product.
"""
from sqlalchemy.orm import Session
from app.models import LedgerEntry, EntryType


def get_balance(db: Session, account_type: str, account_id: str) -> float:
    entries = (
        db.query(LedgerEntry)
        .filter(
            LedgerEntry.account_type == account_type,
            LedgerEntry.account_id == account_id,
        )
        .all()
    )
    total = 0.0
    for e in entries:
        if e.entry_type == EntryType.credit:
            total += e.amount
        else:
            total -= e.amount
    return round(total, 2)


def post_entry(db: Session, account_type: str, account_id: str,
                entry_type: EntryType, amount: float, txn_id: str = None,
                memo: str = None):
    entry = LedgerEntry(
        account_type=account_type,
        account_id=account_id,
        entry_type=entry_type,
        amount=amount,
        txn_id=txn_id,
        memo=memo,
    )
    db.add(entry)
    return entry


def system_wide_reconciliation(db: Session) -> dict:
    """
    Every entry in the ledger should net to zero across the whole system
    (every debit somewhere is a credit somewhere else). If this doesn't
    net to zero, something in the money-movement code is broken — this
    is the check an admin/ops dashboard would run continuously in
    production.
    """
    entries = db.query(LedgerEntry).all()
    total = 0.0
    for e in entries:
        total += e.amount if e.entry_type == EntryType.credit else -e.amount
    return {
        "entry_count": len(entries),
        "net_balance": round(total, 2),
        "reconciled": abs(total) < 0.005,
    }
