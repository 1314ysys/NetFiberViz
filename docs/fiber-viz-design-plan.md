# 机房跳纤布线可视化管理系统 —— 规划设计文档（Agent 执行版）

> 版本 v1.0 ｜ 2026-11-18 ｜ 本文档为唯一需求与设计事实源（Single Source of Truth）。
> 执行 agent 应按 §9 里程碑顺序实施，每阶段完成后对照 §8 验收标准自检。

---

## 0. 确认的需求基线（Interview 结论）

| 项 | 结论 |
|---|---|
| 定位 | 生产级内网运维跳纤管理工具，数据准确性 > 展示效果 |
| 用户 | 机房维护人员（日常操作）+ 领导（大屏只读总览） |
| 权限 | 多用户、登录密码验证、平等权限、全操作可追溯变更记录 |
| LLDP | 仅导入邻居表文件（CSV/Excel/文本）解析匹配，**不做**设备纳管/SSH/SNMP 采集 |
| 初始化 | 手工录入优先 + Excel 模板辅助清洗导入 |
| 部署 | 内网 Linux 服务器、浏览器访问、MySQL |
| 架构约束 | 轻量高性能、无状态 API，未来作为子服务嵌入其他项目 |
| 图形 | 网络抓取拟真 SVG + 代码渲染 + 自定义图形；容器对象（机柜/ODF柜/单元柜/盘）画布自由拖拽摆放、自定义命名、层级分组 |
| 范围外 | 设备采集纳管、复杂 RBAC、外网部署、自由绘制任意图形 |

---

## 1. 技术选型

### 1.1 后端
- **Python 3.11 + FastAPI + Uvicorn**（异步，无状态，JWT 认证）
- **SQLAlchemy 2.0（async）+ Alembic** 迁移；MySQL 8.0，utf8mb4，InnoDB
- **Pydantic v2** 全量输入校验（数据准确性第一道闸）
- Excel 解析：`openpyxl`；导出：`openpyxl`（xlsx）+ CSV
- 依赖极简：不引入 Celery/Redis；长任务（LLDP 匹配、批量导入）用 FastAPI BackgroundTasks + 任务表轮询

### 1.2 前端
- **Vue 3 + TypeScript + Vite + Pinia + Vue Router**
- SVG 画布：**自研轻量画布层**（基于原生 SVG + pointer events：pan/zoom/拖拽/框选/对齐吸附网格），不依赖重量级图库（保证容器自由组态与离线内网部署）
- 拟真设备图形：内网静态资源库 `public/svg/devices/`（抓取后本地化，去除外链引用），命名规范见 §6
- UI 组件：Naive UI（轻量、内网可用）；导出前端无需任何外部 CDN

### 1.3 部署形态（为"子服务嵌入"预留）
- 单机：`docker-compose`（api + mysql + nginx 静态托管）
- 嵌入形态：后端全部路由挂载可配置前缀（`API_PREFIX=/fiber/api/v1`），认证支持对接外部 JWT（`AUTH_MODE=local|external`），前端构建为纯静态目录可被父项目 iframe/子路由挂载
- 配置全部走环境变量（pydantic-settings），**零硬编码**

---

## 2. 领域模型与层级

### 2.1 层级结构（全部可自定义命名）

```
机房 Room
 ├─ 机柜 Rack（网络设备柜）
 │   └─ 设备 Device（交换机/OLT/光切/光放/光发射机/收发器…）
 │       └─ 端口 Port（物理端口，类型：GE/XGE/FC/电口…，编号）
 ├─ ODF配线柜 OdfCabinet
 │   └─ 单元柜 OdfUnit（默认 A/B/C/D/E，可增删改名）
 │       └─ 盘 Tray（默认每盘 12 孔位、水平排列；盘内行列号 A1,A2,B1,B2…）
 │           └─ 孔位 Port（ODF 适配器孔位，状态：空闲/在用/预留/故障，颜色区分）
 └─ 画布布局 CanvasLayout（每机房一张画布，记录容器对象坐标/分组）
```

要点：
- **设备端口与 ODF 孔位统一抽象为 `Port`**（同一张表，`owner_type ∈ {device, odf_tray_slot}`），这是连接模型能统一的前提。
- ODF 盘规格可配置：默认 12 孔/盘水平；行列标号规则 `单元字母 + 行号列号`（A1、A2、B1、B2），盘上标注行列。
- 单元柜默认 A–E 仅是初始命名，**单元柜、盘的数量与命名全部可自定义**。

### 2.2 连接模型（核心，三条规则）

1. **跳纤 PatchCord（物理段）**：`port_a ↔ port_b`，一根实体线，台账/变更基本单位。
   - 合法组合：设备端口↔设备端口、设备端口↔ODF 孔位、ODF 孔位↔ODF 孔位（跨盘/跨柜跳纤）。
   - 属性：型号（FC/SC/LC 单模多模）、长度、用途备注、状态。
2. **盘间连接 Interconnect（ODF 内部物理连接）**：`odf_slot_a ↔ odf_slot_b`，类型 ∈ {熔接 splice, 法兰直通 adapter}。
   - 覆盖"盘1孔位 ↔ 盘2孔位"直连。
3. **纤芯级记录 FiberCore**（覆盖 48 芯进缆只成端 24 芯、余纤与第二根 24 芯对接熔接的场景）：
   - 光缆 `Cable`（芯数、型号、来源方向）→ `Core`（纤芯号 1..48）。
   - 每芯状态：未成端 / 已成端(关联到某 ODF 孔位) / 对接熔接(关联到另一根缆的某芯) / 备用 / 故障。
   - 即：孔位占用可回溯到具体纤芯；纤芯可"芯对芯"熔接而不占孔位或占孔位均可表达。

### 2.3 链路（逻辑端到端）
- **Link = 有序拼接的段序列**：段 = 跳纤 或 盘间连接 或 芯对接熔接。
- 生成规则：给定两端设备端口，沿连接图（Port 为节点、跳纤/盘间连接为边、纤芯熔接为虚拟边）BFS 求路径，自动串段并命名（如 ` agg-A → ODF-A2 → olt-B`）。
- LLDP 端到端邻居对 → 在连接图上校验/自动补全匹配 → 生成或校对链路。

### 2.4 变更记录（审计）
- 统一 `ChangeLog` 表：`id, user_id, ts, entity_type, entity_id, action(create/update/delete), before_json, after_json, remark`。
- 所有写操作走 service 层统一拦截器写入，前端提供按对象/按人/按时间筛选的变更历史视图 + 导出。

---

## 3. 数据库设计（MySQL 8，核心表）

```
users(id, username UNIQUE, password_hash, display_name, is_active, created_at)
rooms(id, name, code, address, canvas_json JSON)          # canvas_json=画布布局快照
racks(id, room_id, name, code, u_count, pos_x, pos_y, group_id NULL)
devices(id, rack_id, name, model, device_type ENUM(sw,olt,oadm,amp,tx,rx,media_conv,custom),
        svg_key, u_position, mgmt_ip NULL, remark)
ports(id, owner_type ENUM('device','odf_slot'), owner_id, port_no, port_type,
      status ENUM('free','used','reserved','fault'), label, remark)
odf_cabinets(id, room_id, name, code, pos_x, pos_y, group_id NULL)
odf_units(id, cabinet_id, name, seq)                      # A/B/C/…
odf_trays(id, unit_id, name, slots_per_row, rows, seq)    # 默认 slots_per_row=6? → 12孔=2行x6 或 1行x12，见§4
odf_slots(id, tray_id, row_label, col_no, port_id UNIQUE) # 每孔位绑定一个 ports 记录
patch_cords(id, port_a_id, port_b_id, cord_type, length_m, status, remark)
interconnects(id, slot_a_id, slot_b_id, kind ENUM('splice','adapter'), remark)
cables(id, room_id, name, core_count, cable_type, direction_from, remark)
cores(id, cable_id, core_no, status ENUM('unused','landed','spliced','spare','fault'),
      port_id NULL, peer_core_id NULL)
links(id, name, a_port_id, z_port_id, path_json JSON, status)
lldp_imports(id, file_name, uploaded_by, uploaded_at, parsed_json JSON, match_report_json JSON, status)
tasks(id, kind, payload_json, status, result_json, created_by)   # 后台任务表
change_logs(id, user_id, ts, entity_type, entity_id, action, before_json, after_json, remark)
canvas_layouts(id, room_id, kind ENUM('topology','screen'), data_json JSON, updated_by, updated_at)
```

约束与准确性保障：
- `patch_cords` 端口唯一性：同一 port 同时只能有 **一条** 在用跳纤端（DB 层用触发器或 service 层事务校验 + 唯一函数索引模拟）；盘间连接同理。
- 所有删除为软删除或强校验（有连接引用的端口/孔位禁止删除）。
- 金额/数量类无；全部 JSON 字段用 `JSON` 类型 + 应用层 schema 校验。

---

## 4. ODF 孔位编址规则（默认，可配置）

- 单元柜：A, B, C, D, E（可增删、可改名）。
- 盘：单元内自上而下编号 1, 2, 3…；每盘默认 12 孔，**水平 1 行 12 列**（可在盘规格中切换 2 行 × 6 列）。
- 孔位标号：`单元字母 + 行标 + 列号`。1 行 12 列时行标省略 → `A1..A12`；2 行 × 6 列时 → `A1..A6（第1行）, B1..B6（第2行）`，即用户举例的 A1 A2 B1 B2。
- 孔位状态颜色（前端约定，写入设计 tokens）：空闲=灰 `#9CA3AF`、在用=绿 `#22C55E`、预留=蓝 `#3B82F6`、故障=红 `#EF4444`。

---

## 5. API 设计（REST，前缀可配）

认证：JWT（access token 8h），`POST /auth/login`；无 RBAC，登录即可用。

核心资源（统一 CRUD + 批量 + 导出）：

```
/rooms /racks /devices /ports
/odf/cabinets /odf/units /odf/trays /odf/slots          # trays 创建时按规格自动生成 slots+ports
/patch-cords            # 创建/删除即变更台账+审计
/interconnects
/cables /cores          # 芯状态、成端、芯对芯熔接
/links                  # GET /links/trace?from_port=&to_port= 自动求路径
/lldp/import            # POST 文件上传 → 解析 → 返回匹配预览（不落库）
/lldp/apply             # POST 确认应用 → 自动建/校对跳纤+链路，产出差异报告
/lldp/imports           # 历史记录与报告
/canvas/{room_id}       # GET/PUT 画布布局 JSON（拓扑编辑视图）
/screen/{room_id}       # 大屏聚合只读接口（统计+拓扑快照）
/export/inventory       # 台账导出 xlsx：设备表/端口占用表/跳纤表/孔位表/纤芯表（多 sheet）
/export/changes         # 变更记录导出
/changelog              # 查询（过滤 entity/user/时间段）
```

关键行为：
- **LLDP 导入两段式**（解析预览 → 人工确认应用），保证生产数据准确性：匹配结果分三类——`match`（已有连接吻合）、`missing`（LLDP 有但系统无连接 → 可一键生成跳纤草稿）、`conflict`（系统有但 LLDP 无 → 标记待核实）。端口识别规则：可配置正则模板（如 `XGE0/0/1`、`Ten-GigabitEthernet1/0/1` 归一化映射到系统端口），模板可由用户维护。
- 后台任务（批量导入、大机房路径计算）走 `tasks` 表，前端轮询 `GET /tasks/{id}`。

---

## 6. SVG 图形资产方案

目录（前端静态，不入库，按 `svg_key` 引用）：

```
frontend/public/svg/devices/    # 拟真设备正面图：sw-24ge.svg, olt-16p.svg, oadm.svg, edfa.svg, ot.svg, media-conv.svg …
frontend/public/svg/ports/      # 端口小图：rj45.svg, sfp.svg, sfp-plus.svg, fc.svg, sc.svg, lc.svg, lc-duplex.svg
frontend/public/svg/odf/        # ODF 柜体/单元柜/盘/适配器孔位（代码渲染为主，SVG 为辅）
frontend/public/svg/custom/     # 用户自定义图形（上传入口，服务端校验 SVG 安全性后入库文件）
```

- 图形规范：viewBox 统一、无外链 `<image href>`（内网离线安全）、`<svg>` 根带 `id`；抓取来源图形需本地化改写（去脚本、去外链、限制体积 ≤200KB）。
- **端口映射**：设备 SVG 上预留 `data-port="port_no"` 锚点元素；无法锚定的设备用"端口栅格生成器"按型号参数（端口数/类型/排列）代码渲染——一套 Vue 组件 `<DeviceSvg :device>` 优先读锚点、否则程序化渲染端口小图。
- 自定义图形上传：白名单校验（仅 svg、无 script/on* 属性、大小限制），存 `custom/`，记录 `svg_key`。

---

## 7. 前端页面与画布设计

路由：

```
/login
/topology/:roomId        # 机房拓扑画布（编辑态）：机柜、ODF柜、单元柜、盘、设备自由拖拽/分组/命名
/inventory/*             # 台账：设备、端口、ODF 孔位、跳纤、光缆纤芯（表格+筛选+批量导入/导出）
/wiring                  # 布线工作台：选中两个端口→建跳纤/盘间连接/芯熔接；LLDP 导入向导
/links                   # 链路视图：端到端路径可视化（沿串接段高亮）+ 链路台账
/changelog               # 变更历史查询
/screen/:roomId          # 领导大屏：全屏只读，机房总览+跳纤占用统计+ODF 状态热力+异常告警（故障孔位/冲突连接）
```

画布交互规格（自研 SVG 层）：
- 视图：滚轮缩放（0.2–4x）、空格/右键拖拽平移、网格吸附（10px）、框选、Ctrl 多选。
- 容器对象（机柜/ODF柜/单元柜/盘）为可拖拽分组节点：拖动父容器带动子元素；双击改名；右键菜单（重命名/分组/删除/属性）。
- 分组：`group_id` + 画布 JSON 分组框，可框选多个对象"成组命名"。
- 布线叠加层：连接以贝塞尔/正交折线画在 overlay 层，颜色区分跳纤（橙）/盘间连接（紫）/链路高亮（青）；点击线段弹出连接详情并可删除。
- 大屏：自动轮询（30s）+ 全屏适配（vw 缩放），无交互控件。

---

## 8. 数据准确性与安全清单（验收硬标准）

1. 一端口一在用连接（DB+service 双重校验）；删除被引用对象必须先解除连接。
2. 所有写操作产生 ChangeLog，before/after 完整可回放。
3. LLDP 一律两段式（预览→确认），不静默改库。
4. 密码 bcrypt/argon2 哈希；JWT 过期；接口全部鉴权；SQL 全参数化。
5. Excel 导入逐行校验，错误行明细返回，不允许部分静默成功。
6. 导出内容与库内数据一致性抽查脚本（pytest 集成测试断言）。
7. SVG 上传安全白名单校验。

---

## 9. 里程碑（Agent 执行顺序）

| # | 阶段 | 内容 | 验收 |
|---|---|---|---|
| M1 | 工程骨架 | monorepo（backend/ frontend/ deploy/ docs/）；FastAPI+SQLAlchemy+Alembic+MySQL docker-compose 起；JWT 登录 | `docker-compose up` 后能登录 |
| M2 | 资源模型 | rooms/racks/devices/ports/odf 全 CRUD + 层级约束 + ChangeLog 拦截器 + pytest 单测 | 建机房→机柜→设备→端口→ODF 全链路成功；变更留痕 |
| M3 | 连接模型 | patch_cords/interconnects/cables/cores + 唯一性校验 + `/links/trace` 路径计算 | 跳纤+盘间连接+芯熔接场景用例通过；端到端 trace 正确 |
| M4 | SVG 资产 | 抓取/整理拟真设备 SVG ≥15 种、端口小图 ≥7 种，本地化清洗；`<DeviceSvg>` 组件 + 端口栅格生成器 | 每类设备均正确渲染端口锚点 |
| M5 | 拓扑画布 | 自研 SVG 画布（pan/zoom/拖拽/吸附/框选/成组/改名）+ 布局持久化 + 布线 overlay | 容器自由拖拽分组命名，刷新不丢 |
| M6 | 台账工作台 | 各台账页面、Excel 模板下载/导入（两段式校验）、多 sheet 导出、变更历史页 | 导入错误行返回明细；导出与库一致 |
| M7 | LLDP | 导入解析（CSV/XLSX/TXT）、端口名归一化模板、预览报告（match/missing/conflict）、确认应用生成跳纤+链路 | 用样例 LLDP 文件跑通三类结果 |
| M8 | 大屏 | /screen 总览页：统计卡+ODF 热力+故障告警+自动轮询 | 1920/4K 自适应展示 |
| M9 | 交付整备 | 部署文档、备份脚本（mysqldump cron）、种子演示数据脚本、README | 新环境 30 分钟内可部署 |

## 10. 目录结构

```
fiber-viz/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            # FastAPI 入口，API_PREFIX 可配
│  │  ├─ core/              # config, security(jwt), deps
│  │  ├─ models/            # SQLAlchemy 模型（按域分文件）
│  │  ├─ schemas/           # Pydantic v2
│  │  ├─ api/v1/            # 路由：auth, rooms, racks, devices, odf, patch_cords,
│  │  │                     #   interconnects, cables, links, lldp, canvas, screen,
│  │  │                     #   export, changelog, tasks
│  │  ├─ services/          # 业务逻辑+审计拦截（唯一写入口）
│  │  └─ utils/             # lldp_parser, excel, port_name_normalizer
│  ├─ alembic/  ├─ tests/  └─ pyproject.toml
├─ frontend/
│  ├─ src/
│  │  ├─ api/  ├─ stores/  ├─ router/
│  │  ├─ views/             # topology, inventory, wiring, links, changelog, screen, login
│  │  ├─ components/canvas/ # Canvas.vue, DragGroup, WireLayer, DeviceSvg, PortGrid, NodeShell
│  │  └─ styles/tokens.css  # 状态色 tokens
│  └─ public/svg/{devices,ports,odf,custom}/
├─ deploy/                  # docker-compose.yml, nginx.conf, backup.sh, .env.example
├─ docs/                    # 本文档 + API.md + excel 模板说明 + LLDP 格式说明
└─ scripts/                 # seed_demo.py（演示数据）
```

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| 抓取 SVG 质量/版权不一 | 优先官方开源图标集（如 network-svg 开源库）+ 端口栅格生成器兜底；清洗脚本统一化 |
| LLDP 端口命名五花八门 | 归一化模板用户可维护；无法匹配的进 `missing/conflict` 人工处理，绝不静默 |
| 路径计算在大机房变慢 | 连接图缓存 + 后台任务表；单机房规模（<10万边）BFS 毫秒级，足够 |
| 嵌入其他项目 | API 前缀/认证模式/静态目录三处均可配置，M1 即固化 |
