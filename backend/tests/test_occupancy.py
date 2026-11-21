"""U 位占用：冲突检测、自动找空位、批量状态接口。"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

API = "/fiber/api/v1"


async def _login(u, p):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30) as c:
        r = await c.post(f"{API}/auth/login", data={"username": u, "password": p})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]


@pytest.fixture(scope="module")
async def cli():
    tok = await _login("admin", "admin123")
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30)
    c.headers["Authorization"] = f"Bearer {tok}"
    yield c
    await c.aclose()


@pytest.fixture(scope="module")
async def rack(cli):
    r = await cli.post(f"{API}/rooms", json={"name": "U位测试机房", "code": "UT-ROOM"})
    room = r.json()
    r = await cli.post(f"{API}/racks", json={
        "room_id": room["id"], "name": "UT架", "code": "UT-R1", "u_count": 10})
    return r.json()


async def _dev(cli, rack, name, u_position, u_height, template="sw-24ge-4sfp"):
    return await cli.post(f"{API}/devices", json={
        "rack_id": rack["id"], "name": name, "template_key": template,
        "u_position": u_position, "u_height": u_height})


@pytest.mark.asyncio
async def test_u_height_from_template(cli, rack):
    """不传 u_height 时按模板默认（OLT 2U）。"""
    r = await _dev(cli, rack, "UT-OLT", 1, None, template="olt-16pon")
    assert r.status_code == 200, r.text
    assert r.json()["u_height"] == 2


@pytest.mark.asyncio
async def test_reject_overlap(cli, rack):
    """已被 U1-U2 占用后，再建 2U 设备到 U2 必须 409。"""
    r = await _dev(cli, rack, "UT-冲突设备", 2, 2)
    assert r.status_code == 409, r.text
    assert "冲突" in r.json()["detail"]


@pytest.mark.asyncio
async def test_allow_adjacent_non_overlap(cli, rack):
    """紧邻但不重叠应允许：U1-U2 之后建 U3-U4。"""
    r = await _dev(cli, rack, "UT-相邻设备", 3, 2)
    assert r.status_code == 200, r.text
    assert r.json()["u_height"] == 2


@pytest.mark.asyncio
async def test_update_reject_overlap(cli, rack):
    d = (await _dev(cli, rack, "UT-移动测试", 5, 1)).json()
    r = await cli.put(f"{API}/devices/{d['id']}", json={"u_position": 1})
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_update_self_no_false_conflict(cli, rack):
    """把设备改到自己的位置不应报冲突。"""
    d = (await _dev(cli, rack, "UT-原地更新", 7, 1)).json()
    r = await cli.put(f"{API}/devices/{d['id']}", json={"u_position": 7, "u_height": 1})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_batch_status(cli, rack):
    d = (await _dev(cli, rack, "UT-批量状态", 9, 1, template="sw-8ge-2sfp")).json()
    ports = (await cli.get(f"{API}/ports", params={
        "owner_type": "device", "owner_id": d["id"]})).json()
    assert len(ports) >= 3
    items = [
        {"port_id": ports[0]["id"], "status": "fault", "remark": "光模块告警"},
        {"port_id": ports[1]["id"], "status": "reserved"},
        {"port_id": 999999, "status": "fault"},
        {"port_id": ports[2]["id"], "status": "nonsense"},
    ]
    r = await cli.post(f"{API}/ports/batch-status", json={"items": items, "source": "测试平台"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated_count"] == 2
    assert body["failed_count"] == 2
    reasons = " ".join(f["reason"] for f in body["failed"])
    assert "不存在" in reasons and "非法状态" in reasons

    after = (await cli.get(f"{API}/ports", params={
        "owner_type": "device", "owner_id": d["id"]})).json()
    by_id = {p["id"]: p for p in after}
    assert by_id[ports[0]["id"]]["status"] == "fault"
    assert by_id[ports[0]["id"]]["remark"] == "光模块告警"
