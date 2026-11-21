import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import User  # noqa: F401 确保全部模型注册

IS_PROD = settings.env.lower() in ("prod", "production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.core.migrate import ensure_columns
        await ensure_columns(conn)

    # 首用户引导：库中无任何用户时创建初始管理员
    async with SessionLocal() as db:
        count = (await db.execute(select(func.count(User.id)))).scalar()
        if count == 0:
            from app.models import User as U
            # 生产环境：必须由 INIT_ADMIN_PASSWORD 提供，否则随机生成并仅在启动日志打印一次
            pwd = os.getenv("INIT_ADMIN_PASSWORD", "").strip()
            if not pwd:
                if IS_PROD:
                    pwd = secrets.token_urlsafe(16)
                    print("=" * 64)
                    print("  已创建初始管理员 admin")
                    print(f"  一次性初始密码：{pwd}")
                    print("  请立即登录并修改，此密码不会再显示")
                    print("=" * 64)
                else:
                    pwd = "admin123"
            if len(pwd) < 8:
                raise RuntimeError("INIT_ADMIN_PASSWORD 长度至少 8 位")
            db.add(U(username="admin", password_hash=hash_password(pwd),
                     display_name="初始化管理员", role="core_admin"))
            await db.commit()
    yield


app = FastAPI(title="NetFiberViz", version="1.0.0", lifespan=lifespan)

# CORS：默认不启用（同源部署）。仅在显式配置来源时挂载，且不使用通配符
_origins = settings.cors_origin_list
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # 前端为纯静态 SPA，样式使用内联变量，故允许 style 'unsafe-inline'
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'",
    )
    return response


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
async def health():
    return {"ok": True}


# ---------------- 前端静态资源（含路径穿越防护） ----------------
# 兼容两种布局：
#   单仓开发： <repo>/frontend/dist
#   容器镜像： /app/static
_DIST_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "frontend" / "dist",
    Path(__file__).resolve().parents[1] / "static",
    Path("/app/static"),
]
_DIST = next((p for p in _DIST_CANDIDATES if p.is_dir()), None)
_DIST_RESOLVED = _DIST.resolve() if _DIST else None

if _DIST_RESOLVED:
    app.mount("/assets", StaticFiles(directory=_DIST_RESOLVED / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        index = _DIST_RESOLVED / "index.html"
        if path:
            try:
                target = (_DIST_RESOLVED / path).resolve()
                # 必须落在静态目录内，防止 ../ 穿越读取任意文件
                target.relative_to(_DIST_RESOLVED)
            except (ValueError, OSError):
                return FileResponse(index)
            if target.is_file():
                return FileResponse(target)
        return FileResponse(index)
