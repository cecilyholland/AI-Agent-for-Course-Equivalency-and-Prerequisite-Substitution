# app/auth.py
# Password hashing helpers for reviewer authentication.
# Uses SHA-256 + random salt (built-in hashlib/os)
# Stored format: "<hex_salt>:<hex_hash>"
# Example:       "a3f8c2d1e4b59f2a:9f2a4c8e1d3b7c6e..."
#
# Usage in main.py:
#   from app.auth import hash_password, verify_password
#
# When creating a reviewer:
#   password_hash=hash_password(body.password)
#
# When logging in:
#   if not verify_password(body.password, r.password_hash):
#       raise HTTPException(status_code=401, detail="Invalid credentials")

from __future__ import annotations
import hashlib
import os

# hash_password and verify_password are designed to be simple and self-contained.
# returning a string that combines salt and hash allows us to store everything in one DB field.
# If password is empty or too short, hash_password raises ValueError to prevent weak passwords.
def hash_password(plain_password: str) -> str:
    if not plain_password or len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
    return f"{salt}:{hashed}"


# Verify_password takes the plain password and the stored hash, splits the salt and hash, and compares them.
# Returns True if they match, False otherwise. 
# It never raises exceptions
def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        salt, hashed = stored_hash.split(":")
        return hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest() == hashed
    except Exception:
        return False