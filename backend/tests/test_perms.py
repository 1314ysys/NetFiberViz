"""权限穿透回归测试：站点管理员对作用域外资源的所有写操作必须 403。

覆盖：机房 / 机柜 / 设备 / 端口 / ODF 柜·单元·盘 / 跳纤 / 盘间连接 / 光缆纤芯 / 链路 / 画布 / 用户管理。
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

API = "/fiber/api/v1"


async def _login(username: str, password: str) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30) as c:
        r = await c.post(f"{API}/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]


def _c(token: str) -> AsyncClient:
    cli = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30)
    cli.headers["Authorization"] = f"Bearer {token}"
    return cli


@pytest.fixture(scope="module")
async def admin():
    tok = await _login("admin", "admin123")
    c = _c(tok)
    yield c
    await c.aclose()


@pytest.fixture(scope="module")
async def world(admin):
    """构造：核心机房 CORE → 前端机房 F1 / F2，各含机柜+设备+端口+ODF。"""
    async def mk_room(name, code, parent=None):
        r = await admin.post(f"{API}/rooms", json={"name": name, "code": code, "parent_id": parent})
        assert r.status_code == 200, r.text
        return r.json()

    core = await mk_room("权限测试核心机房", "PRM-CORE")
    f1 = await mk_room("权限测试前端机房1", "PRM-F1", core["id"])
    f2 = await mk_room("权限测试前端机房2", "PRM-F2", core["id"])

    async def mk_rack(room_id, code):
        r = await admin.post(f"{API}/racks", json={"room_id": room_id, "name": f"{code}-架", "code": code})
        assert r.status_code == 200, r.text
        return r.json()

    async def mk_device(rack_id, name, u_position=1):
        r = await admin.post(f"{API}/devices", json={
            "rack_id": rack_id, "name": name, "template_key": "sw-24ge-4sfp",
            "u_position": u_position})
        assert r.status_code == 200, r.text
        return r.json()

    async def mk_cabinet(room_id, code):
        r = await admin.post(f"{API}/odf/cabinets", json={
            "room_id": room_id, "name": f"{code}-ODF", "code": code})
        assert r.status_code == 200, r.text
        return r.json()

    rk1 = await mk_rack(f1["id"], "PRM-R1")
    rk2 = await mk_rack(f2["id"], "PRM-R2")
    d1 = await mk_device(rk1["id"], "F1-交换机", u_position=1)
    d2 = await mk_device(rk2["id"], "F2-交换机", u_position=1)
    cab1 = await mk_cabinet(f1["id"], "PRM-ODF1")
    cab2 = await mk_cabinet(f2["id"], "PRM-ODF2")

    async def mk_tray(cab_id, name):
        r = await admin.post(f"{API}/odf/trays", json={
            "cabinet_id": cab_id, "name": name, "pos_x": 10, "pos_y": 10})
        assert r.status_code == 200, r.text
        return r.json()

    tr1 = await mk_tray(cab1["id"], "T1")
    tr2 = await mk_tray(cab2["id"], "T2")

    async def ports(dev_id):
        r = await admin.get(f"{API}/ports", params={"owner_type": "device", "owner_id": dev_id})
        return r.json()

    async def slots(tray_id):
        r = await admin.get(f"{API}/odf/slots", params={"tray_id": tray_id})
        return r.json()

    return {
        "core": core, "f1": f1, "f2": f2,
        "rk1": rk1, "rk2": rk2,
        "d1": d1, "d2": d2,
        "cab1": cab1, "cab2": cab2,
        "tr1": tr1, "tr2": tr2,
        "p1": await ports(d1["id"]), "p2": await ports(d2["id"]),
        "s1": await slots(tr1["id"]), "s2": await slots(tr2["id"]),
    }


@pytest.fixture(scope="module")
async def site1(admin, world):
    """站点管理员：仅授权 F1。"""
    r = await admin.post(f"{API}/auth/users", json={
        "username": "site_f1", "password": "site12345", "display_name": "F1 管理员",
        "role": "site_admin", "room_ids": [world["f1"]["id"]],
    })
    assert r.status_code == 200, r.text
    tok = await _login("site_f1", "site12345")
    c = _c(tok)
    yield c
    await c.aclose()


@pytest.fixture(scope="module")
async def site_core(admin, world):
    """站点管理员：授权核心机房 CORE（应可写其所有子机房 F1/F2）。"""
    r = await admin.post(f"{API}/auth/users", json={
        "username": "site_core", "password": "site12345", "display_name": "核心授权管理员",
        "role": "site_admin", "room_ids": [world["core"]["id"]],
    })
    assert r.status_code == 200, r.text
    tok = await _login("site_core", "site12345")
    c = _c(tok)
    yield c
    await c.aclose()


# ---------------- 读权限：全部可读 ----------------
@pytest.mark.asyncio
async def test_site_can_read_all(site1, world):
    for path in ("/rooms", "/racks", "/devices", "/ports", "/odf/cabinets", "/patch-cords", "/changelog"):
        r = await site1.get(f"{API}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}"


# ---------------- 机房 ----------------
@pytest.mark.asyncio
async def test_site_cannot_create_top_level_room(site1):
    r = await site1.post(f"{API}/rooms", json={"name": "越权核心机房", "code": "PRM-EVIL-CORE"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_modify_other_room(site1, world):
    r = await site1.put(f"{API}/rooms/{world['f2']['id']}", json={
        "name": "被篡改", "code": "PRM-F2", "parent_id": world["core"]["id"]})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_delete_other_room(site1, world):
    r = await site1.delete(f"{API}/rooms/{world['f2']['id']}")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_can_create_sub_room_in_scope(site1, world):
    r = await site1.post(f"{API}/rooms", json={
        "name": "F1 子机房", "code": "PRM-F1-SUB", "parent_id": world["f1"]["id"]})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_site_cannot_reparent_to_other_room(site1, world):
    """把自己的机房挂到别人机房下 = 越权。"""
    r = await site1.put(f"{API}/rooms/{world['f1']['id']}", json={
        "name": "权限测试前端机房1", "code": "PRM-F1", "parent_id": world["f2"]["id"]})
    assert r.status_code == 403, r.text


# ---------------- 机柜 ----------------
@pytest.mark.asyncio
async def test_site_cannot_create_rack_in_other_room(site1, world):
    r = await site1.post(f"{API}/racks", json={
        "room_id": world["f2"]["id"], "name": "越权机柜", "code": "PRM-EVIL-R"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_can_create_rack_in_scope(site1, world):
    r = await site1.post(f"{API}/racks", json={
        "room_id": world["f1"]["id"], "name": "F1 新机柜", "code": "PRM-R1-B"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_site_cannot_update_or_delete_other_rack(site1, world):
    r = await site1.put(f"{API}/racks/{world['rk2']['id']}", json={
        "room_id": world["f2"]["id"], "name": "篡改", "code": "PRM-R2"})
    assert r.status_code == 403
    r = await site1.delete(f"{API}/racks/{world['rk2']['id']}")
    assert r.status_code == 403


# ---------------- 设备 / 端口 ----------------
@pytest.mark.asyncio
async def test_site_cannot_create_device_in_other_rack(site1, world):
    r = await site1.post(f"{API}/devices", json={
        "rack_id": world["rk2"]["id"], "name": "越权设备", "template_key": "sw-8ge-2sfp"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_can_create_device_in_scope(site1, world):
    r = await site1.post(f"{API}/devices", json={
        "rack_id": world["rk1"]["id"], "name": "F1 新设备", "template_key": "sw-8ge-2sfp",
        "u_position": 3})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_site_cannot_update_other_device(site1, world):
    r = await site1.put(f"{API}/devices/{world['d2']['id']}", json={"name": "篡改设备"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_delete_other_device(site1, world):
    r = await site1.delete(f"{API}/devices/{world['d2']['id']}")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_add_port_to_other_device(site1, world):
    r = await site1.post(f"{API}/devices/{world['d2']['id']}/ports", json={
        "port_no": "EVIL/1", "port_type": "rj45"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_update_other_port(site1, world):
    p = world["p2"][0]
    r = await site1.put(f"{API}/ports/{p['id']}", json={
        "port_no": p["port_no"], "port_type": p["port_type"], "status": "fault"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_delete_other_port(site1, world):
    p = world["p2"][0]
    r = await site1.delete(f"{API}/ports/{p['id']}")
    assert r.status_code == 403, r.text


# ---------------- ODF ----------------
@pytest.mark.asyncio
async def test_site_cannot_create_cabinet_in_other_room(site1, world):
    r = await site1.post(f"{API}/odf/cabinets", json={
        "room_id": world["f2"]["id"], "name": "越权ODF", "code": "PRM-EVIL-ODF"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_update_or_delete_other_cabinet(site1, world):
    r = await site1.put(f"{API}/odf/cabinets/{world['cab2']['id']}", json={"name": "篡改"})
    assert r.status_code == 403
    r = await site1.delete(f"{API}/odf/cabinets/{world['cab2']['id']}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_site_cannot_create_unit_in_other_cabinet(site1, world):
    r = await site1.post(f"{API}/odf/units", json={
        "cabinet_id": world["cab2"]["id"], "name": "Z", "tray_count": 1})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_create_tray_in_other_cabinet(site1, world):
    r = await site1.post(f"{API}/odf/trays", json={
        "cabinet_id": world["cab2"]["id"], "name": "EVIL", "pos_x": 1, "pos_y": 1})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_update_or_delete_other_tray(site1, world):
    r = await site1.put(f"{API}/odf/trays/{world['tr2']['id']}", json={"name": "篡改"})
    assert r.status_code == 403
    r = await site1.delete(f"{API}/odf/trays/{world['tr2']['id']}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_site_cannot_group_other_cabinet_trays(site1, world):
    r = await site1.post(f"{API}/odf/trays/group", json={
        "cabinet_id": world["cab2"]["id"], "tray_ids": [world["tr2"]["id"]], "name": "EVIL"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_can_create_tray_in_scope(site1, world):
    r = await site1.post(f"{API}/odf/trays", json={
        "cabinet_id": world["cab1"]["id"], "name": "F1-T2", "pos_x": 20, "pos_y": 20})
    assert r.status_code == 200, r.text


# ---------------- 连接 ----------------
@pytest.mark.asyncio
async def test_site_cannot_wire_within_other_room(site1, world):
    a, b = world["p2"][0], world["p2"][1]
    r = await site1.post(f"{API}/patch-cords", json={"port_a_id": a["id"], "port_b_id": b["id"]})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_wire_across_rooms(site1, world):
    """跨机房跳纤仅核心管理员：即使一端在自己机房也拒绝。"""
    a = world["p1"][0]
    b = world["p2"][0]
    r = await site1.post(f"{API}/patch-cords", json={"port_a_id": a["id"], "port_b_id": b["id"]})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_can_wire_within_scope(site1, world):
    # 用光口（SFP+）连 ODF 孔位（LC/UPC），同属光介质；force 跳过子类型警告
    a = next(p for p in world["p1"] if p["port_no"].startswith("XGE"))
    slot_port = world["s1"][0]["port"]
    r = await site1.post(f"{API}/patch-cords", json={"port_a_id": a["id"], "port_b_id": slot_port["id"],
                                                     "force": True})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_site_cannot_interconnect_other_room(site1, world):
    r = await site1.post(f"{API}/interconnects", json={
        "slot_a_id": world["s2"][0]["id"], "slot_b_id": world["s2"][1]["id"], "kind": "adapter"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_create_cable_in_other_room(site1, world):
    r = await site1.post(f"{API}/cables", json={
        "room_id": world["f2"]["id"], "name": "越权光缆", "core_count": 12})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_land_or_splice_other_cable(site1, admin, world):
    r = await admin.post(f"{API}/cables", json={
        "room_id": world["f2"]["id"], "name": "F2 光缆", "core_count": 12})
    cable = r.json()
    r = await admin.get(f"{API}/cores", params={"cable_id": cable["id"]})
    core = r.json()[0]
    r = await site1.put(f"{API}/cores/{core['id']}/land", json={"port_id": None})
    assert r.status_code == 403, r.text
    r = await site1.put(f"{API}/cores/{core['id']}/status", json={"status": "fault"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_create_link_across_rooms(site1, world):
    r = await site1.post(f"{API}/links", json={
        "name": "越权链路", "a_port_id": world["p1"][0]["id"], "z_port_id": world["p2"][0]["id"]})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_cannot_write_other_canvas(site1, world):
    r = await site1.put(f"{API}/canvas/{world['f2']['id']}", json={"data_json": {"nodes": []}})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_site_can_write_own_canvas(site1, world):
    r = await site1.put(f"{API}/canvas/{world['f1']['id']}", json={"data_json": {"nodes": []}})
    assert r.status_code == 200, r.text


# ---------------- 用户管理 ----------------
@pytest.mark.asyncio
async def test_site_cannot_manage_users(site1):
    r = await site1.get(f"{API}/auth/users")
    assert r.status_code == 403, r.text
    r = await site1.post(f"{API}/auth/users", json={
        "username": "evil", "password": "x1234567", "role": "core_admin"})
    assert r.status_code == 403, r.text


# ---------------- 作用域继承：授权核心机房 → 可写全部子机房 ----------------
@pytest.mark.asyncio
async def test_core_grant_inherits_children(site_core, world):
    r = await site_core.post(f"{API}/racks", json={
        "room_id": world["f2"]["id"], "name": "继承可写", "code": "PRM-R2-B"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_core_grant_can_wire_across_own_children(site_core, world):
    """同属一个核心机房的两个前端机房之间建跳纤，应被允许。"""
    a = world["p1"][1]
    b = world["p2"][1]
    r = await site_core.post(f"{API}/patch-cords", json={"port_a_id": a["id"], "port_b_id": b["id"],
                                                          "force": True})
    assert r.status_code == 200, r.text
