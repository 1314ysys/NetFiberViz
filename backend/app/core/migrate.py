"""轻量幂等迁移：仅做 ADD COLUMN（带默认值），兼容 SQLite 与 MySQL。

新表由 Base.metadata.create_all 负责；已存在的表新增字段在此补齐，
避免开发/生产环境因表已存在而缺少新列。
"""
import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

log = logging.getLogger("migrate")

# SQL 标识符白名单：DDL 无法参数化，必须确保表名/列名来自受信常量而非外部输入
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _ident(name: str) -> str:
    if not _SAFE_IDENT.match(name or ""):
        raise ValueError(f"非法 SQL 标识符: {name!r}")
    return name

# (table, column, ddl)
COLUMNS: list[tuple[str, str, str]] = [
    # ODF 单元柜：自由拖拽坐标 + 未分组容器标记
    ("odf_units", "pos_x", "FLOAT DEFAULT 0"),
    ("odf_units", "pos_y", "FLOAT DEFAULT 0"),
    ("odf_units", "is_pending", "BOOLEAN DEFAULT 0"),
    # ODF 盘：自由拖拽坐标
    ("odf_trays", "pos_x", "FLOAT DEFAULT 0"),
    ("odf_trays", "pos_y", "FLOAT DEFAULT 0"),
    # 设备：模板标识 + 图形类别 + 占用 U 数
    ("devices", "template_key", "VARCHAR(64) DEFAULT ''"),
    ("devices", "category", "VARCHAR(32) DEFAULT ''"),
    ("devices", "u_height", "INTEGER DEFAULT 1"),
    ("devices", "port_layout", "VARCHAR(16) DEFAULT 'horizontal'"),
    ("devices", "panel_width", "INTEGER DEFAULT 480"),
    # 端口：分组名与组序（分组成排）
    ("ports", "group_name", "VARCHAR(64) DEFAULT ''"),
    ("ports", "group_seq", "INTEGER DEFAULT 0"),
    # 机房层级（核心机房 → 前端机房，自引用树）
    ("rooms", "parent_id", "INTEGER"),
    # 角色：core_admin / site_admin
    ("users", "role", "VARCHAR(16) DEFAULT 'site_admin'"),
]


async def _existing_columns(conn: AsyncConnection, table: str) -> set[str]:
    table = _ident(table)
    if conn.dialect.name == "sqlite":
        res = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in res.fetchall()}
    res = await conn.execute(
        text("SELECT COLUMN_NAME FROM information_schema.columns WHERE table_name = :t"),
        {"t": table},
    )
    return {row[0] for row in res.fetchall()}


async def ensure_columns(conn: AsyncConnection) -> list[str]:
    applied: list[str] = []
    for table, column, ddl in COLUMNS:
        try:
            cols = await _existing_columns(conn, table)
        except Exception as e:  # 表不存在等
            log.warning("skip migration check %s.%s: %s", table, column, e)
            continue
        if column in cols:
            continue
        await conn.execute(text(
            f"ALTER TABLE {_ident(table)} ADD COLUMN {_ident(column)} {ddl}"))
        applied.append(f"{table}.{column}")
    if applied:
        log.info("migrated columns: %s", ", ".join(applied))

    # 首次加 u_height 列时，按模板回填多 U 设备的默认高度
    if "devices.u_height" in applied:
        try:
            from app.api.v1.device_templates import u_height_of
            rows = (await conn.execute(text(
                "SELECT id, template_key, category FROM devices "
                "WHERE template_key IS NOT NULL AND template_key <> ''"))).fetchall()
            for did, tkey, cat in rows:
                uh = u_height_of(tkey or "", cat or "")
                if uh > 1:
                    await conn.execute(
                        text("UPDATE devices SET u_height = :h WHERE id = :i"),
                        {"h": uh, "i": did})
            log.info("backfilled u_height for %d devices", len(rows))
        except Exception as e:
            log.warning("backfill u_height failed: %s", e)
    # 数据回填：历史设备端口没有分组信息，按接口类型归组，保证前端"分组成排"可显示
    try:
        await conn.execute(text("""
            UPDATE ports SET
              group_name = CASE port_type
                WHEN 'rj45' THEN '电口'
                WHEN 'sfp' THEN 'SFP 光口'
                WHEN 'sfp_plus' THEN 'XGE 光口'
                WHEN 'qsfp' THEN 'QSFP 光口'
                WHEN 'pon' THEN 'PON 口'
                WHEN 'sc' THEN 'SC 光口'
                WHEN 'fc' THEN 'FC 光口'
                ELSE '光口' END,
              group_seq = CASE port_type WHEN 'rj45' THEN 0 ELSE 1 END
            WHERE owner_type = 'device' AND (group_name IS NULL OR group_name = '')
        """))
    except Exception as e:
        log.warning("backfill port groups failed: %s", e)

    # 至少保留一个核心管理员（首次升级时把最早的用户提升为 core_admin）
    try:
        n_core = (await conn.execute(text(
            "SELECT COUNT(*) FROM users WHERE role = 'core_admin'"))).scalar() or 0
        n_user = (await conn.execute(text("SELECT COUNT(*) FROM users"))).scalar() or 0
        if n_core == 0 and n_user > 0:
            await conn.execute(text(
                "UPDATE users SET role = 'core_admin' "
                "WHERE id = (SELECT MIN(id) FROM (SELECT id FROM users) t)"))
            log.info("promoted earliest user to core_admin")
    except Exception as e:
        log.warning("backfill admin role failed: %s", e)

    return applied
