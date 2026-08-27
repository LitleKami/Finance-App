from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

from app.models import Category, KYCStatus, MerchantStatus, TxnStatus, DisputeStatus, TicketStatus


# ---- Users ----
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr


class UserOut(BaseModel):
    id: str
    full_name: str
    email: str
    kyc_status: KYCStatus
    is_suspended: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SetPin(BaseModel):
    pin: str  # 4-6 digits, demo only — never do this in production


# ---- Merchants ----
class MerchantCreate(BaseModel):
    business_name: str
    category: Category


class MerchantOut(BaseModel):
    id: str
    business_name: str
    category: Category
    status: MerchantStatus
    is_suspended: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Wallets ----
class WalletCreate(BaseModel):
    user_id: str
    category: Category
    target_amount: Optional[float] = None
    frequency: Optional[str] = None
    target_date: Optional[datetime] = None


class WalletOut(BaseModel):
    id: str
    user_id: str
    category: Category
    target_amount: Optional[float]
    frequency: Optional[str]
    target_date: Optional[datetime]
    balance: float
    progress_pct: Optional[float]

    class Config:
        from_attributes = True


class FundWallet(BaseModel):
    amount: float
    source_memo: Optional[str] = "manual deposit (simulated)"


# ---- Payments ----
class PaymentInitiate(BaseModel):
    wallet_id: str
    merchant_id: str
    amount: float


class PaymentConfirm(BaseModel):
    pin: str
    otp: Optional[str] = "000000"  # simulated OTP, any value accepted in MVP


class TransactionOut(BaseModel):
    id: str
    wallet_id: str
    merchant_id: str
    amount: float
    status: TxnStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Disputes / Support ----
class DisputeCreate(BaseModel):
    txn_id: str
    raised_by: str  # "user" | "merchant"
    reason: str


class DisputeResolve(BaseModel):
    uphold: bool
    resolution_note: str


class DisputeOut(BaseModel):
    id: str
    txn_id: str
    raised_by: str
    reason: str
    status: DisputeStatus
    resolution_note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TicketCreate(BaseModel):
    raised_by_type: str
    raised_by_id: str
    subject: str
    description: str


class TicketResolve(BaseModel):
    resolution_note: str


class TicketOut(BaseModel):
    id: str
    raised_by_type: str
    raised_by_id: str
    subject: str
    description: str
    status: TicketStatus
    resolution_note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
