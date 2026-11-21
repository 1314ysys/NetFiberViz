# NetFiberViz

机房跳纤布线可视化管理系统 —— 面向运营商机房的物理连接台账、可视化组态与 LLDP 自动布线平台。

[![Version](https://img.shields.io/badge/version-1.0-blue)]()
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688)]()
[![Frontend](https://img.shields.io/badge/frontend-Vue3-42b883)]()
[![Database](https://img.shields.io/badge/database-MySQL%208%20%7C%20SQLite-4479A1)]()

---

## 功能

- **三级下钻画布**：机房 → 机柜/配线柜 → 设备/单元柜 → 端口
- **机柜视图**：设备按 U 位排列，支持多 U 设备、拖拽自动避让、端口状态色带
- **ODF 组态**：盘为最小单元（12 孔水平），多选组合成单元柜并自动对齐，可解散
- **端口状态可视化**：空闲/在用/预留/故障四态分布，端口故障强提示至机房画布
- **设备面板设计器**：自绘设备外形与端口布局，也可从 31 个内置机型模板选择
- **布线**：跳纤、盘间连接（熔接/法兰）、纤芯熔接（批量映射规则）
- **LLDP 自动布线**：邻居表导入 → 匹配预览 → 一键生成
- **全局搜索**：`Ctrl+K` 跨机房/机柜/设备/端口/连接定位
- **权限**：核心机房管理员（全量）/ 前端机房管理员（仅授权机房及其子机房）
- **审计**：全部写操作留痕（before/after + 操作人），可导出

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy 2.0(async) · PyJWT · argon2 |
| 数据库 | MySQL 8（生产） / SQLite（开发） |
| 前端 | Vue 3 · TypeScript · Vite · Pinia · Naive UI · 自研 SVG 画布 |
| 部署 | Podman/Docker 单镜像（API + 静态资源） |

## 快速开始

### 获取镜像

**方式 A：下载 Release 中的离线镜像（推荐，无需构建）**

从 [Releases v1.0](https://github.com/1314ysys/NetFiberViz/releases/tag/v1.0) 下载 `netfiberviz-1.0.tar.gz`（78 MB），然后：

```bash
gunzip -c netfiberviz-1.0.tar.gz | podman load
```

**方式 B：本地构建**

```bash
podman build -t netfiberviz:1.0 .

# 国内网络（npm / pip 走镜像加速）
podman build -t netfiberviz:1.0 \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple .
```

> 基础镜像也可替换：`--build-arg PYTHON_IMAGE=... --build-arg NODE_IMAGE=...`

### 运行

```bash
podman run -d --name netfiberviz -p 8000:8000 \
  -e ENV=prod \
  -e JWT_SECRET="$(openssl rand -base64 48)" \
  -e INIT_ADMIN_PASSWORD='YourStrongPassw0rd' \
  -v netfiberviz-data:/app/data \
  netfiberviz:1.0

# 访问 http://localhost:8000
```

### 方式二：源码运行
```bash
# 后端
cd backend
pip install fastapi 'uvicorn[standard]' 'sqlalchemy[asyncio]' aiosqlite pymysql \
            pydantic-settings PyJWT 'passlib[argon2]' python-multipart openpyxl
python -m uvicorn app.main:app --port 8000

# 前端（开发）
cd frontend && pnpm install && pnpm dev
```

默认账号 `admin`。生产环境初始密码由 `INIT_ADMIN_PASSWORD` 指定，未指定时随机生成并在启动日志打印一次。

### 演示数据

```bash
cd backend && python scripts/seed_demo.py
```

生成：2 机房 / 2 机柜 / 3 设备 / 1 ODF 柜（3 单元×2 盘=72 孔位）/ 4 跳纤 / 48+24 芯光缆。

## 配置

全部通过环境变量，见 [.env.example](.env.example)。生产必设：

| 变量 | 说明 |
|---|---|
| `ENV` | `prod` 时启用密钥强度与 CORS 校验 |
| `JWT_SECRET` | ≥32 位随机串，缺失或过弱时**启动失败** |
| `INIT_ADMIN_PASSWORD` | 初始管理员密码，≥8 位 |
| `DATABASE_URL` | MySQL 连接串；留空回退 SQLite |

## 安全

详见 [安全审计报告](docs/security-audit-1.0.md)。要点：

- JWT 强制 HS256 + 校验 exp/sub/iss，防算法混淆与 `alg=none`
- 登录限流（5 次/5 分钟锁定）
- 密码 argon2 哈希，最小长度 8
- 静态路由防路径穿越，CSP/X-Frame-Options 等安全头
- 容器非 root 运行（uid 10001）

## 测试

```bash
cd backend && python -m pytest tests -q --asyncio-mode=auto
```

覆盖：资源/ODF/连接/链路、权限穿透（43 项越权断言）、U 位冲突、批量熔接。

## 目录

```
backend/app/         FastAPI 应用（api / models / services / core）
frontend/src/        Vue 3 应用（views / components / stores / utils）
deploy/              docker-compose 与 nginx 配置
docs/                设计文档、安全审计报告
Dockerfile           单镜像构建（后端 + 前端静态资源）
```

## 许可

Proprietary.
