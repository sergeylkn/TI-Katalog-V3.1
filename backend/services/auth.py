"""JWT Authentication for Admin Panel."""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext

logger = logging.getLogger("auth")

# Конфигурация
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def hash_password(password: str) -> str:
    """Хешируем пароль."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяем пароль."""
    return pwd_context.verify(plain_password, hashed_password)

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
