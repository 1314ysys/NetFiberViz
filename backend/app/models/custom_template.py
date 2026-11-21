from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base


class CustomDeviceTemplate(Base):
    """用户通过「设备面板设计器」绘制的设备模板。

    layout_json 结构：
    {
      "width": 482, "height": 44,          # 面板画布尺寸（画布单位）
      "ports": [
        {"no": "GE0/0/1", "type": "RJ45/CAT6", "group": "GE 电口",
         "group_seq": 0, "x": 12, "y": 18}
      ]
    }
    """

    __tablename__ = "custom_device_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32), default="custom")
    device_type: Mapped[str] = mapped_column(String(32), default="custom")
    width: Mapped[int] = mapped_column(Integer, default=480)
    height: Mapped[int] = mapped_column(Integer, default=44)
    u_height: Mapped[int] = mapped_column(Integer, default=1)
    layout_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str] = mapped_column(String(256), default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
