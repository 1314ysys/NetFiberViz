from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class OdfCabinet(Base):
    __tablename__ = "odf_cabinets"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64))
    pos_x: Mapped[float] = mapped_column(default=0)
    pos_y: Mapped[float] = mapped_column(default=0)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OdfUnit(Base):
    """单元柜：默认 A/B/C/D/E，可增删改名；is_pending 表示"未分组"容器（不显示在 UI）。"""

    __tablename__ = "odf_units"
    __table_args__ = (UniqueConstraint("cabinet_id", "name", name="uq_unit_cab_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cabinet_id: Mapped[int] = mapped_column(ForeignKey("odf_cabinets.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))  # "A"...
    seq: Mapped[int] = mapped_column(Integer, default=1)
    pos_x: Mapped[float] = mapped_column(default=0)
    pos_y: Mapped[float] = mapped_column(default=0)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=False)


class OdfTray(Base):
    """盘：默认 12 孔；1 行 x12 列（行标省略）或 2 行 x6 列（A/B 行标）。"""

    __tablename__ = "odf_trays"
    __table_args__ = (UniqueConstraint("unit_id", "name", name="uq_tray_unit_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("odf_units.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))  # "1","2"...
    slots_per_row: Mapped[int] = mapped_column(Integer, default=12)
    rows: Mapped[int] = mapped_column(Integer, default=1)
    seq: Mapped[int] = mapped_column(Integer, default=1)
    pos_x: Mapped[float] = mapped_column(default=0)
    pos_y: Mapped[float] = mapped_column(default=0)


class OdfSlot(Base):
    """孔位：row_label ('A'/'B' 或 '') + col_no → 编址 单元字母+行标+列号。"""

    __tablename__ = "odf_slots"
    __table_args__ = (UniqueConstraint("tray_id", "row_label", "col_no", name="uq_slot_pos"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tray_id: Mapped[int] = mapped_column(ForeignKey("odf_trays.id"), index=True)
    row_label: Mapped[str] = mapped_column(String(4), default="")
    col_no: Mapped[int] = mapped_column(Integer)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), unique=True)

    unit: Mapped["OdfUnit"] = relationship(
        primaryjoin="OdfSlot.tray_id==OdfTray.id",
        viewonly=True,
        remote_side="OdfTray.id",
        uselist=False,
    )
