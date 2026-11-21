# NetFiberViz 1.0 安全审计与渗透测试报告

| 项目 | 内容 |
|---|---|
| 系统 | NetFiberViz —— 机房跳纤布线可视化管理系统 |
| 版本 | 1.0 |
| 审计日期 | 2026-11-21 |
| 审计方式 | 白盒（源码可读）+ 黑盒（运行时主动探测） |
| 范围 | 后端 API、前端 SPA、容器镜像、依赖链、部署配置 |
| 授权 | 项目所有者本机授权测试 |

---

## 1. 执行摘要

本次审计覆盖 OWASP Top 10 全部类目、依赖供应链、密钥泄露、认证与授权、文件上传与静态资源服务。

**共发现 13 项问题：高危 3、中危 6、低危 3、信息 1。全部已修复并通过回归验证。**

最关键的三个问题：

1. **JWT 签名密钥存在硬编码默认值**（`change-me-in-prod`）。若部署时未覆盖，任何知道该默认值的人都可伪造管理员令牌，完全绕过认证。
2. **SPA 静态路由存在路径穿越**。`/{path:path}` 直接把请求路径拼到静态目录后返回文件，`../` 可读取容器/主机上的任意文件（含 `.env`、数据库、私钥）。
3. **JWT 组件 python-jose 存在无修复版本的已知漏洞**（PYSEC-2026-4298）。已整体迁移至 PyJWT，并显式限定算法与必需声明。

修复后主动渗透验证 **16/16 全部通过**，功能回归 **47 项测试全部通过**。

---

## 2. 测试方法与工具

| 阶段 | 手段 |
|---|---|
| 静态分析 | 正则扫描（硬编码密钥、SQL 拼接、危险 API、XSS sink）、人工代码审阅 |
| 依赖审计 | `pip-audit` 对照项目实际依赖 |
| 密钥扫描 | 全仓扫描默认口令、示例密钥、连接串 |
| 主动渗透 | 自建脚本覆盖路径穿越、CSP/安全头、认证绕过、JWT 攻击、限流、弱口令、上传上限 |
| 授权验证 | 已有 43 项权限穿透回归用例（跨机房/跨角色越权断言 403） |

---

## 3. 发现与修复明细

### NFV-01 · JWT 签名密钥硬编码默认值 — 高危

- **位置**：`backend/app/core/config.py`（原 `jwt_secret: str = "change-me-in-prod"`）
- **风险**：攻击者用默认密钥离线签发 `{"sub":"admin"}`，携带即可通过全部鉴权，等同系统接管。
- **修复**：引入 `ENV` 环境标识。生产环境（`ENV=prod`）下若密钥为空、长度 < 32 或命中弱值字典，**启动即失败**；开发环境自动生成一次性随机密钥并告警。
- **验证**：伪造/篡改令牌访问 `/rooms` 均返回 401。

### NFV-02 · SPA 静态路由路径穿越 — 高危

- **位置**：`backend/app/main.py`
- **风险**：`f = _DIST / path` 未做目录约束，`GET /../../backend/.env` 可读取任意文件。该路由**不需要认证**，风险放大。
- **修复**：`resolve()` 后用 `relative_to(_DIST)` 强制校验落在静态目录内，越界一律回退 `index.html`。
- **验证**：`../backend/app/core/config.py`、`..%2f..%2fetc%2fpasswd`、`....//....//` 等 4 种载荷均未泄露内容。

### NFV-03 · JWT 组件已知漏洞 — 高危

- **位置**：依赖 `python-jose`
- **风险**：PYSEC-2026-4298 无修复版本；该库历史上多次出现算法混淆类问题（RS256→HS256 混淆、`alg:none` 绕过）。
- **修复**：迁移至 **PyJWT 2.15**；解码时显式 `algorithms=["HS256"]`，强制 `require=["exp","sub","iss"]`，并校验 `iss=netfiberviz`。不信任令牌头部的 `alg`。
- **验证**：`alg=none` 构造令牌、篡改 payload 保留原签名，均返回 401。

### NFV-04 · CORS 通配符 + 携带凭据 — 中危

- **位置**：`main.py`（原 `allow_origins=["*"]` 且 `allow_credentials=True`）
- **风险**：任意站点可发起带凭据的跨域请求；若将来误配代理或放宽，即成 CSRF 放大器。
- **修复**：默认**不启用 CORS**（前端与 API 同源部署，nginx 代理）。仅当显式配置 `CORS_ORIGINS` 时挂载，且生产环境禁止 `*`。方法/头收敛为白名单。

### NFV-05 · 登录无限流 — 中危

- **位置**：`POST /auth/login`
- **风险**：可离线字典爆破管理员口令。
- **修复**：新增 `services/ratelimit.py`，按 `IP + 用户名` 维度统计，5 分钟内 5 次失败即锁定 5 分钟，返回 `429` 与 `Retry-After`。登录成功清零。
- **验证**：连续 6 次错误密码，第 6 次返回 429（序列 `401×5 → 429`）。

### NFV-06 · 密码强度缺失 — 中危

- **位置**：`auth.py` 的 `UserCreate` / `UserUpdate`
- **风险**：可创建 1 位密码账号，等于无口令。
- **修复**：`min_length=8`、`max_length=128`（Pydantic 层强制）。
- **验证**：提交 3 位密码返回 422。

### NFV-07 · 文件上传无体积限制 — 中危

- **位置**：`/import/excel`、`/lldp/import`
- **风险**：超大文件造成内存/CPU 耗尽（DoS）；openpyxl 解析恶意 xlsx 亦可放大资源消耗。
- **修复**：统一读取后校验 ≤ `MAX_UPLOAD_BYTES`（默认 10MB），超限返回 `413`；空文件返回 `400`。
- **验证**：11MB 上传返回 413。

### NFV-08 · 前端暴露默认凭据 — 中危

- **位置**：`LoginView.vue`
- **风险**：登录页预填 `admin/admin123` 并在页面明示，任何访问者可直接获得有效凭据。
- **修复**：移除预填值，提示文案改为"请使用管理员账号登录，登录后立即修改初始密码"。

### NFV-09 · 部署配置内置默认数据库口令 — 中危

- **位置**：`deploy/docker-compose.yml`
- **风险**：`${MYSQL_ROOT_PASSWORD:-fiberroot}` 等默认值会静默生效，形成弱口令数据库。
- **修复**：改为 `${VAR:?必须设置}` 语法，缺失即拒绝启动；补充 `JWT_SECRET`、`INIT_ADMIN_PASSWORD`、`ENV=prod`。

### NFV-10 · 迁移脚本 SQL 标识符拼接 — 低危

- **位置**：`core/migrate.py`
- **说明**：DDL 无法参数化，原实现用 f-string 拼接表名/列名。当前取值来自代码常量，**未构成立即可利用漏洞**，但属脆弱模式。
- **修复**：新增 `_ident()` 白名单（`^[A-Za-z_][A-Za-z0-9_]{0,63}$`），非法标识符直接抛错。

### NFV-11 · 缺少安全响应头 — 低危

- **修复**：统一中间件下发 `X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`、`Referrer-Policy: no-referrer`、`Permissions-Policy`、以及限定源的 `Content-Security-Policy`（`default-src 'self'`，样式因内联变量保留 `'unsafe-inline'`）。

### NFV-12 · 依赖漏洞 — 低危

| 包 | 漏洞 | 处置 |
|---|---|---|
| python-jose | PYSEC-2026-4298（无修复） | 迁移 PyJWT（见 NFV-03） |
| starlette | PYSEC-2026-248 / 249 | 升级至 1.3.1+ |
| urllib3 | PYSEC-2026-4175/4176/4177 | 升级至 2.8.0+ |
| certifi | PYSEC-2026-4320 | 升级至 2026.10.18+ |

### NFV-13 · 初始管理员口令硬编码 — 信息

- **原实现**：首次启动固定创建 `admin/admin123`。
- **修复**：生产环境优先读取 `INIT_ADMIN_PASSWORD`；未提供则**随机生成 16 位密码并在启动日志打印一次**，提示立即修改。开发环境保留 `admin123` 以便本地联调。

---

## 4. 已验证无问题的项

| 检查项 | 结论 |
|---|---|
| SQL 注入 | 全部查询经 SQLAlchemy 参数化；无字符串拼接 SQL（DDL 例外见 NFV-10，已加固） |
| 命令注入 / 反序列化 | 全仓无 `eval` / `exec` / `pickle` / `subprocess` / `yaml.load` |
| XSS | 前端无 `v-html` / `innerHTML` / `insertAdjacentHTML`；Vue 默认转义 |
| 密码存储 | argon2（passlib），带盐、抗 GPU |
| 越权（IDOR/BFLA） | 43 项回归用例覆盖：跨机房读写、跨角色提权、跨机柜连线、用户管理等，越权一律 403 |
| 审计追溯 | 全部写操作落 `change_logs`（before/after JSON + 操作人） |
| 容器安全 | 非 root（uid 10001）运行、`slim` 基础镜像、多阶段构建、内置 healthcheck |

---

## 5. 主动渗透测试结果

```
=== 1. 路径穿越（SPA 静态路由）===
[PASS] ../backend/app/core/config.py        status=200 leaked=False
[PASS] ..%2f..%2fetc%2fpasswd               status=200 leaked=False
[PASS] ../../../../etc/passwd               status=200 leaked=False
[PASS] ....//....//backend/.env             status=200 leaked=False

=== 2. 安全响应头 ===
[PASS] x-content-type-options   nosniff
[PASS] x-frame-options          SAMEORIGIN
[PASS] referrer-policy          no-referrer
[PASS] content-security-policy  default-src 'self'; ...

=== 3. 认证绕过 ===
[PASS] 未授权访问 /rooms        status=401
[PASS] 伪造 token 拒绝          status=401
[PASS] alg=none 攻击拒绝        status=401
[PASS] 篡改 payload 拒绝        status=401

=== 4. 登录限流（6 次错误密码）===
[PASS] 连续失败触发 429         codes=[401,401,401,401,401,429]

=== 5. 弱口令校验 ===
[PASS] 拒绝 3 位弱密码          status=422

=== 6. 越权抽查 ===
[PASS] 未授权列用户拒绝         status=401

=== 7. 上传体积限制 ===
[PASS] 超限上传拒绝             status=413

结果：16/16 通过
```

---

## 6. 残余风险与建议

| 项 | 说明 | 建议 |
|---|---|---|
| 限流为单进程内存 | 多实例部署时计数不共享，攻击者可分散打点 | 扩展到多副本时改用 Redis 计数器 |
| JWT 无吊销机制 | 令牌在有效期内（默认 8h）无法主动失效 | 高风险场景缩短有效期，或引入 `token_version` 字段 |
| 无多因素认证 | 仅口令认证 | 面向外网暴露时建议加 TOTP |
| 无 HTTPS 终结 | 镜像内仅 HTTP | 由外层 nginx/网关做 TLS 终结并强制 HSTS |
| 无自动化安全门禁 | 本次为人工 + 脚本审计 | 在 CI 中加入 `pip-audit`、`semgrep`、`gitleaks` 作为合并门禁 |
| 备份与恢复 | 未纳入本次范围 | 建议对 MySQL 做定期 dump 并验证可恢复性 |

---

## 7. 结论

本次审计发现的 3 项高危问题（默认 JWT 密钥、路径穿越、JWT 库漏洞）均已修复并验证，6 项中危与 4 项低危/信息项同步整改完毕。

修复后：
- 主动渗透 **16/16 通过**
- 功能回归 **47/47 通过**
- 无已知可利用的高/中危漏洞

**可以进入发布流程。** 生产部署务必：
1. 设置 `ENV=prod`
2. 提供 ≥32 位随机 `JWT_SECRET`
3. 提供强 `INIT_ADMIN_PASSWORD`
4. 外层启用 HTTPS
