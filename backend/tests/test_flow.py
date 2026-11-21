"""端到端集成测试：资源→ODF→跳纤→盘间→纤芯→链路 trace→审计。"""
import pytest

API = "/fiber/api/v1"


@pytest.fixture(scope="module")
async def room(auth_client):
    r = await auth_client.post(f"{API}/rooms", json={"name": "核心机房", "code": "CR-01"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
async def rack(auth_client, room):
    r = await auth_client.post(f"{API}/racks", json={"room_id": room["id"], "name": "01架", "code": "R01"})
    return r.json()


async def _device(auth_client, rack, name, dtype="sw", u_position=1):
    r = await auth_client.post(f"{API}/devices", json={
        "rack_id": rack["id"], "name": name, "device_type": dtype, "u_position": u_position})
    assert r.status_code == 200, r.text
    return r.json()


async def _ports(auth_client, device_id):
    r = await auth_client.get(f"{API}/ports", params={"owner_type": "device", "owner_id": device_id})
    return {p["port_no"]: p for p in r.json()}


async def _odf_tray(auth_client, room, unit_name="A", tray_name="1", rows=1, spr=12):
    r = await auth_client.post(f"{API}/odf/cabinets", json={"room_id": room["id"], "name": "ODF-1", "code": "ODF01"})
    cab = r.json()
    r = await auth_client.post(f"{API}/odf/units", json={"cabinet_id": cab["id"], "name": unit_name, "seq": 1})
    unit = r.json()
    r = await auth_client.post(f"{API}/odf/trays",
                               json={"unit_id": unit["id"], "name": tray_name, "rows": rows, "slots_per_row": spr})
    assert r.status_code == 200, r.text
    return r.json()


async def _slots(auth_client, tray_id):
    r = await auth_client.get(f"{API}/odf/slots", params={"tray_id": tray_id})
    return {s["label"]: s for s in r.json()}


@pytest.mark.asyncio
async def test_full_flow(auth_client, rack):
    # 1. 设备与模板端口（U 位互不重叠）
    agg = await _device(auth_client, rack, "汇聚交换机", "sw", u_position=1)
    olt = await _device(auth_client, rack, "OLT", "olt", u_position=5)
    p_agg = await _ports(auth_client, agg["id"])
    p_olt = await _ports(auth_client, olt["id"])
    assert "XGE0/1/1" in p_agg and "GPON0/1" in p_olt

    # 2. ODF 盘（1x12）编址 A1..A12
    tray = await _odf_tray(auth_client, rack)
    slots = await _slots(auth_client, tray["id"])
    assert set(slots) == {f"A{i}" for i in range(1, 13)}

    # 3. 跳纤：agg XGE0/1/1 → ODF A1；olt GPON0/1 → ODF A12（SFP+/PON 与 LC/UPC 同属光，需 force）
    r = await auth_client.post(f"{API}/patch-cords", json={
        "port_a_id": p_agg["XGE0/1/1"]["id"], "port_b_id": slots["A1"]["port"]["id"],
        "force": True})
    assert r.status_code == 200, r.text
    r = await auth_client.post(f"{API}/patch-cords", json={
        "port_a_id": p_olt["GPON0/1"]["id"], "port_b_id": slots["A12"]["port"]["id"],
        "force": True})
    assert r.status_code == 200, r.text

    # 一端口一跳纤：重复应 409
    r = await auth_client.post(f"{API}/patch-cords", json={
        "port_a_id": p_agg["XGE0/1/1"]["id"], "port_b_id": slots["A2"]["port"]["id"]})
    assert r.status_code == 409

    # 4. 盘间连接 A1↔A2 法兰直通（跳纤占用的孔位仍可做盘间连接：业务上法兰/熔接与跳纤共存于孔位）
    r = await auth_client.post(f"{API}/interconnects",
                               json={"slot_a_id": slots["A1"]["id"], "slot_b_id": slots["A2"]["id"], "kind": "adapter"})
    assert r.status_code == 200, r.text
    ic_id = r.json()["id"]
    # 重复盘间连接应 409
    r = await auth_client.post(f"{API}/interconnects",
                               json={"slot_a_id": slots["A2"]["id"], "slot_b_id": slots["A3"]["id"], "kind": "splice"})
    assert r.status_code == 409

    # 5. 端到端 trace：XGE0/1/1 →(跳纤) A1 →(法兰) A2 →(跳纤) XGE0/1/2
    r = await auth_client.post(f"{API}/patch-cords", json={
        "port_a_id": p_agg["XGE0/1/2"]["id"], "port_b_id": slots["A2"]["port"]["id"],
        "force": True})
    assert r.status_code == 200, r.text
    r = await auth_client.get(f"{API}/links/trace",
                              params={"from_port": p_agg["XGE0/1/1"]["id"], "to_port": p_agg["XGE0/1/2"]["id"]})
    assert r.status_code == 200, r.text
    hops = r.json()["hops"]
    assert len(hops) == 3  # 跳纤+法兰+跳纤

    # 6. 光缆：48 芯只成端 24 芯 + 余纤与第二根缆芯对芯熔接
    r = await auth_client.post(f"{API}/cables", json={"room_id": rack["room_id"], "name": "进局光缆1", "core_count": 48})
    cable1 = r.json()
    r = await auth_client.post(f"{API}/cables", json={"room_id": rack["room_id"], "name": "对接光缆2", "core_count": 24})
    cable2 = r.json()
    r = await auth_client.get(f"{API}/cores", params={"cable_id": cable1["id"]})
    cores1 = {c["core_no"]: c for c in r.json()}
    r = await auth_client.get(f"{API}/cores", params={"cable_id": cable2["id"]})
    cores2 = {c["core_no"]: c for c in r.json()}
    assert len(cores1) == 48 and len(cores2) == 24

    # 24 芯成端到 ODF A4..A27？盘只有 12 孔，成端到 A4..A11（8芯演示）+ 芯1↔芯2'(对接熔接)
    r = await auth_client.put(f"{API}/cores/{cores1[1]['id']}/land", json={"port_id": slots["A4"]["port"]["id"]})
    assert r.status_code == 200, r.text
    r = await auth_client.put(f"{API}/cores/{cores1[1]['id']}/splice", json={"peer_core_id": cores2[1]["id"]})
    assert r.status_code == 200, r.text
    r = await auth_client.get(f"{API}/cores", params={"cable_id": cable1["id"]})
    c1 = {c["core_no"]: c for c in r.json()}
    assert c1[1]["status"] == "spliced" and c1[1]["peer_core"]["id"] == cores2[1]["id"]
    # 已熔接芯再被他人熔接 → 409
    r = await auth_client.put(f"{API}/cores/{cores2[2]['id']}/splice", json={"peer_core_id": cores1[1]["id"]})
    assert r.status_code == 409

    # 7. 审计可查
    r = await auth_client.get(f"{API}/changelog", params={"limit": 50})
    assert r.status_code == 200
    logs = r.json()
    actions = {(l["entity_type"], l["action"]) for l in logs}
    assert ("room", "create") in actions and ("patch_cord", "create") in actions
    assert any(l["before"] or l["after"] for l in logs)

    # 8. 拆除跳纤释放端口
    r = await auth_client.get(f"{API}/patch-cords")
    cords = r.json()
    target = next(c for c in cords if c["port_a_id"] == p_agg["XGE0/1/1"]["id"])
    r = await auth_client.delete(f"{API}/patch-cords/{target['id']}")
    assert r.status_code == 200
    r = await auth_client.get(f"{API}/ports", params={"owner_type": "device", "owner_id": agg["id"]})
    ports = {p["port_no"]: p for p in r.json()}
    assert ports["XGE0/1/1"]["status"] == "free"


@pytest.mark.asyncio
async def test_trace_unreachable(auth_client, rack):
    dev = await _device(auth_client, rack, "孤立收发器", "media_conv", u_position=20)
    ports = await _ports(auth_client, dev["id"])
    r = await auth_client.get(f"{API}/links/trace",
                              params={"from_port": ports["ETH/1"]["id"], "to_port": ports["OPT/1"]["id"]})
    assert r.status_code == 404
