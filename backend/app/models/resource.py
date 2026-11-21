from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    address: Mapped[str] = mapped_column(String(256), default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True, index=True)
    canvas_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Rack(Base):
    __tablename__ = "racks"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64))
    u_count: Mapped[int] = mapped_column(Integer, default=42)
    pos_x: Mapped[float] = mapped_column(default=0)
    pos_y: Mapped[float] = mapped_column(default=0)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    rack_id: Mapped[int] = mapped_column(ForeignKey("racks.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128), default="")
    device_type: Mapped[str] = mapped_column(
        Enum("sw", "olt", "oadm", "amp", "tx", "rx", "media_conv", "custom", name="device_type"),
        default="sw",
    )
    template_key: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(32), default="")   # 图形类别（含枚举外的光切换器/光传送平台等）
    svg_key: Mapped[str] = mapped_column(String(128), default="sw-generic")
    u_position: Mapped[int] = mapped_column(Integer, default=1)
    u_height: Mapped[int] = mapped_column(Integer, default=1)   # 占用 U 数
    port_layout: Mapped[str] = mapped_column(String(16), default="horizontal")  # 端口排列方向
    panel_width: Mapped[int] = mapped_column(Integer, default=480)              # 面板宽度（画布单位）
    mgmt_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Port(Base):
    """统一端口抽象：设备端口与 ODF 孔位共用一张表。"""

    __tablename__ = "ports"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "port_no", name="uq_port_owner_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(Enum("device", "odf_slot", name="port_owner_type"))
    owner_id: Mapped[int] = mapped_column(Integer, index=True)  # device.id 或 odf_slot.id
    port_no: Mapped[str] = mapped_column(String(64))            # 如 "GE0/0/1" 或 ODF "A1"
    port_type: Mapped[str] = mapped_column(String(32), default="LC/UPC")
    group_name: Mapped[str] = mapped_column(String(64), default="")   # 端口组名，如 "GE 电口"
    group_seq: Mapped[int] = mapped_column(Integer, default=0)        # 组顺序（分组成排）
    status: Mapped[str] = mapped_column(
        Enum("free", "used", "reserved", "fault", name="port_status"), default="free"
    )
    label: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
