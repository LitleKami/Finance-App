# Only relevant if you still have a /admin/seed endpoint in admin.py from
# earlier. If you deleted it as instructed, ignore this file — just use the
# manual click-through in /docs instead, updated for the new schema.
#
# If you kept it, replace your import line:
#   from app.routers.users import hash_pin
# with:
#   from app.security import hash_secret
#
# ...and replace the whole function body with this version:

@router.post("/seed")
def seed_demo_data(db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == "ada@example.com").first()
    if existing:
        return {"status": "already seeded", "user_id": existing.id}

    user = models.User(full_name="Ada Eze", email="ada@example.com",
                        kyc_status=models.KYCStatus.verified,
                        password_hash=hash_secret("password123"),
                        pin_hash=hash_secret("1234"))
    db.add(user)
    db.flush()

    wallet = models.Wallet(user_id=user.id, category=models.Category.groceries,
                            target_amount=20000, frequency="weekly")
    db.add(wallet)
    db.flush()

    post_entry(db, "wallet", wallet.id, EntryType.credit, 5000, memo="seed funding")
    post_entry(db, "platform_suspense", "SUSPENSE", EntryType.debit, 5000, memo="seed funding source")

    m1 = models.Merchant(business_name="GreenBasket Stores",
                          email="greenbasket@example.com",
                          password_hash=hash_secret("password123"),
                          category=models.Category.groceries,
                          status=models.MerchantStatus.approved)
    m2 = models.Merchant(business_name="FastCab Rides",
                          email="fastcab@example.com",
                          password_hash=hash_secret("password123"),
                          category=models.Category.transport,
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
        "user_login": {"email": "ada@example.com", "password": "password123"},
        "merchant_groceries_login": {"email": "greenbasket@example.com", "password": "password123"},
        "merchant_transport_login": {"email": "fastcab@example.com", "password": "password123"},
        "user_id": user.id,
        "wallet_id": wallet.id,
    }
