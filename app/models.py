import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Enum, Boolean, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Categories — same list as the real product's purpose wallets
# ---------------------------------------------------------------------------
class Category(str, enum.Enum):
    transport = "transport"
    food = "food"
    rent = "rent"
    school_fees = "school_fees"
    healthcare = "healthcare"
    electricity = "electricity"
    water = "water"
    fuel = "fuel"
    groceries = "groceries"
    other = "other"


class KYCStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class MerchantStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class TxnStatus(str, enum.Enum):
    initiated = "initiated"
    purpose_matched = "purpose_matched"
    balance_reserved = "balance_reserved"
    auth_confirmed = "auth_confirmed"
    settled = "settled"
    failed_pending = "failed_pending"
    failed_reversed = "failed_reversed"
    disputed = "disputed"
    rejected_purpose_mismatch = "rejected_purpose_mismatch"
    rejected_insufficient_funds = "rejected_insufficient_funds"


class EntryType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class DisputeStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved_upheld = "resolved_upheld"       # dispute valid, txn reversed
    resolved_rejected = "resolved_rejected"   # dispute invalid, settlement stands


class TicketStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"
    closed = "closed"


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=gen_id)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    kyc_status = Column(Enum(KYCStatus), default=KYCStatus.pending)
    pin_hash = Column(String, nullable=True)
    is_suspended = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    wallets = relationship("Wallet", back_populates="owner")


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(String, primary_key=True, default=gen_id)
    business_name = Column(String, nullable=False)
    category = Column(Enum(Category), nullable=False)
    status = Column(Enum(MerchantStatus), default=MerchantStatus.pending)
    is_suspended = Column(Boolean, default=False)
    # settlement account balance is DERIVED from ledger, never trusted —
    # see get_merchant_balance() in routers/admin.py / payments.py
    created_at = Column(DateTime, default=datetime.utcnow)


class Wallet(Base):
    """A 'purpose wallet' — money locked to a single spending category."""
    __tablename__ = "wallets"
    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(Enum(Category), nullable=False)
    target_amount = Column(Float, nullable=True)
    frequency = Column(String, nullable=True)   # daily / weekly / monthly / manual
    target_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="wallets")


class LedgerEntry(Base):
    """
    Immutable double-entry ledger line. Every money movement — funding,
    payment, settlement, reversal — writes at least two of these (one debit,
    one credit) so the system-wide sum always nets to zero. Wallet and
    merchant "balances" are never stored directly; they're always computed
    by summing entries. This is the same principle the real product's
    ledger must follow — the MVP just runs it on fake currency.
    """
    __tablename__ = "ledger_entries"
    id = Column(String, primary_key=True, default=gen_id)
    account_type = Column(String, nullable=False)   # "wallet" | "merchant" | "platform_suspense"
    account_id = Column(String, nullable=False)      # wallet.id / merchant.id / "SUSPENSE"
    entry_type = Column(Enum(EntryType), nullable=False)
    amount = Column(Float, nullable=False)
    txn_id = Column(String, ForeignKey("transactions.id"), nullable=True)
    memo = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String, primary_key=True, default=gen_id)
    wallet_id = Column(String, ForeignKey("wallets.id"), nullable=False)
    merchant_id = Column(String, ForeignKey("merchants.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(TxnStatus), default=TxnStatus.initiated)
    hold_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    entries = relationship("LedgerEntry", backref="transaction",
                            foreign_keys=[LedgerEntry.txn_id])


class Dispute(Base):
    __tablename__ = "disputes"
    id = Column(String, primary_key=True, default=gen_id)
    txn_id = Column(String, ForeignKey("transactions.id"), nullable=False)
    raised_by = Column(String, nullable=False)   # "user" | "merchant"
    reason = Column(Text, nullable=False)
    status = Column(Enum(DisputeStatus), default=DisputeStatus.open)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(String, primary_key=True, default=gen_id)
    raised_by_type = Column(String, nullable=False)  # "user" | "merchant"
    raised_by_id = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.open)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


HOLD_DURATION_MINUTES = 10  # how long a balance reservation is valid before auto-expiry
