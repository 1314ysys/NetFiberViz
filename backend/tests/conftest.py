import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_fiber.db"

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import Base, SessionLocal, engine
from app.main import app

TIMEOUT = 30.0


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    from app.core.security import hash_password
    from app.models import User
    async with SessionLocal() as db:
        db.add(User(username="admin", password_hash=hash_password("admin123"),
                    display_name="init", role="core_admin"))
        await db.commit()
    yield
    await engine.dispose()


@pytest.fixture(scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
async def token(client):
    # main lifespan 建了首个 admin/admin123
    r = await client.post("/fiber/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
async def auth_client(client, token):
    client.headers["Authorization"] = f"Bearer {token}"
    return client
