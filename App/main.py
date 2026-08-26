from fastapi import FastAPI

from app.database import Base, engine
from app.routers import users, merchants, wallets, payments, admin, support

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Purpose Wallet — MVP Demo (Simulated Currency)",
    description=(
        "Simulated-currency demo of the purpose-locked budgeting platform. "
        "No real money, no external processor, no licensing dependency — "
        "same domain model (ledger, purpose-matching, payment state machine, "
        "settlement, disputes) the licensed product will run on. "
        "Use this page (Swagger UI) as the walkthrough: try the endpoints "
        "top to bottom in the order shown in each tag group."
    ),
    version="0.1.0-mvp",
)

app.include_router(users.router)
app.include_router(merchants.router)
app.include_router(wallets.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(support.router)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Purpose Wallet MVP is running.",
        "docs": "/docs",
        "note": "All currency here is simulated (SIM). No real funds, no KYC provider, no payment rail.",
    }
