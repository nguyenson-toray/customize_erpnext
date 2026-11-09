"""Hồi quy cảm biến cửa ESP32 (network/door/sensor.py) — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/network/door/test_sensor.py').read())"

KHÔNG kết nối máy cửa nào (probe / _run bị thay), KHÔNG gửi Telegram thật
(`requests.post` bị mock). User + Door Sensor + Door Sensor Event của test đều
rollback ở cuối; khoá alert_state của test được xoá.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import get_datetime, now_datetime

import customize_erpnext.network.door.alerts as da
import customize_erpnext.network.door.control as dc
import customize_erpnext.network.door.sensor as ds

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
    except Exception as e:
        print(f"        (raised {type(e).__name__}: {e})")
        return False
    return False


ON, OFF, NEW, LOST = "ZZ-TEST-ON", "ZZ-TEST-OFF", "ZZ-TEST-NEW", "ZZ-TEST-LOST"
BOARD = "zz-door-sensor-test@example.invalid"
STATE_KEYS = [f"door_alerts:{k}:{n}" for k in ("sensor_offline", "sensor_open") for n in (ON, OFF, NEW, LOST)]


def sensor_row(name):
    return frappe.db.get_value("Door Sensor", name, ["last_state", "last_state_change", "last_seen", "sensor_ip",
                                                     "sensor_rssi", "sensor_fw", "modified", "enabled"], as_dict=True)


def events(name):
    return frappe.get_all("Door Sensor Event", filters={"door_sensor": name},
                          fields=["state", "previous_state", "event", "event_time"], order_by="creation asc")


def post(**kw):
    body = {"door_id": ON, "state": "closed", "event": "heartbeat", "age_ms": 0, "rssi": -61, "ip": "192.0.2.80", "fw": "1.0.0"}
    body.update(kw)
    return ds.report(**body)


_orig_log_error = frappe.log_error
logged = []
frappe.log_error = lambda *a, **k: logged.append(k.get("message") or (a[0] if a else ""))
tg = patch("requests.post", return_value=MagicMock(content=b"x", status_code=200, json=lambda: {"ok": True}))
tg_post = tg.start()

try:
    frappe.set_user("Administrator")
    check("role Door Sensor tồn tại, không vào desk", frappe.db.get_value("Role", "Door Sensor", "desk_access") == 0)
    for name, enabled in ((ON, 1), (OFF, 0), (LOST, 1)):
        frappe.get_doc({"doctype": "Door Sensor", "sensor_id": name, "location": f"Test {name[-3:]}",
                        "enabled": enabled}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "User", "email": BOARD, "first_name": "ZZ Door Sensor", "send_welcome_email": 0,
                    "roles": [{"role": "Door Sensor"}]}).insert(ignore_permissions=True)
    check("user chỉ có role Door Sensor = Website User", frappe.db.get_value("User", BOARD, "user_type") == "Website User")

    # ── 1. quyền ────────────────────────────────────────────────────────────
    print("1. quyền")
    door_control_user = frappe.db.sql(
        """select hr.parent from `tabHas Role` hr join tabUser u on u.name = hr.parent
        where hr.role = 'Door Control' and u.enabled = 1 and hr.parent not in
        (select parent from `tabHas Role` where role in ('System Manager','Door Sensor')) limit 1""")
    if door_control_user:
        frappe.set_user(door_control_user[0][0])
        check("user Door Control KHÔNG gọi được report", raises(post, frappe.PermissionError))
    frappe.set_user("Guest")
    check("Guest KHÔNG gọi được report", raises(post, frappe.PermissionError))
    frappe.set_user(BOARD)
    check("user Door Sensor KHÔNG vào được /door_control API", raises(dc.get_doors, frappe.PermissionError))

    # ── 2. report ───────────────────────────────────────────────────────────
    print("2. report")
    modified0 = sensor_row(ON).modified
    r = post(event="boot", state="closed")
    check("boot closed (unknown -> closed): changed", r == {"ok": True, "changed": True}, str(r))
    ev = events(ON)
    check("1 Event boot, previous unknown", len(ev) == 1 and ev[0].event == "boot" and ev[0].previous_state == "unknown")
    r = post(state="closed")
    check("heartbeat cùng trạng thái: changed false", r == {"ok": True, "changed": False}, str(r))
    check("heartbeat KHÔNG tạo Event", len(events(ON)) == 1)
    row = sensor_row(ON)
    check("diag cập nhật (ip / rssi / fw / last_seen)", row.sensor_ip == "192.0.2.80" and row.sensor_rssi == -61
          and row.sensor_fw == "1.0.0" and now_datetime() - get_datetime(row.last_seen) < timedelta(seconds=10))
    check("modified KHÔNG đổi (update_modified=False)", row.modified == modified0)
    check("không sinh Version", not frappe.db.exists("Version", {"ref_doctype": "Door Sensor", "docname": ON}))

    before = now_datetime()
    r = post(state="open", event="change", age_ms=5000)
    row = sensor_row(ON)
    lag = (before - get_datetime(row.last_state_change)).total_seconds()
    check("change open: changed + last_state", r["changed"] and row.last_state == "open")
    check("last_state_change = lúc nhận − age_ms (≈5 s)", 4 <= lag <= 6, f"{lag:.2f}s")
    r = post(state="open", event="change", age_ms=1000)
    check("gửi lại trùng (retry) -> 200 ok, changed false", r == {"ok": True, "changed": False})
    r = post(state="closed", event="change", age_ms=25 * 3600 * 1000)
    lag = (now_datetime() - get_datetime(sensor_row(ON).last_state_change)).total_seconds()
    check("age_ms > 24 h coi như 0", r["changed"] and lag < 5, f"{lag:.2f}s")
    r = post(state="closed", event="change", age_ms=-50)
    check("age_ms âm coi như 0, không lỗi", r == {"ok": True, "changed": False})
    check("state sai -> lỗi", raises(lambda: post(state="ajar"), frappe.ValidationError))
    check("event sai -> lỗi", raises(lambda: post(event="ping"), frappe.ValidationError))
    check("door_id sai ký tự -> lỗi", raises(lambda: post(door_id="KHO 01"), frappe.ValidationError))
    check("door_id > 32 ký tự -> lỗi", raises(lambda: post(door_id="X" * 33), frappe.ValidationError))
    check("age_ms không phải số -> lỗi", raises(lambda: post(age_ms="abc"), frappe.ValidationError))
    check("trường lạ từ firmware mới không làm lỗi", post(state="closed", extra_field=1)["ok"])
    r = post(state="fault", event="change")
    check("fault ghi Event", r["changed"] and events(ON)[-1].state == "fault")
    post(state="closed", event="change")

    # disabled / unknown
    r = post(door_id=OFF, state="open", event="change")
    check("sensor tắt -> 200, ok false", r["ok"] is False and r["reason"] == "disabled", str(r))
    check("sensor tắt: KHÔNG Event, chỉ cập nhật last_seen",
          not events(OFF) and sensor_row(OFF).last_seen and sensor_row(OFF).last_state == "unknown")
    logged.clear()
    r = post(door_id=NEW, state="open", event="boot", ip="192.0.2.81")
    row = sensor_row(NEW)
    check("door_id lạ -> 200 ok false + tạo Door Sensor TẮT", r["ok"] is False and row and row.enabled == 0, str(r))
    check("door_id lạ -> ghi Error Log 1 lần", len(logged) == 1 and NEW in logged[0])
    post(door_id=NEW, state="open")
    check("lần sau KHÔNG ghi log nữa", len(logged) == 1)
    frappe.set_user("Administrator")
    with patch("customize_erpnext.network.biometric.machines.get_machines", lambda **k: [{"device_name": "ZZ-MACHINE"}]):
        check("Sensor ID trùng Device Name máy (không phân biệt hoa thường) bị chặn", raises(
            lambda: frappe.get_doc({"doctype": "Door Sensor", "sensor_id": "zz-machine"}).insert(ignore_permissions=True),
            frappe.ValidationError))
    frappe.set_user(BOARD)
    check("report KHÔNG gọi Telegram", not tg_post.called)

    # ── 3. /door_control ────────────────────────────────────────────────────
    print("3. /door_control")
    post(state="open", event="change")
    frappe.set_user("Administrator")
    with patch.object(dc, "_probe_all", lambda doors, force=False: {}):
        payload = dc.get_doors()["doors"]
    by = {d["device_name"]: d for d in payload}
    check("cửa F21 có kind lock", all(d["kind"] == "lock" for d in payload if d["device_name"] not in (ON, LOST)))
    s = by.get(ON) or {}
    check("cảm biến bật có trong get_doors, kind sensor", s.get("kind") == "sensor")
    check("payload: open, online, can_unlock false", s.get("sensor") == "open" and s.get("online") and s.get("can_unlock") is False)
    check("Administrator thấy IP cảm biến", s.get("ip_address") == "192.0.2.80")
    check("cảm biến tắt KHÔNG có trong get_doors", OFF not in by and NEW not in by)
    check("cảm biến chưa từng báo = offline", by.get(LOST, {}).get("online") is False)
    tl = dc.get_timeline()["events"]
    check("timeline có sự kiện kind sensor", any(e["kind"] == "sensor" and e["device_name"] == ON for e in tl))
    check("timeline lọc theo cảm biến", {e["device_name"] for e in dc.get_timeline(device_name=ON)["events"]} == {ON})
    sent = []
    with patch.object(dc, "_run", lambda cfg, action: sent.append(cfg["ip"])), \
         patch.object(dc, "_set_open", lambda *a, **k: None):
        r = dc.unlock_all()
    names = [x["device_name"] for x in r["results"]] + r["skipped"]
    check("unlock_all không đụng cảm biến", ON not in names and LOST not in names and len(sent) == len(r["results"]))

    # ── 4. cảnh báo ────────────────────────────────────────────────────────
    print("4. cảnh báo")
    frappe.set_user(BOARD)

    def hm(dt):
        return dt.strftime("%H:%M:%S")

    def settings_for(now, after_hours=True):
        st = frappe.new_doc("Door Alert Setting")
        st.enabled, st.bot_token = 1, "123456:TEST-TOKEN"
        st.append("recipients", {"label": "Door", "chat_id": "-1", "enabled": 1, "door_alerts": 1, "device_alerts": 0})
        st.append("recipients", {"label": "Device", "chat_id": "-2", "enabled": 1, "door_alerts": 0, "device_alerts": 1})
        if after_hours:
            st.work_start_time, st.work_end_time = hm(now + timedelta(hours=1)), hm(now + timedelta(hours=2))
        else:
            st.work_start_time, st.work_end_time = hm(now - timedelta(hours=1)), hm(now + timedelta(hours=1))
        st.erp_open_alert = st.fingerprint_alert = "Off"
        st.sensor_open_alert = "After Hours"
        st.alert_sensor_fault = st.alert_device_offline = st.alert_not_locked_after_hours = 1
        st.use_lock_sensor = 0
        st.offline_after_minutes, st.not_locked_repeat_minutes, st.check_interval_minutes = 5, 30, 1
        return st

    real_set_status = da._set_status

    def run(st, now, since):
        """One run_checks pass at `now` over the rows created after `since` (real clock)."""
        st.last_check_at = since

        def set_status(**values):
            if "alert_state" in values:
                real_set_status(alert_state=values.pop("alert_state"))
            for k, v in values.items():
                st.set(k, v)
        tg_post.reset_mock()
        with patch.object(da, "_settings", lambda: st), \
             patch.object(da, "_set_status", set_status), \
             patch.object(da.dc, "_doors", lambda: []):
            da.run_checks(now=now, probe=lambda d: {}, read_punches=lambda d: None, force=True)
        return {c.kwargs["json"]["chat_id"]: c.kwargs["json"]["text"] for c in tg_post.call_args_list}

    def soon(seconds=1):
        return now_datetime() + timedelta(seconds=seconds)

    for k in STATE_KEYS:
        da._state_put(k, None)
    with patch.object(ds, "offline_after_minutes", lambda: 5):
        mark = now_datetime()
        # LOST: silent for 10 minutes, door was open
        frappe.db.set_value("Door Sensor", LOST, {"last_seen": mark - timedelta(minutes=10), "last_state": "open"},
                            update_modified=False)
        post(state="fault", event="change")
        post(state="open", event="change")
        t = soon()
        msgs = run(settings_for(t), t, mark)
        door_msg, dev_msg = msgs.get("-1", ""), msgs.get("-2", "")
        check("ngoài giờ: Door opened after hours (kênh cửa)", "Door opened after hours" in door_msg, door_msg[:200])
        check("fault + hết fault (kênh thiết bị)", "Door sensor fault" in dev_msg and "working again" in dev_msg, dev_msg[:300])
        check("mất kết nối -> Door sensor offline + trạng thái cuối", "Door sensor offline" in dev_msg and "DOOR OPEN" in dev_msg)
        check("mất kết nối -> last_state unknown", sensor_row(LOST).last_state == "unknown")
        check("tin cửa KHÔNG sang kênh thiết bị", "Door opened" not in dev_msg)
        t2 = soon(30)
        msgs = run(settings_for(t2), t2, soon(0))
        check("offline KHÔNG báo lặp", "offline" not in msgs.get("-2", ""))

        # left open after hours, dated from last_state_change
        mark = now_datetime()
        da._state_put(f"door_alerts:sensor_open:{ON}", None)   # the first run already saw it open "just now"
        frappe.db.set_value("Door Sensor", ON, "last_state_change", mark - timedelta(minutes=3), update_modified=False)
        t = soon(2)
        msgs = run(settings_for(t), t, mark)
        check("mở 3 phút ngoài giờ -> Door left open after hours", "Door left open after hours" in msgs.get("-1", ""), msgs.get("-1", "")[:200])
        t = soon(60)
        msgs = run(settings_for(t), t, soon(0))
        check("chưa tới chu kỳ nhắc -> không nhắc lại", "Door still open" not in msgs.get("-1", ""))
        mark = now_datetime()
        post(state="closed", event="change")
        t = soon(120)
        msgs = run(settings_for(t), t, mark)
        check("đóng lại -> Door closed", "Door closed" in msgs.get("-1", ""), msgs.get("-1", "")[:200])

        # back online
        mark = now_datetime()
        post(door_id=LOST, state="closed", event="heartbeat")
        t = soon(180)
        msgs = run(settings_for(t), t, mark)
        check("có lại -> Door sensor back online", "Door sensor back online" in msgs.get("-2", ""), msgs.get("-2", "")[:200])
        last = events(LOST)[-1]
        check("unknown -> closed khi có lại: Event heartbeat", last.previous_state == "unknown" and last.event == "heartbeat")

        # working hours + After Hours: no open alert
        mark = now_datetime()
        post(state="open", event="change")
        t = soon()
        msgs = run(settings_for(t, after_hours=False), t, mark)
        check("trong giờ + After Hours: không báo mở", "Door opened" not in msgs.get("-1", ""), str(msgs)[:200])
        # Always: open alert inside working hours too
        st = settings_for(t, after_hours=False)
        st.sensor_open_alert = "Always"
        msgs = run(st, t, mark)
        check("trong giờ + Always: báo Door opened", "Door opened" in msgs.get("-1", ""), str(msgs)[:200])
        # Off
        st = settings_for(t)
        st.sensor_open_alert = "Off"
        msgs = run(st, t, mark)
        check("Off: không báo mở", "Door opened" not in msgs.get("-1", ""))

        # Send Door Alerts off: nothing about that sensor
        frappe.db.set_value("Door Sensor", ON, "send_door_alerts", 0, update_modified=False)
        mark = now_datetime()
        post(state="closed", event="change")
        post(state="open", event="change")
        t = soon()
        msgs = run(settings_for(t), t, mark)
        check("Send Door Alerts tắt: không báo", "Test -ON" not in " ".join(msgs.values()), str(msgs)[:200])

    frappe.set_user("Administrator")
    status = da.get_status()
    check("get_status có danh sách cảm biến", any(x["sensor_id"] == ON for x in status["sensors"]))
finally:
    tg.stop()
    frappe.log_error = _orig_log_error
    frappe.set_user("Administrator")
    frappe.db.rollback()
    for k in STATE_KEYS:
        da._state_put(k, None)
    frappe.db.commit()

print(f"\n{ok} PASS / {fail} FAIL")
