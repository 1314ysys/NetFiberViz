# NetFiberViz 1.0 —— 单镜像（后端 API + 前端静态资源）
#
# 构建：
#   podman build -t netfiberviz:1.0 .
#
# 国内网络如需替换基础镜像源：
#   podman build -t netfiberviz:1.0 \
#     --build-arg PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/<ns>/python:3.11-slim \
#     --build-arg NODE_IMAGE=registry.cn-hangzhou.aliyuncs.com/<ns>/node:20-alpine .

ARG NODE_IMAGE=node:20-alpine
ARG PYTHON_IMAGE=python:3.11-slim

# ---------- 1. 构建前端 ----------
FROM ${NODE_IMAGE} AS frontend-build
WORKDIR /fe
ENV CI=true
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---------- 2. 安装 Python 依赖 ----------
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && pip install \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "sqlalchemy[asyncio]>=2.0" \
    "aiosqlite>=0.20" \
    "pymysql>=1.1" \
    "cryptography>=42" \
    "alembic>=1.13" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "PyJWT>=2.9" \
    "passlib[argon2]>=1.7" \
    "python-multipart>=0.0.9" \
    "openpyxl>=3.1"

# ---------- 3. 运行时 ----------
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENV=prod

# 非 root 运行
RUN groupadd -r -g 10001 app && useradd -r -u 10001 -g app -s /sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=root:root backend/app ./app
COPY --from=frontend-build --chown=root:root /fe/dist ./static

# 运行期可写目录（SQLite 回退 / 临时文件）
RUN mkdir -p /app/data && chown -R app:app /app/data
ENV DATABASE_URL="sqlite+aiosqlite:////app/data/fiber.db"

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=4s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

LABEL org.opencontainers.image.title="NetFiberViz" \
      org.opencontainers.image.version="1.0" \
      org.opencontainers.image.description="机房跳纤布线可视化管理系统" \
      org.opencontainers.image.source="https://github.com/"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
