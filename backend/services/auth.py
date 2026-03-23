"""JWT Authentication for Admin Panel."""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt as _bcrypt

logger = logging.getLogger("auth")

# Конфигурация
_DEFAULT_SECRET = "your-secret-key-change-in-production"
SECRET_KEY = os.getenv("JWT_SECRET", _DEFAULT_SECRET)
ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

if SECRET_KEY == _DEFAULT_SECRET:
    logger.warning("⚠️  JWT_SECRET is not set — using insecure default. Set JWT_SECRET env var in production!")
if not os.getenv("ADMIN_PASSWORD"):
    logger.warning("⚠️  ADMIN_PASSWORD is not set — using default password 'admin'. Set ADMIN_PASSWORD env var in production!")

# Password hashing (direct bcrypt, no passlib)
security = HTTPBearer()

def hash_password(password: str) -> str:
    """Хешируем пароль."""
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяем пароль."""
    return _bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

def create_access_token(admin_id: str = "admin", expires_delta: Optional[timedelta] = None) -> str:
    """Создаем JWT токен."""
    if expires_delta is None:
        expires_delta = timedelta(hours=TOKEN_EXPIRY_HOURS)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"sub": admin_id, "exp": expire}

    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        raise

def verify_token(token: str) -> str:
    """Проверяем JWT токен."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_id: str = payload.get("sub")
        if admin_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
        return admin_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Dependency для защиты роутов."""
    return verify_token(credentials.credentials)

# Учетные данные по умолчанию (для первого входа)
DEFAULT_ADMIN = {
    "username": "admin",
    "password_hash": hash_password(os.getenv("ADMIN_PASSWORD", "admin"))  # Меняй в env!
}
