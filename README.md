# Purpose Wallet — MVP Demo (Simulated Currency)

No real money, no bank/BaaS partner, no licensing exposure — same domain
model (ledger, purpose-matching, payment state machine, settlement,
disputes) the real product's architecture plan calls for, running on a
local SQLite file and a fake currency. Built to show the startup team the
mechanic end-to-end, not to take a single real deposit.

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** — this is the demo. FastAPI generates
an interactive UI where you (or anyone on the team) can call every
endpoint from the browser, no separate frontend needed for an MVP walk-through.

## Load demo data

In a second terminal, with the server still running:

```bash
python3 seed.py
```

This creates a verified user with a funded groceries wallet, an approved
groceries merchant, an approved transport merchant (for demoing a
rejection), and one already-settled payment. It prints the IDs you'll need
to click through the rest of the flow in `/docs`.

## What to click through in `/docs`, to tell the story

1. **Users → POST /register**, then **POST /{id}/kyc/verify**, then
   **POST /{id}/pin** — registration + KYC + secure PIN, matching flow
   chart steps 1–3.
2. **Wallets → POST /wallets** (pick a category, a target amount, a
   frequency) → **POST /{id}/fund** — purpose wallet creation + savings
   target + funding, steps 4–8.
3. **Merchants → POST /register**, then **Admin → POST
   /merchants/{id}/verify** — merchant onboarding + approval.
4. **Payments → POST /initiate** with a wallet and a *mismatched-category*
   merchant — watch it get rejected outright (step 10's "no" branch,
   before a merchant is even properly engaged).
5. **Payments → POST /initiate** with a matching merchant, then **POST
   /{id}/confirm** with the PIN — the full purpose-match → balance-check →
   PIN confirm → settle path, steps 11–21. Try confirming with the wrong
   PIN too, to show that rejection path.
6. **Payments → POST /{id}/simulate_failure`** on a freshly-initiated (not
   yet confirmed) transaction — shows the "pending vs. reversed" branch
   that was ambiguous in the original flow chart; here it's resolved
   explicitly (see `app/routers/payments.py`, `_expire_stale_holds`).
7. **Admin → GET /reconcile** — proves the whole system's ledger nets to
   zero. This is the check that matters most once real money is involved;
   showing it working on fake money now is the point.
8. **Admin → POST /disputes**, then **POST /disputes/{id}/resolve** with
   `uphold: true` — shows funds being clawed back from a merchant
   *after* settlement, which is the specific gap the architecture
   red-team prompt flagged.
9. **Support → POST /tickets**, **POST /{id}/resolve** — the dispute/
   support ticketing flow.

## What this MVP deliberately does NOT do

- No real KYC provider — `/kyc/verify` is a manual toggle.
- No real payment rail — funding and settlement are just ledger entries.
- No production-grade PIN security — SHA-256, no rate limiting/lockout on
  wrong attempts. Flagged inline in `routers/payments.py`. Do not reuse
  this PIN handling as-is once real money is involved.
- No auth/session layer — every endpoint trusts whatever ID you pass it.
  Fine for a team demo, not fine for anything public-facing.

## Why it's structured this way

The one rule worth carrying forward into the licensed product: **every
wallet and merchant balance is derived by summing ledger entries at read
time — nothing is ever a trusted stored number.** See `app/ledger.py`.
That's the single habit from the architecture plan that matters most, and
it's cheap to build correctly from day one and expensive to retrofit later.

## Note on testing

This was written and syntax-checked but **not run against a live server**
in the environment I built it in (no outbound network to install
dependencies). Run it yourself with the steps above before showing anyone
— if anything breaks on first run, it's most likely a small FastAPI/
SQLAlchemy version-compatibility issue, not a logic error in the flow.
