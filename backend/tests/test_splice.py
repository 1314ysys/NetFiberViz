"""批量熔接：成功/失败明细、对端关系、不可重复熔接。"""
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
async def cables(cli):
    r = await cli.post(f"{API}/rooms", json={"name": "熔接测试机房", "code": "SP-ROOM"})
    room = r.json()
    a = (await cli.post(f"{API}/cables", json={
        "room_id": room["id"], "name": "SP-A", "core_count": 12})).json()
    b = (await cli.post(f"{API}/cables", json={
        "room_id": room["id"], "name": "SP-B", "core_count": 12})).json()
    return a, b


@pytest.mark.asyncio
async def test_batch_splice_success(cli, cables):
    a, b = cables
    ca = (await cli.get(f"{API}/cores", params={"cable_id": a["id"]})).json()
    cb = (await cli.get(f"{API}/cores", params={"cable_id": b["id"]})).json()
    pairs = [{"core_a_id": ca[i]["id"], "core_b_id": cb[i]["id"]} for i in range(3)]
    r = await cli.post(f"{API}/cores/batch-splice", json={"pairs": pairs})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["succeeded_count"] == 3
    assert d["failed_count"] == 0

    # 对端关系正确
    ca2 = (await cli.get(f"{API}/cores", params={"cable_id": a["id"]})).json()
    assert ca2[0]["status"] == "spliced"
    assert ca2[0]["peer_core"]["core_no"] == cb[0]["core_no"]


@pytest.mark.asyncio
async def test_batch_splice_partial_failure(cli, cables):
    a, b = cables
    ca = (await cli.get(f"{API}/cores", params={"cable_id": a["id"]})).json()
    cb = (await cli.get(f"{API}/cores", params={"cable_id": b["id"]})).json()
    # 芯 0 已熔接 → 应失败；芯 3/4 未熔接 → 成功；不存在 → 失败
    pairs = [
        {"core_a_id": ca[0]["id"], "core_b_id": cb[5]["id"]},   # A 已熔接
        {"core_a_id": ca[3]["id"], "core_b_id": cb[3]["id"]},   # ok
        {"core_a_id": 999999, "core_b_id": cb[4]["id"]},        # 不存在
        {"core_a_id": ca[4]["id"], "core_b_id": cb[4]["id"]},   # ok
    ]
    r = await cli.post(f"{API}/cores/batch-splice", json={"pairs": pairs})
    d = r.json()
    assert d["succeeded_count"] == 2, d
    assert d["failed_count"] == 2, d
    reasons = " ".join(x["reason"] for x in d["failed"])
    assert "不存在" in reasons and "已熔接" in reasons


@pytest.mark.asyncio
async def test_batch_splice_same_cable_rejected(cli, cables):
    a, _ = cables
    ca = (await cli.get(f"{API}/cores", params={"cable_id": a["id"]})).json()
    r = await cli.post(f"{API}/cores/batch-splice", json={
        "pairs": [{"core_a_id": ca[8]["id"], "core_b_id": ca[9]["id"]}]})
    d = r.json()
    assert d["succeeded_count"] == 0
    assert "同缆" in d["failed"][0]["reason"]


@pytest.mark.asyncio
async def test_offset_rule_data(cli, cables):
    """模拟「起始偏移」：A 第 7 芯起 3 对连 B 第 6 芯起（B 1-5 已被前面用例占用）。"""
    a, b = cables
    ca = (await cli.get(f"{API}/cores", params={"cable_id": a["id"]})).json()
    cb = (await cli.get(f"{API}/cores", params={"cable_id": b["id"]})).json()
    by_no_a = {x["core_no"]: x for x in ca}
    by_no_b = {x["core_no"]: x for x in cb}
    pairs = []
    for i in range(3):
        pairs.append({"core_a_id": by_no_a[7 + i]["id"], "core_b_id": by_no_b[6 + i]["id"]})
    r = await cli.post(f"{API}/cores/batch-splice", json={"pairs": pairs})
    d = r.json()
    assert d["succeeded_count"] == 3, d

    ca2 = (await cli.get(f"{API}/cores", params={"cable_id": a["id"]})).json()
    m = {x["core_no"]: x for x in ca2}
    assert m[7]["peer_core"]["core_no"] == 6
    assert m[9]["peer_core"]["core_no"] == 8
