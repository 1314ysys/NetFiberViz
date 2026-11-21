"""设备模板库：常见机房设备的固定端口组合。

模板字段：
  key / name / category / device_type
  layout   端口排列方向（horizontal | vertical）
  width    面板宽度（画布单位，用于机柜视图渲染）
  groups   端口组：[{name, prefix, count, type}]
           type 取 PORT_TYPES 的 key（如 "RJ45/CAT6"、"LC/UPC"、"SFP+"）
  u_height 占用机柜 U 数（可选，缺省由类别决定）
"""

from app.services.port_types import PORT_TYPES

# category -> 中文名（界面分类展示）
CATEGORIES: dict[str, str] = {
    "sw": "交换机",
    "router": "路由器",
    "firewall": "防火墙",
    "olt": "OLT",
    "otp": "光传送平台",
    "otn": "OTN",
    "oadm": "光分插复用",
    "dwdm": "波分设备",
    "amp": "光放大器",
    "osw": "光切换器",
    "tx": "光发射机",
    "rx": "光接收机",
    "media_conv": "光纤收发器",
    "mux": "合波器",
    "demux": "分波器",
    "splitter": "分光器",
    "patch_panel": "配线面板",
    "custom": "自定义",
}


def _g(name: str, prefix: str, count: int, ptype: str, gap: int = 0) -> dict:
    """端口组。gap = 组前留白（端口宽度数），用于视觉分块。"""
    return {"name": name, "prefix": prefix, "count": count, "type": ptype, "gap": gap}


def _w(groups: list[dict], per_port: int = 11, pad: int = 24) -> int:
    """按端口数估算面板宽度。"""
    total = sum(g["count"] for g in groups)
    gaps = sum(g.get("gap", 0) for g in groups)
    return max(120, total * per_port + gaps * per_port + pad)


TEMPLATES: list[dict] = [
    # ---------------- 交换机 ----------------
    {"key": "sw-24ge-4sfp", "name": "交换机 24×GE + 4×SFP+", "category": "sw", "device_type": "sw",
     "layout": "horizontal", "groups": [
         _g("GE 电口", "GE0/0/", 24, "RJ45/CAT6"),
         _g("SFP+ 光口", "XGE0/1/", 4, "SFP+", gap=3)]},
    {"key": "sw-48ge-6sfp", "name": "交换机 48×GE + 6×SFP+", "category": "sw", "device_type": "sw",
     "layout": "horizontal", "groups": [
         _g("GE 电口", "GE0/0/", 48, "RJ45/CAT6"),
         _g("SFP+ 光口", "XGE0/1/", 6, "SFP+", gap=4)]},
    {"key": "sw-24ge-4sfp28", "name": "交换机 24×GE + 4×SFP28", "category": "sw", "device_type": "sw",
     "layout": "horizontal", "groups": [
         _g("GE 电口", "GE0/0/", 24, "RJ45/CAT6"),
         _g("SFP28 光口", "25GE0/1/", 4, "SFP28", gap=3)]},
    {"key": "sw-48xge-6qsfp", "name": "数据中心交换机 48×SFP+ + 6×QSFP28", "category": "sw", "device_type": "sw",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("SFP+ 光口", "XGE0/1/", 48, "SFP+"),
         _g("QSFP28 光口", "100GE0/2/", 6, "QSFP28", gap=4)]},
    {"key": "sw-8ge-2sfp", "name": "小型交换机 8×GE + 2×SFP", "category": "sw", "device_type": "sw",
     "layout": "horizontal", "groups": [
         _g("GE 电口", "GE0/0/", 8, "RJ45/CAT6"),
         _g("SFP 光口", "SFP0/1/", 2, "SFP", gap=2)]},
    {"key": "sw-24lc", "name": "全光交换机 24×LC", "category": "sw", "device_type": "sw",
     "layout": "horizontal", "groups": [_g("LC 光口", "OPT/", 24, "LC/UPC")]},

    # ---------------- 路由器 / 防火墙 ----------------
    {"key": "router-8ge-2sfp", "name": "路由器 8×GE + 2×SFP+", "category": "router", "device_type": "sw",
     "layout": "horizontal", "groups": [
         _g("GE 电口", "GE0/0/", 8, "RJ45/CAT6"),
         _g("SFP+ 光口", "XGE0/1/", 2, "SFP+", gap=2)]},
    {"key": "fw-8ge", "name": "防火墙 8×GE", "category": "firewall", "device_type": "sw",
     "layout": "horizontal", "groups": [_g("GE 电口", "GE0/0/", 8, "RJ45/CAT6")]},

    # ---------------- OLT ----------------
    {"key": "olt-8pon", "name": "OLT 8×PON + 4×SFP+", "category": "olt", "device_type": "olt",
     "layout": "horizontal", "groups": [
         _g("PON 口", "GPON0/", 8, "PON/UPC"),
         _g("SFP+ 上行", "XGE0/1/", 4, "SFP+", gap=3)]},
    {"key": "olt-16pon", "name": "OLT 16×PON + 4×SFP+", "category": "olt", "device_type": "olt",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("PON 口", "GPON0/", 16, "PON/UPC"),
         _g("SFP+ 上行", "XGE0/1/", 4, "SFP+", gap=3)]},
    {"key": "olt-16pon-2qsfp", "name": "OLT 16×PON + 2×QSFP28", "category": "olt", "device_type": "olt",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("PON 口", "GPON0/", 16, "PON/APC"),
         _g("QSFP28 上行", "100GE0/1/", 2, "QSFP28", gap=3)]},

    # ---------------- 光传送平台 / OTN ----------------
    {"key": "otp-2x10g", "name": "光传送平台 2×10G", "category": "otp", "device_type": "tx",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("客户侧", "CLI/", 2, "SFP+"),
         _g("线路侧", "LINE/", 2, "SFP+", gap=3)]},
    {"key": "otp-8x10g", "name": "光传送平台 8×10G", "category": "otp", "device_type": "tx",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("客户侧", "CLI/", 8, "SFP+"),
         _g("线路侧", "LINE/", 2, "SFP+", gap=3)]},
    {"key": "otp-16x10g", "name": "光传送平台 16×10G", "category": "otp", "device_type": "tx",
     "layout": "horizontal", "u_height": 4, "groups": [
         _g("客户侧", "CLI/", 16, "SFP+"),
         _g("线路侧", "LINE/", 4, "SFP+", gap=4)]},
    {"key": "otp-4x100g", "name": "光传送平台 4×100G", "category": "otp", "device_type": "tx",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("客户侧", "CLI/", 4, "QSFP28"),
         _g("线路侧", "LINE/", 2, "QSFP28", gap=3)]},
    {"key": "otn-8x10g-2x100g", "name": "OTN 8×10G + 2×100G", "category": "otn", "device_type": "tx",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("10G 支路", "CLI10G/", 8, "SFP+"),
         _g("100G 线路", "LINE100G/", 2, "QSFP28", gap=4)]},

    # ---------------- 波分 / 光放 ----------------
    {"key": "oadm-8ch", "name": "光分插复用 8 波", "category": "oadm", "device_type": "oadm",
     "layout": "horizontal", "groups": [
         _g("线路侧", "LINE/", 2, "LC/UPC"),
         _g("支路侧", "CH/", 8, "LC/UPC", gap=3)]},
    {"key": "oadm-16ch", "name": "光分插复用 16 波", "category": "oadm", "device_type": "oadm",
     "layout": "horizontal", "u_height": 2, "groups": [
         _g("线路侧", "LINE/", 2, "LC/APC"),
         _g("支路侧", "CH/", 16, "LC/APC", gap=3)]},
    {"key": "dwdm-40ch", "name": "波分设备 40 波", "category": "dwdm", "device_type": "oadm",
     "layout": "horizontal", "u_height": 4, "groups": [
         _g("线路侧", "LINE/", 2, "LC/APC"),
         _g("波长口", "CH/", 40, "LC/APC", gap=4)]},
    {"key": "amp-edfa-2", "name": "光放大器 EDFA 2 口", "category": "amp", "device_type": "amp",
     "layout": "horizontal", "groups": [_g("光口", "LC/", 2, "LC/UPC")]},
    {"key": "amp-edfa-4", "name": "光放大器 EDFA 4 口", "category": "amp", "device_type": "amp",
     "layout": "horizontal", "groups": [_g("光口", "LC/", 4, "LC/UPC")]},

    # ---------------- 光切换 ----------------
    {"key": "osw-4x4", "name": "光切换器 4×4", "category": "osw", "device_type": "custom",
     "layout": "horizontal", "groups": [
         _g("输入", "IN/", 4, "LC/UPC"),
         _g("输出", "OUT/", 4, "LC/UPC", gap=3)]},

    # ---------------- 分光 / 配线 ----------------
    {"key": "splitter-1x8", "name": "分光器 1×8", "category": "splitter", "device_type": "custom",
     "layout": "horizontal", "groups": [
         _g("输入", "IN/", 1, "SC/UPC"),
         _g("输出", "OUT/", 8, "SC/UPC", gap=2)]},
    {"key": "splitter-1x16", "name": "分光器 1×16", "category": "splitter", "device_type": "custom",
     "layout": "horizontal", "groups": [
         _g("输入", "IN/", 1, "SC/APC"),
         _g("输出", "OUT/", 16, "SC/APC", gap=2)]},
    {"key": "pp-24lc", "name": "配线面板 24×LC", "category": "patch_panel", "device_type": "custom",
     "layout": "horizontal", "groups": [_g("LC 端口", "LC/", 24, "LC/UPC")]},
    {"key": "pp-48lc", "name": "配线面板 48×LC", "category": "patch_panel", "device_type": "custom",
     "layout": "horizontal", "u_height": 2, "groups": [_g("LC 端口", "LC/", 48, "LC/UPC")]},
    {"key": "pp-24sc", "name": "配线面板 24×SC", "category": "patch_panel", "device_type": "custom",
     "layout": "horizontal", "groups": [_g("SC 端口", "SC/", 24, "SC/UPC")]},

    # ---------------- 收发器 ----------------
    {"key": "mc-1", "name": "光纤收发器 1 电 1 光", "category": "media_conv", "device_type": "media_conv",
     "layout": "horizontal", "groups": [
         _g("电口", "ETH/", 1, "RJ45/CAT6"),
         _g("光口", "OPT/", 1, "SC/UPC", gap=2)]},
    {"key": "mc-8", "name": "光纤收发器 8 路", "category": "media_conv", "device_type": "media_conv",
     "layout": "horizontal", "groups": [
         _g("电口", "ETH/", 8, "RJ45/CAT6"),
         _g("光口", "OPT/", 8, "SC/UPC", gap=3)]},

    # ---------------- 自定义（设计器入口） ----------------
    {"key": "custom", "name": "自定义设备（手动定义端口组）", "category": "custom", "device_type": "custom",
     "layout": "horizontal", "groups": []},
]

# 面板宽度按端口数估算（模板未显式给出时）
for _t in TEMPLATES:
    if "width" not in _t:
        _t["width"] = _w(_t["groups"])

TEMPLATE_BY_KEY: dict[str, dict] = {t["key"]: t for t in TEMPLATES}

# 各类设备默认占用机柜 U 数（模板可用 u_height 字段覆盖）
DEFAULT_U_HEIGHT: dict[str, int] = {
    "sw": 1, "router": 1, "firewall": 1,
    "olt": 2, "oadm": 1, "amp": 1, "dwdm": 2,
    "otp": 2, "otn": 2, "osw": 1, "tx": 1, "rx": 1,
    "media_conv": 1, "mux": 1, "demux": 1,
    "splitter": 1, "patch_panel": 1, "custom": 1,
}

# 个别常见机型为多 U（覆盖类别默认值）
U_HEIGHT_BY_TEMPLATE: dict[str, int] = {
    "olt-16pon": 2, "olt-16pon-2qsfp": 2,
    "otp-2x10g": 2, "otp-8x10g": 2, "otp-16x10g": 4, "otp-4x100g": 2,
    "otn-8x10g-2x100g": 2,
    "dwdm-40ch": 4, "oadm-16ch": 2,
    "sw-48xge-6qsfp": 2, "pp-48lc": 2,
}


def u_height_of(template_key: str = "", category: str = "") -> int:
    """设备默认占机柜 U 数：模板专属 > 类别默认 > 1U。"""
    tpl = TEMPLATE_BY_KEY.get(template_key)
    if tpl and tpl.get("u_height"):
        return int(tpl["u_height"])
    if template_key in U_HEIGHT_BY_TEMPLATE:
        return U_HEIGHT_BY_TEMPLATE[template_key]
    return DEFAULT_U_HEIGHT.get(category, 1)


def build_ports(groups: list[dict]) -> list[dict]:
    """按端口组展开为端口列表（含 group_name / group_seq / port_type）。"""
    out: list[dict] = []
    for gi, g in enumerate(groups):
        name = str(g.get("name") or f"组{gi + 1}")
        prefix = str(g.get("prefix") or "")
        count = int(g.get("count") or 0)
        ptype = str(g.get("type") or "LC/UPC")
        for i in range(1, count + 1):
            out.append({
                "port_no": f"{prefix}{i}",
                "port_type": ptype,
                "group_name": name,
                "group_seq": gi,
            })
    return out


def build_ports_from_layout(layout: dict) -> list[dict]:
    """从设计器布局生成端口（显式坐标由前端渲染，这里只取编号/类型/组）。"""
    ports = (layout or {}).get("ports") or []
    out: list[dict] = []
    for p in ports:
        out.append({
            "port_no": str(p.get("no") or ""),
            "port_type": str(p.get("type") or "LC/UPC"),
            "group_name": str(p.get("group") or ""),
            "group_seq": int(p.get("group_seq") or 0),
        })
    return [p for p in out if p["port_no"]]


def port_type_keys() -> set[str]:
    return {p.key for p in PORT_TYPES}
