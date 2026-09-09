"""
Shared secret hashing — used for both login passwords and payment PINs.
Bcrypt handles salting internally, so equal secrets never produce the same
hash twice and there's no separate salt column to manage.
"""
import bcrypt


def hash_secret(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_secret(raw: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        # Malformed/legacy hash (e.g. old sha256 PINs from before this change)
        return False
