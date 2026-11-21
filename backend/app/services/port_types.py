"""端口类型字典与兼容性判定。

端口类型分三大族：
- fiber  光纤接头（LC/SC/FC/ST/E2000/MPO，各含 UPC/APC 研磨）
- optic  光模块笼位（SFP/SFP+/SFP28/QSFP+/QSFP28/CFP）
- pon    PON 口（SC 接头，含 UPC/APC）
- copper 电口（RJ45 CAT5e/6/6A/7）

兼容规则（与用户确认）：
- 光电互连 → 硬拒绝
- 同族但类型不同 → 仅警告，可强制
- 未标注类型 → 放行
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PortType:
    key: str          # 存储值，如 "LC/UPC"
    label: str        # 显示名
    family: str       # fiber | optic | pon | copper
    shape: str        # 画布外形：lc | sc | fc | st | rj45 | cage | mpo
    polish: str = ""  # UPC | APC


PORT_TYPES: list[PortType] = [
    # ---- 光纤接头（UPC/APC）----
    PortType("LC/UPC", "LC/UPC", "fiber", "lc", "UPC"),
    PortType("LC/APC", "LC/APC", "fiber", "lc", "APC"),
    PortType("SC/UPC", "SC/UPC", "fiber", "sc", "UPC"),
    PortType("SC/APC", "SC/APC", "fiber", "sc", "APC"),
    PortType("FC/UPC", "FC/UPC", "fiber", "fc", "UPC"),
    PortType("FC/APC", "FC/APC", "fiber", "fc", "APC"),
    PortType("ST/UPC", "ST/UPC", "fiber", "st", "UPC"),
    PortType("ST/APC", "ST/APC", "fiber", "st", "APC"),
    PortType("E2000/APC", "E2000/APC", "fiber", "sc", "APC"),
    PortType("MPO/UPC", "MPO/UPC", "fiber", "mpo", "UPC"),
    PortType("MPO/APC", "MPO/APC", "fiber", "mpo", "APC"),
    # ---- 光模块笼位 ----
    PortType("SFP", "SFP", "optic", "cage"),
    PortType("SFP+", "SFP+", "optic", "cage"),
    PortType("SFP28", "SFP28", "optic", "cage"),
    PortType("QSFP+", "QSFP+", "optic", "cage"),
    PortType("QSFP28", "QSFP28", "optic", "cage"),
    PortType("CFP", "CFP", "optic", "cage"),
    # ---- PON ----
    PortType("PON/UPC", "PON (SC/UPC)", "pon", "sc", "UPC"),
    PortType("PON/APC", "PON (SC/APC)", "pon", "sc", "APC"),
    # ---- 电口 ----
    PortType("RJ45/CAT5e", "RJ45 超五类", "copper", "rj45"),
    PortType("RJ45/CAT6", "RJ45 六类", "copper", "rj45"),
    PortType("RJ45/CAT6A", "RJ45 超六类", "copper", "rj45"),
    PortType("RJ45/CAT7", "RJ45 七类", "copper", "rj45"),
]

PORT_TYPE_BY_KEY: dict[str, PortType] = {p.key: p for p in PORT_TYPES}

FAMILY_LABEL = {
    "fiber": "光纤",
    "optic": "光模块",
    "pon": "PON",
    "copper": "电口",
}

# 兼容性分组：fiber/optic/pon 同属"光"，copper 属"电"
FAMILY_MEDIUM = {"fiber": "optical", "optic": "optical", "pon": "optical", "copper": "electrical"}


def family_of(port_type: str) -> str:
    """返回端口族；未知类型返回空串。"""
    pt = PORT_TYPE_BY_KEY.get(port_type or "")
    return pt.family if pt else ""


def medium_of(port_type: str) -> str:
    fam = family_of(port_type)
    return FAMILY_MEDIUM.get(fam, "")


def check_compatibility(a_type: str, b_type: str) -> tuple[str, str]:
    """判定两端端口类型是否可连。

    返回 (level, message)：
      level = "ok"     可直接连接
      level = "warn"   类型不匹配，但允许强制确认
      level = "block"  物理上不成立，拒绝
    """
    if not a_type or not b_type:
        return "ok", ""
    ma, mb = medium_of(a_type), medium_of(b_type)
    if not ma or not mb:
        # 含未知类型，放行
        return "ok", ""
    if ma != mb:
        return "block", f"光口与电口不能互连（{a_type} ↔ {b_type}）"
    if a_type == b_type:
        return "ok", ""

    # 同属光/电但类型不同：给出具体差异
    pa, pb = PORT_TYPE_BY_KEY.get(a_type), PORT_TYPE_BY_KEY.get(b_type)
    if pa and pb:
        if pa.family == pb.family and pa.polish and pb.polish and pa.polish != pb.polish:
            return "warn", f"研磨方式不同（{pa.polish} ↔ {pb.polish}），现场可能使用转接跳线"
        return "warn", f"接口类型不同（{pa.label} ↔ {pb.label}），现场可能使用转接跳线"
    return "warn", f"接口类型不同（{a_type} ↔ {b_type}）"


def port_types_payload() -> list[dict]:
    """供前端下拉与外形渲染使用。"""
    return [
        {"key": p.key, "label": p.label, "family": p.family,
         "familyLabel": FAMILY_LABEL.get(p.family, p.family),
         "shape": p.shape, "polish": p.polish}
        for p in PORT_TYPES
    ]
