"""
Run once after starting the server (or standalone) to populate demo data:
    python seed.py

Creates:
  - Ada (verified user, PIN 1234) with a groceries wallet, funded 5000 SIM
  - GreenBasket Stores (approved groceries merchant)
  - FastCab Rides (approved transport merchant) — used to demo a purpose
    mismatch rejection against Ada's groceries wallet
  - One completed settled payment from Ada to GreenBasket
"""
import hashlib
import requests

BASE = "http://127.0.0.1:8000"


def main():
    # 1. Register + verify user
    u = requests.post(f"{BASE}/users/register", json={
        "full_name": "Ada Eze", "email": "ada@example.com"
    }).json()
    user_id = u["id"]
    requests.post(f"{BASE}/users/{user_id}/kyc/verify?approve=true")
    requests.post(f"{BASE}/users/{user_id}/pin", json={"pin": "1234"})

    # 2. Create + fund a groceries wallet
    w = requests.post(f"{BASE}/wallets", json={
        "user_id": user_id, "category": "groceries",
        "target_amount": 20000, "frequency": "weekly"
    }).json()
    wallet_id = w["id"]
    requests.post(f"{BASE}/wallets/{wallet_id}/fund", json={"amount": 5000})

    # 3. Register + approve two merchants (one matching, one not)
    m1 = requests.post(f"{BASE}/merchants/register", json={
        "business_name": "GreenBasket Stores", "category": "groceries"
    }).json()
    requests.post(f"{BASE}/admin/merchants/{m1['id']}/verify?approve=true")

    m2 = requests.post(f"{BASE}/merchants/register", json={
        "business_name": "FastCab Rides", "category": "transport"
    }).json()
    requests.post(f"{BASE}/admin/merchants/{m2['id']}/verify?approve=true")

    # 4. Run a successful payment (groceries wallet -> groceries merchant)
    txn = requests.post(f"{BASE}/payments/initiate", json={
        "wallet_id": wallet_id, "merchant_id": m1["id"], "amount": 1500
    }).json()
    requests.post(f"{BASE}/payments/{txn['id']}/confirm", json={"pin": "1234"})

    print("Seed complete.")
    print(f"  user_id     = {user_id}")
    print(f"  wallet_id   = {wallet_id}  (groceries, funded 5000, 1500 spent)")
    print(f"  merchant_ok = {m1['id']}  (GreenBasket, groceries)")
    print(f"  merchant_mismatch = {m2['id']}  (FastCab, transport)")
    print("Try in /docs: POST /payments/initiate with wallet_id above and "
          f"merchant_id={m2['id']} to see the purpose-mismatch rejection.")


if __name__ == "__main__":
    main()
