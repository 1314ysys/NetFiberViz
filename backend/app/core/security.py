from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "netfiberviz"


def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(p: str, h: str) -> bool:
    try:
        return pwd_ctx.verify(p, h)
    except Exception:
        # 哈希格式异常时按验证失败处理，避免抛出 500
        return False


def create_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> str | None:
    """解码并校验 JWT。

    显式限定 HS256，防止算法混淆攻击（none / RS256→HS256）；
    强制校验 exp 与 sub，拒绝无过期时间的令牌。
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
    except pyjwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
