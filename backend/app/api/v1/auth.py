from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Room, User, UserRoom
from app.services import ratelimit
from app.services.perms import require_core

router = APIRouter(prefix="/auth", tags=["auth"])

ROLES = ("core_admin", "site_admin")

PASSWORD_MIN = 8


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    room_ids: list[int] = []


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    display_name: str = ""
    role: str = "site_admin"
    room_ids: list[int] = []


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=PASSWORD_MIN, max_length=128)
    room_ids: list[int] | None = None


async def _room_ids(db: AsyncSession, user_id: int) -> list[int]:
    return [r.room_id for r in (await db.execute(
        select(UserRoom).where(UserRoom.user_id == user_id))).scalars()]


async def _set_rooms(db: AsyncSession, user_id: int, room_ids: list[int]) -> None:
    await db.execute(delete(UserRoom).where(UserRoom.user_id == user_id))
    if room_ids:
        valid = {r.id for r in (await db.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()}
        for rid in valid:
            db.add(UserRoom(user_id=user_id, room_id=rid))


async def _to_out(db: AsyncSession, u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, display_name=u.display_name,
                   role=u.role, is_active=u.is_active, room_ids=await _room_ids(db, u.id))


@router.post("/login")
async def login(request: Request,
                form: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    username = form.username or ""

    locked, remaining = ratelimit.is_locked(ip, username)
    if locked:
        raise HTTPException(
            429, f"登录失败次数过多，请 {remaining} 秒后再试",
            headers={"Retry-After": str(remaining)},
        )

    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        count = ratelimit.record_failure(ip, username)
        raise HTTPException(
            401,
            "用户名或密码错误" if count < ratelimit.MAX_FAILURES
            else "登录失败次数过多，账号已临时锁定",
        )

    ratelimit.clear(ip, username)
    return {"access_token": create_access_token(user.username), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _to_out(db, user)


# ---------------- 用户管理（仅核心管理员） ----------------
@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await require_core(user)
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return [await _to_out(db, u) for u in users]


@router.post("/users", response_model=UserOut)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    await require_core(user)
    if body.role not in ROLES:
        raise HTTPException(400, "非法角色")
    exists = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "用户名已存在")
    u = User(username=body.username, password_hash=hash_password(body.password),
             display_name=body.display_name, role=body.role)
    db.add(u)
    await db.flush()
    await _set_rooms(db, u.id, body.room_ids)
    await db.commit()
    await db.refresh(u)
    return await _to_out(db, u)


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    await require_core(user)
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, "非法角色")
        # 不允许把最后一个核心管理员降级
        if u.role == "core_admin" and body.role != "core_admin":
            n_core = len((await db.execute(
                select(User).where(User.role == "core_admin"))).scalars().all())
            if n_core <= 1:
                raise HTTPException(409, "至少需要保留一个核心管理员")
        u.role = body.role
    if body.display_name is not None:
        u.display_name = body.display_name
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
    if body.room_ids is not None:
        await _set_rooms(db, u.id, body.room_ids)
    await db.commit()
    await db.refresh(u)
    return await _to_out(db, u)


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    await require_core(user)
    if user_id == user.id:
        raise HTTPException(400, "不能删除当前登录账号")
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    if u.role == "core_admin":
        n_core = len((await db.execute(
            select(User).where(User.role == "core_admin"))).scalars().all())
        if n_core <= 1:
            raise HTTPException(409, "至少需要保留一个核心管理员")
    await db.execute(delete(UserRoom).where(UserRoom.user_id == user_id))
    await db.delete(u)
    await db.commit()
    return {"ok": True}
