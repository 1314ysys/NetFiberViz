import secrets
import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

log = logging.getLogger("config")

# 明确禁止在生产使用的弱密钥
WEAK_SECRETS = {
    "change-me-in-prod", "change-me", "secret", "changeme",
    "your-secret-key", "test", "dev",
}


class Settings(BaseSettings):
    # 运行环境：dev | prod。prod 下会强制校验安全配置
    env: str = "dev"
    api_prefix: str = "/fiber/api/v1"
    auth_mode: str = "local"  # local | external
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8
    database_url: str = "sqlite+aiosqlite:///./fiber.db"
    # 逗号分隔的允许来源；为空表示不启用 CORS（同源部署，推荐）
    cors_origins: str = ""
    # 上传体积上限（字节）
    max_upload_bytes: int = 10 * 1024 * 1024

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _guard_secrets(self):
        secret = (self.jwt_secret or "").strip()
        is_prod = self.env.lower() in ("prod", "production")

        if not secret:
            if is_prod:
                raise ValueError(
                    "生产环境必须通过环境变量 JWT_SECRET 设置签名密钥"
                    "（建议 `openssl rand -base64 48` 生成）"
                )
            # 开发环境随机生成，重启后 token 失效属预期
            object.__setattr__(self, "jwt_secret", secrets.token_urlsafe(48))
            log.warning("JWT_SECRET 未设置，已为本次运行生成临时密钥（仅限开发环境）")

        if is_prod:
            if secret.lower() in WEAK_SECRETS or len(secret) < 32:
                raise ValueError(
                    "JWT_SECRET 过弱：生产环境要求长度 ≥ 32 且不得使用默认/示例值"
                )
            if self.cors_origins.strip() == "*":
                raise ValueError(
                    "生产环境禁止 CORS 使用 '*'（且需与 allow_credentials 隔离），"
                    "请显式配置具体来源域名"
                )
            if self.auth_mode == "local" and "sqlite" in self.database_url:
                log.warning("生产环境正在使用 SQLite，建议切换到 MySQL 以获得并发与备份能力")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw:
            return []
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
