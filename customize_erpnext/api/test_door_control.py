"""Hồi quy /door_control — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/api/test_door_control.py').read())"

🔴 Chỉ được kết nối máy TEST 10.0.1.50 (user cho phép 08/10/2026) — máy này sẽ
kêu "tách" 2 lần (unlock_door + unlock_all). Máy cửa giả 192.0.2.1 là địa chỉ
TEST-NET (RFC 5737), không tồn tại, dùng để thử nhánh mất kết nối.

Không ghi vào Attendance Machine Setting: bảng máy được dựng trong bộ nhớ và
`attendance_machines._get_settings` bị thay tạm. Kết thúc bằng rollback + xoá các
cache key mà test đã đặt (nếu không, "records" cache làm lần Lấy log thật kế tiếp
tưởng máy không có log mới trong khi các dòng đã bị rollback).
"""

import frappe

import customize_erpnext.api.attendance_machines as am
import customize_erpnext.api.door_control as dc

TEST_IP = "10.0.1.50"
FAKE_IP = "192.0.2.1"

frappe.set_user("Administrator")
ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    except Exception as e:  # wrong exception type
        print(f"        (raised {type(e).__name__}: {e})")
        return False
    return False


# ── dựng Setting trong bộ nhớ ────────────────────────────────────────────────
settings = frappe.get_doc("Attendance Machine Setting")
test_row = next((r for r in settings.machines if r.ip_address == TEST_IP), None)
assert test_row, f"{TEST_IP} không có trong Attendance Machine Setting"
TEST_NAME = test_row.device_name
test_row.enable = 1
test_row.is_door_control = 1
test_row.unlock_seconds = 3
test_row.sensor_type = "NO"   # LB-35
test_row.allow_hold_close = 0
fake = settings.append("machines", {
    "device_name": "ZZ Test Fake Door", "ip_address": FAKE_IP, "enable": 1,
    "is_door_control": 1, "unlock_seconds": 5,
})
# 🔴 every OTHER door controller is switched off in memory: the test must reach 10.0.1.50 only
for r in settings.machines:
    if r is not test_row and r is not fake and r.is_door_control:
        r.enable = 0
attendance_count = sum(1 for r in settings.machines if r.enable and not r.is_door_control)

_orig_get_settings = am._get_settings
am._get_settings = lambda: settings
touched_keys = [dc._key(k, n) for k in ("probe", "open", "records") for n in (TEST_NAME, fake.device_name)]

try:
    print("1. get_machines / get_machine — tách khỏi chấm công")
    names = {m["device_name"] for m in am.get_machines(enabled_only=True)}
    check("mặc định loại máy cửa", TEST_NAME not in names and fake.device_name not in names)
    check("số máy chấm công không đổi", len(names) == attendance_count, f"({len(names)})")
    with_door = {m["device_name"] for m in am.get_machines(enabled_only=True, include_door=True)}
    check("include_door có cả 2 máy cửa", {TEST_NAME, fake.device_name} <= with_door)
    door_only = {m["device_name"] for m in am.get_machines(enabled_only=True, door_only=True)}
    check("door_only chỉ máy cửa", door_only == {TEST_NAME, fake.device_name}, str(door_only))
    check("get_machine từ chối máy cửa", raises(lambda: am.get_machine(TEST_NAME), frappe.ValidationError))
    check("get_machine(allow_door) trả máy cửa", am.get_machine(TEST_NAME, allow_door=True)["is_door_control"])
    from customize_erpnext.api.biometric_sync import _get_machine_doc
    check("resync/reboot (_get_machine_doc) từ chối máy cửa",
          raises(lambda: _get_machine_doc(TEST_NAME), frappe.ValidationError))

    print("2. Validate Setting")
    test_row.master_device = 1
    check("máy cửa không được là master", raises(settings._validate_door_controllers, frappe.ValidationError))
    test_row.master_device = 0
    test_row.unlock_seconds = 0
    check("unlock_seconds = 0 bị chặn", raises(settings._validate_door_controllers, frappe.ValidationError))
    test_row.unlock_seconds = 3
    check("cấu hình hợp lệ qua được", not raises(settings._validate_door_controllers))

    print("3. Quyền")
    outsider = frappe.db.sql(
        """select u.name from tabUser u where u.enabled=1 and u.user_type='System User'
        and u.name not in ('Administrator','Guest')
        and not exists (select 1 from `tabHas Role` h where h.parent=u.name and h.role in ('Door Control','System Manager'))
        limit 1""")[0][0]
    frappe.set_user(outsider)
    check("get_doors chặn người không có role", raises(dc.get_doors, frappe.PermissionError), outsider)
    check("unlock_door chặn người không có role", raises(lambda: dc.unlock_door(TEST_NAME), frappe.PermissionError))
    check("đẩy vân tay lên máy cửa bị chặn",
          raises(lambda: am.check_door_machine_access(am.get_machine(TEST_NAME, allow_door=True)), frappe.PermissionError))
    check("đẩy vân tay lên máy chấm công không bị chặn",
          not raises(lambda: am.check_door_machine_access({"is_door_control": False})))
    frappe.set_user("Administrator")

    print("4. get_doors — trạng thái")
    r = dc.get_doors(force=1)
    doors = {d["device_name"]: d for d in r["doors"]}
    check("chỉ trả 2 máy cửa", set(doors) == {TEST_NAME, fake.device_name}, str(list(doors)))
    check(f"{TEST_IP} online", doors[TEST_NAME]["online"], f"{doors[TEST_NAME].get('response_ms')}ms")
    check("đọc được byte cảm biến", doors[TEST_NAME]["sensor_raw"] is not None, str(doors[TEST_NAME]["sensor_raw"]))
    d50 = doors[TEST_NAME]
    check("đọc Door Sensor Mode của máy", d50["device_sensor_mode"] in ("None", "NO", "NC"), str(d50["device_sensor_mode"]))
    dev_mode = d50["device_sensor_mode"]
    test_row.sensor_type = "NC" if dev_mode != "NC" else "NO"     # deliberately different
    d50m = {d["device_name"]: d for d in dc.get_doors(force=1)["doors"]}[TEST_NAME]
    check("Sensor Type ≠ Door Sensor Mode của máy → báo lệch, bỏ giá trị sensor",
          dev_mode == "None" or (d50m["sensor_mode_mismatch"] and d50m["sensor"] is None),
          f'máy={dev_mode} setting={test_row.sensor_type} mismatch={d50m["sensor_mode_mismatch"]}')
    if dev_mode in ("NO", "NC"):
        test_row.sensor_type = dev_mode
        d50b = {d["device_name"]: d for d in dc.get_doors(force=1)["doors"]}[TEST_NAME]
        check("Sensor Type khớp máy → không lệch, có trạng thái chốt",
              not d50b["sensor_mode_mismatch"] and d50b["sensor"] in ("locked", "unlocked"), f'sensor={d50b["sensor"]}')
    test_row.sensor_type = "None"
    d50c = {d["device_name"]: d for d in dc.get_doors(force=1)["doors"]}[TEST_NAME]
    check("Sensor Type None → không đọc sensor", d50c["sensor_raw"] is None and not d50c["has_door_sensor"])
    test_row.sensor_type = "NO"
    check("máy giả offline", not doors[fake.device_name]["online"], (doors[fake.device_name].get("error") or "")[:60])
    check("không trả comm key/password", "password" not in doors[TEST_NAME])

    print("5. unlock_door (máy test kêu tách lần 1)")
    before = frappe.db.count("Door Control Action")
    r = dc.unlock_door(TEST_NAME)
    check("mở thành công", r["success"], str(r.get("message") or ""))
    check("trạng thái ERP: đang mở ~3s", 1 <= r["door"]["open_remaining"] <= 3, str(r["door"]["open_remaining"]))
    act = frappe.get_all("Door Control Action", fields=["action", "result", "user", "seconds"],
                         order_by="creation desc", limit=1)[0]
    check("ghi Door Control Action", frappe.db.count("Door Control Action") == before + 1 and act.action == "Unlock"
          and act.result == "Success" and act.user == "Administrator" and act.seconds == 3, str(act))

    r = dc.unlock_door(fake.device_name)
    check("mở máy offline: trả lỗi, không throw", not r["success"])
    act = frappe.get_all("Door Control Action", fields=["result", "error"], order_by="creation desc", limit=1)[0]
    check("lệnh lỗi vẫn được ghi Failed", act.result == "Failed" and act.error, (act.error or "")[:60])

    print("6. Giữ mở / Đóng bị chặn khi allow_hold_close = 0")
    check("hold_open bị chặn", raises(lambda: dc.hold_open(TEST_NAME), frappe.ValidationError))
    check("close_door bị chặn", raises(lambda: dc.close_door(TEST_NAME), frappe.ValidationError))
    test_row.allow_hold_close = 1
    check("HOLD_CLOSE_ENABLED=False: chặn cả khi máy cho phép",
          dc.HOLD_CLOSE_ENABLED or raises(lambda: dc.hold_open(TEST_NAME), frappe.ValidationError))
    check("payload báo nút đang tắt", dc.get_doors()["doors"][0]["hold_close_enabled"] == dc.HOLD_CLOSE_ENABLED)
    test_row.allow_hold_close = 0

    print("7. unlock_all (máy test kêu tách lần 2)")
    r = dc.unlock_all()
    res = {x["device_name"]: x["success"] for x in r["results"]}
    check("máy test mở, máy giả lỗi", res == {TEST_NAME: True, fake.device_name: False}, str(res))
    n_all = frappe.db.count("Door Control Action", {"action": "Unlock All", "creation": [">=", frappe.utils.add_to_date(None, minutes=-1)]})
    check("ghi 1 dòng Unlock All mỗi cửa", n_all == 2, str(n_all))

    print("8. fetch_logs + get_timeline")
    for k in touched_keys:
        if ":records:" in k:
            frappe.cache.delete_value(k)
    r = dc.fetch_logs(TEST_NAME)
    first = r["results"][0]
    check("đọc log máy test", first["success"], str(first))
    r2 = dc.fetch_logs(TEST_NAME)
    check("lần 2 không tải lại khi số log không đổi", r2["results"][0].get("unchanged"), str(r2["results"][0]))
    r3 = dc.fetch_logs(TEST_NAME, force=1)
    check("force: tải lại nhưng không chèn trùng", r3["results"][0]["inserted"] == 0, str(r3["results"][0]))
    tl = dc.get_timeline()["events"]
    kinds = {e["kind"] for e in tl}
    check("timeline có lệnh ERP + lệnh lỗi", {"erp", "failed"} <= kinds, str(kinds))
    check("timeline sắp mới nhất trước", all(tl[i]["timestamp"] >= tl[i + 1]["timestamp"] for i in range(len(tl) - 1)))
    only = dc.get_timeline(device_name=fake.device_name)["events"]
    check("lọc theo cửa", only and all(e["device_name"] == fake.device_name for e in only), str(len(only)))

    print("9. Trang /door_control: chuỗi dịch")
    import importlib
    page = importlib.import_module("customize_erpnext.www.door_control.index")
    strings = page._page_strings()
    check("gom được chuỗi __() từ template", len(strings) > 50, str(len(strings)))
    frappe.local.lang = "vi"
    missing = [s for s in strings if frappe._(s) == s and s not in ("ID {0}",)]
    check("mọi chuỗi đều có bản dịch vi", not missing, str(missing[:5]))
finally:
    am._get_settings = _orig_get_settings
    frappe.set_user("Administrator")
    frappe.db.rollback()
    for k in touched_keys:
        frappe.cache.delete_value(k)
    print(f"\n{ok} PASS / {fail} FAIL  (đã rollback + xoá cache test)")
