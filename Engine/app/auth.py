"""
Authentication module - Simplified version
"""

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import os
import json
import threading
import tempfile
import shutil
from app.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
ALGORITHM = "HS256"
# Access tokens: shorter-lived
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 2  # 2 hours
# Refresh tokens: longer-lived
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Revocation storage
DATA_DIR = "data"
REVOCATION_FILE = os.path.join(DATA_DIR, "revoked_refresh_tokens.json")
os.makedirs(DATA_DIR, exist_ok=True)
_REVOCATION_LOCK = threading.RLock()

def _load_revoked() -> set:
    with _REVOCATION_LOCK:
        if not os.path.exists(REVOCATION_FILE):
            return set()
        try:
            with open(REVOCATION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data or [])
        except Exception:
            return set()

def _save_revoked(s: set) -> None:
    with _REVOCATION_LOCK:
        tmp = REVOCATION_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(list(s), f, indent=2, ensure_ascii=False)
        shutil.move(tmp, REVOCATION_FILE)

def is_refresh_token_revoked(jti: str) -> bool:
    return jti in _load_revoked()

def revoke_refresh_token(jti: str) -> None:
    s = _load_revoked()
    s.add(jti)
    _save_revoked(s)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a refresh JWT with a unique jti"""
    to_encode = data.copy()
    jti = str(uuid.uuid4())
    to_encode.update({"jti": jti, "type": "refresh"})

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire})
    encoded = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded


def decode_token(token: str) -> Optional[dict]:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
