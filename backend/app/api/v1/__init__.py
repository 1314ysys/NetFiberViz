from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth, rooms, devices, odf, cords, interconnects, cables, links, changelog, canvas
from app.api.v1 import lldp, export, import_excel
from app.core.db import get_db
from app.core.deps import get_current_user

api_router = APIRouter()
api_router.include_router(auth.router)
for r in (rooms, devices, odf, cords, interconnects, cables, links, changelog, canvas,
          lldp, export, import_excel):
    api_router.include_router(r.router, dependencies=[Depends(get_current_user)])
