"""JWT auth with two roles: viewer and operator.

This is the bare minimum for a working scaffold. Production additions:
- Replace the in-memory users dict with a DB.
- Add refresh tokens.
- Require MFA for operator-role tokens used on mutating endpoints.
- Rate-limit /token to slow credential stuffing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from libs.common.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"


class User(BaseModel):
    username: str
    role: Role


class TokenData(BaseModel):
    sub: str
    role: Role
    exp: datetime


# In-memory user store. Replace with DB-backed lookup.
# Default password for viewer: "viewer", for operator: "operator". Change before deploying.
_FAKE_USERS: dict[str, dict] = {
    "viewer": {"username": "viewer", "hashed": pwd_context.hash("viewer"), "role": Role.VIEWER},
    "operator": {"username": "operator", "hashed": pwd_context.hash("operator"), "role": Role.OPERATOR},
}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate(username: str, password: str) -> User | None:
    rec = _FAKE_USERS.get(username)
    if not rec or not verify_password(password, rec["hashed"]):
        return None
    return User(username=rec["username"], role=rec["role"])


def create_access_token(user: User, expires_minutes: int | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload = {"sub": user.username, "role": user.role.value, "exp": expire}
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        username = payload.get("sub")
        role = payload.get("role")
        if not username or not role:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        return User(username=username, role=Role(role))
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc


def require_role(required: Role):
    """Dependency factory enforcing a minimum role."""
    order = {Role.VIEWER: 0, Role.OPERATOR: 1}

    def _enforce(user: User = Depends(get_current_user)) -> User:
        if order[user.role] < order[required]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires {required.value}",
            )
        return user

    return _enforce
