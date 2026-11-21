from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="done")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PatchCord(Base):
    """跳纤（物理段）：port_a ↔ port_b，台账/变更基本单位。"""

    __tablename__ = "patch_cords"
    id: Mapped[int] = mapped_column(primary_key=True)
    port_a_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), index=True)
    port_b_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), index=True)
    cord_type: Mapped[str] = mapped_column(String(64), default="LC-LC 单模")
    length_m: Mapped[float] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(Enum("active", "removed", name="cord_status"), default="active")
    remark: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Interconnect(Base):
    """ODF 盘间物理连接：splice(熔接) / adapter(法兰直通)。"""

    __tablename__ = "interconnects"
    id: Mapped[int] = mapped_column(primary_key=True)
    slot_a_id: Mapped[int] = mapped_column(ForeignKey("odf_slots.id"), index=True)
    slot_b_id: Mapped[int] = mapped_column(ForeignKey("odf_slots.id"), index=True)
    kind: Mapped[str] = mapped_column(Enum("splice", "adapter", name="interconnect_kind"))
    remark: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cable(Base):
    __tablename__ = "cables"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    core_count: Mapped[int] = mapped_column(Integer, default=24)
    cable_type: Mapped[str] = mapped_column(String(64), default="GYTA 单模")
    direction_from: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Core(Base):
    """纤芯：未成端/已成端(占孔位)/芯对芯熔接/备用/故障。"""

    __tablename__ = "cores"
    id: Mapped[int] = mapped_column(primary_key=True)
    cable_id: Mapped[int] = mapped_column(ForeignKey("cables.id"), index=True)
    core_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        Enum("unused", "landed", "spliced", "spare", "fault", name="core_status"), default="unused"
    )
    port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    peer_core_id: Mapped[int | None] = mapped_column(ForeignKey("cores.id"), nullable=True)


class Link(Base):
    """逻辑端到端链路：path_json 记录有序段序列。"""

    __tablename__ = "links"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    a_port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), index=True)
    z_port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), index=True)
    path_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
