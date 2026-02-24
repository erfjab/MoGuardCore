import jwt
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from src.db import Admin
from src.models.admins import AdminRole
from src.config import JWT_SECRET_KEY


class TokenData(BaseModel):
    admin_id: int
    username: str
    secret: str
    role: AdminRole
    created_at: datetime


class Auth:
    @classmethod
    def create(cls, admin: Admin) -> str:
        now = datetime.utcnow()
        data = {
            "username": admin.username,
            "role": admin.role,
            "sub": str(admin.id),
            "secret": admin.hashed_secret(),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=24)).timestamp()),
        }
        return jwt.encode(data, JWT_SECRET_KEY, algorithm="HS256")

    @classmethod
    def load(cls, token: str) -> Optional[TokenData]:
        try:
            payload: dict = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "username", "role", "secret"]},
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

        username = payload.get("username")
        role = payload.get("role")
        admin_id = payload.get("sub")
        created_at_ts = payload.get("iat")
        secret = payload.get("secret")

        if not all([username, role, admin_id, created_at_ts, secret]):
            return None

        if role not in [value for value in AdminRole]:
            return None

        try:
            created_at = datetime.fromtimestamp(created_at_ts)
        except (TypeError, ValueError):
            return None

        return TokenData(
            admin_id=int(admin_id),
            username=username,
            secret=secret,
            role=role,
            created_at=created_at,
        )
