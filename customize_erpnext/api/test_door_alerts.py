"""Hồi quy cảnh báo cửa Telegram — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/api/test_door_alerts.py').read())"

KHÔNG kết nối máy thật, KHÔNG gửi Telegram thật: cửa là 2 máy giả (TEST-NET),
probe/đọc log được thay bằng hàm giả, `requests.post` bị mock. Setting dựng trong
bộ nhớ (không lưu). Kết thúc rollback + xoá cache key test.
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

import frappe
from frappe.utils import now_datetime

import customize_erpnext.api.door_alerts as da

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
    return False


DOORS = [
    {"device_name": "ZZ Test Door A", "ip_address": "192.0.2.10", "enable": True, "is_door_control": True, "send_door_alerts": True},
    {"device_name": "ZZ Test Door B", "ip_address": "192.0.2.11", "enable": True, "is_door_control": True, "send_door_alerts": True},
]
TOKEN = "123456:TEST-TOKEN-SECRET"


def hm(dt):
    return dt.strftime("%H:%M:%S")


def make_settings(now, after_hours=True):
    s = frappe.new_doc("Door Alert Setting")
    s.enabled = 1
    s.bot_token = TOKEN
    s.append("recipients", {"label": "Group 1", "chat_id": "-1001", "enabled": 1})
    s.append("recipients", {"label": "Group 2", "chat_id": "-1002", "enabled": 1})
    s.append("recipients", {"label": "Off", "chat_id": "-1003", "enabled": 0})
    if after_hours:   # working period = a window that does not contain `now`
        s.work_start_time, s.work_end_time = hm(now + timedelta(hours=1)), hm(now + timedelta(hours=2))
    else:
        s.work_start_time, s.work_end_time = hm(now - timedelta(hours=1)), hm(now + timedelta(hours=1))
    for f in ("alert_device_offline", "alert_unlock_all", "alert_command_failed", "alert_unknown_user"):
        s.set(f, 1)
    s.erp_open_alert = s.fingerprint_alert = "After Hours"
    # Các mục 1–10 dùng ID 99000x (≥ 6000) làm ID giả -> tắt lọc ID đối tác; mục 11 kiểm riêng.
    s.only_staff_user_ids = 0
    s.offline_after_minutes = 5
    s.check_interval_minutes = 2
    s.daily_summary = 0
    s.last_check_at = now - timedelta(minutes=5)
    return s


def tg_response(ok_flag=True):
    r = MagicMock()
    r.content = b"x"
    r.status_code = 200 if ok_flag else 401
    r.json.return_value = {"ok": True} if ok_flag else {"ok": False, "description": f"Unauthorized bot{TOKEN}"}
    return r


STATUS = {}


def run(settings, now, probes=None, tg_ok=True, force=False, doors=None):
    """run_checks with every outside dependency replaced."""
    probes = probes or {d["device_name"]: {"online": True} for d in DOORS}

    def set_status(**values):
        STATUS.update(values)
        for k, v in values.items():
            settings.set(k, v)

    with patch.object(da, "_settings", lambda: settings), \
         patch.object(da, "_set_status", set_status), \
         patch.object(da.dc, "_doors", lambda: doors if doors is not None else DOORS), \
         patch("requests.post", return_value=tg_response(tg_ok)) as post:
        out = da.run_checks(now=now, probe=lambda ds: probes, read_punches=lambda ds: None, force=force)
    texts = [c.kwargs["json"]["text"] for c in post.call_args_list]
    chats = [c.kwargs["json"]["chat_id"] for c in post.call_args_list]
    return out, texts, chats, post


cache_keys = [f"door_alerts:{k}:{d['device_name']}" for d in DOORS for k in ("offline", "not_locked")]
try:
    print("1. Giờ làm việc")
    check("06–22: 10:00 trong giờ", da.in_work_hours("2026-10-09 10:00:00", "06:00:00", "22:00:00"))
    check("06–22: 22:00 ngoài giờ", not da.in_work_hours("2026-10-09 22:00:00", "06:00:00", "22:00:00"))
    check("06–22: 05:59 ngoài giờ", not da.in_work_hours("2026-10-09 05:59:00", "06:00:00", "22:00:00"))
    check("qua nửa đêm 22–06: 23:00 trong giờ", da.in_work_hours("2026-10-09 23:00:00", "22:00:00", "06:00:00"))
    check("qua nửa đêm 22–06: 12:00 ngoài giờ", not da.in_work_hours("2026-10-09 12:00:00", "22:00:00", "06:00:00"))
    check("nhận timedelta từ DB", da.in_work_hours("2026-10-09 07:00:00", timedelta(hours=6), timedelta(hours=22)))

    print("2. Validate Setting")
    base = now_datetime()
    s = make_settings(base)
    s.check_interval_minutes = 0
    check("chu kỳ 0 bị chặn", raises(s.validate, frappe.ValidationError))
    s.check_interval_minutes = 2
    s.bot_token = ""
    check("bật mà thiếu token bị chặn", raises(s.validate, frappe.ValidationError))
    s.bot_token = TOKEN
    for r in s.recipients:
        r.enabled = 0
    check("bật mà không có người nhận bị chặn", raises(s.validate, frappe.ValidationError))
    check("mặc định của DocType: TẮT", frappe.get_meta("Door Alert Setting").get_field("enabled").default == "0")

    print("3. Tắt thì không làm gì")
    s = make_settings(base)
    s.enabled = 0
    out, texts, _c, post = run(s, base)
    check("disabled → bỏ qua, không gửi", out.get("skipped") == "disabled" and not post.called)

    print("4. Sự kiện ngoài giờ")
    emp = frappe.db.get_value("Employee", {"status": "Active"}, ["name", "employee_name"], as_dict=True)
    now = now_datetime()
    t = now - timedelta(minutes=1)
    def act(action, result, door, error=None):
        frappe.get_doc({"doctype": "Door Control Action", "timestamp": t, "action": action, "result": result,
                        "device_name": door["device_name"], "device_ip": door["ip_address"], "seconds": 15,
                        "user": "Administrator", "user_full_name": "Administrator", "error": error}).insert(ignore_permissions=True)
    def punch(user_id, ts, employee=None):
        frappe.get_doc({"doctype": "Door Access Log", "user_id": user_id, "employee": employee,
                        "timestamp": ts, "device_ip": DOORS[0]["ip_address"]}).insert(ignore_permissions=True)
    act("Unlock", "Success", DOORS[0])
    act("Unlock", "Failed", DOORS[1], error="timed out")
    act("Unlock All", "Success", DOORS[0])
    act("Unlock All", "Failed", DOORS[1], error="timed out")
    punch("990001", t, emp.name)
    punch("990002", t + timedelta(seconds=10))                       # unknown ID
    punch("990003", now - timedelta(days=2))                         # backlog: stored now, must NOT alert
    s = make_settings(now)
    out, texts, chats, _p = run(s, now + timedelta(seconds=1))
    body = texts[0] if texts else ""
    check("1 tin / người nhận đang bật (2 group, bỏ group tắt)", sorted(chats) == ["-1001", "-1002"], str(chats))
    check("cùng nội dung cho mọi người nhận", len(set(texts)) == 1)
    check("có: mở từ ERP ngoài giờ", "Opened from ERP after hours" in body or "Mở từ ERP ngoài giờ" in body)
    check("có: lệnh mở thất bại", "timed out" in body)
    check("Mở tất cả gộp 1 sự kiện, ghi cửa lỗi", body.count("ZZ Test Door B") >= 1 and (body.count("Open all doors used") + body.count("Mở tất cả cửa")) == 1)
    open_all_line = body.split("Open all doors used</b>\n")[1].split("\n")[0] if "Open all doors used" in body else ""
    check("Mở tất cả: ghi số cửa, chỉ nêu cửa lỗi", "1/2 doors opened" in open_all_line and "ZZ Test Door B" in open_all_line
          and "ZZ Test Door A" not in open_all_line, open_all_line.strip())
    check("có: quẹt ngoài giờ kèm mã NV + họ tên", f"{emp.name} {emp.employee_name}"[:40] in body)
    check("có: ID lạ", "ID 990002" in body)
    check("không báo log tồn đọng (timestamp cũ)", "990003" not in body)
    # ERP after hours + failed + open-all (grouped) + after-hours punch + unknown ID
    check("đếm 5 sự kiện", out["events"] == 5, str(out["events"]))
    check("dời mốc last_check_at", str(STATUS.get("last_check_at")) == str(now + timedelta(seconds=1)))

    print("5. Chưa đủ chu kỳ → không chạy lại")
    out2, texts2, _c, post2 = run(s, now + timedelta(seconds=40))
    check("trong 2 phút: không kiểm tra, không gửi", out2["events"] == 0 and not post2.called)

    print("6. Trong giờ làm")
    s = make_settings(now, after_hours=False)
    out, texts, _c, _p = run(s, now + timedelta(seconds=1))
    body = texts[0] if texts else ""
    check("trong giờ: KHÔNG báo quẹt của nhân viên", emp.name not in body)
    check("trong giờ: KHÔNG báo mở từ ERP", "after hours" not in body and "ngoài giờ" not in body)
    check("trong giờ: VẪN báo ID lạ + lệnh lỗi + mở tất cả", "ID 990002" in body and "timed out" in body)

    print("6b. Báo mọi lần mở (tuỳ chọn any time)")
    s = make_settings(now, after_hours=False)
    for f in ("alert_unlock_all", "alert_command_failed", "alert_unknown_user", "alert_device_offline"):
        s.set(f, 0)
    s.erp_open_alert = s.fingerprint_alert = "Always"
    out, texts, _c, _p = run(s, now + timedelta(seconds=1))
    body = texts[0] if texts else ""
    check("trong giờ: báo mở từ ERP", "Opened from ERP" in body and "after hours" not in body, str(out["events"]))
    check("trong giờ: báo quẹt của nhân viên", emp.name in body)
    check("trong giờ: ID lạ vẫn báo (thuộc 'mọi lượt quẹt')", "ID 990002" in body)
    check("Mở tất cả vẫn báo khi chỉ bật 'mọi lần mở ERP'", "Open all doors used" in body)
    check("lệnh lỗi KHÔNG báo (không phải lần mở)", "timed out" not in body.split("Open all doors used")[0])
    s2 = make_settings(now, after_hours=True)
    for f in ("alert_unlock_all", "alert_command_failed", "alert_unknown_user", "alert_device_offline"):
        s2.set(f, 0)
    s2.erp_open_alert = s2.fingerprint_alert = "Always"
    out2, texts2, _c, _p = run(s2, now + timedelta(seconds=1))
    body2 = texts2[0] if texts2 else ""
    check("ngoài giờ: ghi 'after hours', mỗi lần mở chỉ 1 dòng",
          body2.count("Opened from ERP after hours") == 1 and "🔓" not in body2 and body2.count(emp.name) == 1)
    check("cùng số sự kiện trong giờ và ngoài giờ", out["events"] == out2["events"], f'{out["events"]} vs {out2["events"]}')

    print("7. Mất kết nối")
    for k in cache_keys:
        frappe.cache.delete_value(k)
    s = make_settings(now)
    s.alert_command_failed = s.alert_unlock_all = s.alert_unknown_user = 0
    s.erp_open_alert = s.fingerprint_alert = "Off"
    off = {DOORS[0]["device_name"]: {"online": True}, DOORS[1]["device_name"]: {"online": False}}
    T0 = now + timedelta(minutes=10)
    s.last_check_at = T0 - timedelta(minutes=3)
    out, texts, _c, _p = run(s, T0, probes=off)
    check("vừa mất: chưa báo (ngưỡng 5 phút)", out["events"] == 0)
    out, texts, _c, _p = run(s, T0 + timedelta(minutes=6), probes=off)
    check("mất 6 phút: báo 1 lần", out["events"] == 1 and "ZZ Test Door B" in (texts or [""])[0], str(out))
    out, texts, _c, _p = run(s, T0 + timedelta(minutes=9), probes=off)
    check("vẫn mất: không báo lặp", out["events"] == 0)
    out, texts, _c, _p = run(s, T0 + timedelta(minutes=12))
    check("có lại: báo kết nối lại", out["events"] == 1 and ("back online" in texts[0] or "kết nối lại" in texts[0]))

    print("8. Telegram lỗi")
    s = make_settings(now)
    before = s.last_check_at
    STATUS.clear()
    with patch.object(da.frappe, "log_error") as log_err:
        out, texts, _c, _p = run(s, now + timedelta(seconds=1), tg_ok=False)
    check("gửi lỗi mọi nơi → KHÔNG dời mốc (lần sau gửi lại)", s.last_check_at == before and "last_check_at" not in STATUS)
    check("ghi last_error", bool(STATUS.get("last_error")))
    check("token không lộ trong last_error", TOKEN not in (STATUS.get("last_error") or ""))
    check("token không lộ trong Error Log", all(TOKEN not in str(c) for c in log_err.call_args_list))

    print("9. Tổng hợp cuối ngày")
    s = make_settings(now)
    s.alert_command_failed = s.alert_unlock_all = s.alert_unknown_user = s.alert_device_offline = 0
    s.erp_open_alert = s.fingerprint_alert = "Off"
    s.daily_summary = 1
    s.daily_summary_time = hm(now - timedelta(minutes=1)) if now.hour or now.minute else "00:00:00"
    s.last_summary_date = None
    out, texts, _c, _p = run(s, now + timedelta(seconds=1))
    check("gửi tổng hợp", out["summary"] and any("ZZ Test Door A" in x for x in texts))
    out, texts, _c, _p = run(s, now + timedelta(minutes=5))
    check("cùng ngày không gửi lại", not out["summary"])

    print("9b. Tạm ngưng / chọn cửa / Check Now / bộ đếm")
    s = make_settings(now)
    s.mute_until = now + timedelta(hours=1)
    STATUS.clear()
    out, texts, _c, post = run(s, now + timedelta(seconds=1))
    check("đang tạm ngưng: có sự kiện nhưng KHÔNG gửi", out["muted"] and out["events"] > 0 and not post.called, str(out))
    check("tạm ngưng: vẫn dời mốc (không dồn tin lại)", "last_check_at" in STATUS)
    s = make_settings(now)
    s.mute_until = now - timedelta(minutes=1)
    STATUS.clear()
    out, texts, _c, post = run(s, now + timedelta(seconds=1))
    check("hết giờ tạm ngưng: gửi lại bình thường", post.called and not out["muted"])
    check("bộ đếm tin hôm nay + last_sent_at", STATUS.get("sent_count") == 1 and STATUS.get("last_sent_at"), str(STATUS.get("sent_count")))
    unwatched = [dict(DOORS[0], send_door_alerts=False), DOORS[1]]
    s = make_settings(now)
    out, texts, _c, _p = run(s, now + timedelta(seconds=1), doors=unwatched)
    check("cửa bỏ tick Send Door Alerts: không báo", "ZZ Test Door A" not in "".join(texts), str(out["events"]))
    s = make_settings(now)
    s.last_check_at = now
    out, texts, _c, post = run(s, now + timedelta(seconds=20), force=True)
    check("force (Check Now): chạy ngay dù chưa đủ chu kỳ", post.called)

    print("9d. Mở tất cả qua ranh giới phút")
    edge = now.replace(second=59, microsecond=900000) - timedelta(minutes=1)
    s = make_settings(now)
    rows = [frappe._dict(timestamp=edge, action="Unlock All", result="Success", device_name=DOORS[0]["device_name"], user="Administrator", user_full_name="Administrator"),
            frappe._dict(timestamp=edge + timedelta(milliseconds=200), action="Unlock All", result="Success", device_name=DOORS[1]["device_name"], user="Administrator", user_full_name="Administrator")]
    with patch.object(da.frappe.db, "sql", return_value=rows):
        ev = da._action_events(s, DOORS, now - timedelta(minutes=5), now)
    check("1 lần bấm qua 2 phút vẫn là 1 sự kiện", len(ev) == 1 and "2/2 doors opened" in ev[0][2], str(ev))

    print("9c. Get Chat ID")
    s = make_settings(now)
    upd = {"ok": True, "result": [
        {"message": {"chat": {"id": -5546758050, "type": "group", "title": "TIQN"}, "text": "/start@x"}},
        {"message": {"chat": {"id": -42, "type": "group", "title": "Old"}, "migrate_to_chat_id": -100777}},
        {"my_chat_member": {"chat": {"id": -1001, "type": "supergroup", "title": "Group 1"}}},
    ]}
    def fake_get(url, timeout=None, **kw):
        r = MagicMock(); r.json.return_value = {"ok": True, "result": {"username": "torayqn_bot"}} if url.endswith("getMe") else upd
        return r
    with patch.object(da, "_settings", lambda: s), patch("requests.get", side_effect=fake_get):
        res = da.get_chat_ids()
    ids = {c["chat_id"]: c for c in res["chats"]}
    check("đọc chat id group", "-5546758050" in ids and ids["-5546758050"]["title"] == "TIQN")
    check("group nâng cấp: dùng id mới", "-100777" in ids and "-42" not in ids)
    check("đánh dấu chat đã có trong bảng", ids["-1001"]["added"] and not ids["-5546758050"]["added"])
    check("trả tên bot", res["bot"] == "torayqn_bot")

    print("9e. Chốt chưa khoá sau giờ làm (Lock Sensor)")
    for d in DOORS:
        frappe.cache.delete_value(f"door_alerts:not_locked:{d['device_name']}")
    sdoors = [dict(DOORS[0], has_door_sensor=True, sensor_type="NO"), dict(DOORS[1], has_door_sensor=True, sensor_type="NO")]
    def probes(a, b):   # raw byte per door; sensor_locked_value is 1 in the DB
        return {DOORS[0]["device_name"]: {"online": True, "sensor_raw": a, "device_sensor_mode": "NO"},
                DOORS[1]["device_name"]: {"online": True, "sensor_raw": b, "device_sensor_mode": "NO"}}
    def nl_settings(t, after_hours=True):
        s = make_settings(t, after_hours=after_hours)
        for f in ("alert_unlock_all", "alert_command_failed", "alert_unknown_user", "alert_device_offline"):
            s.set(f, 0)
        s.erp_open_alert = s.fingerprint_alert = "Off"
        s.use_lock_sensor = s.alert_not_locked_after_hours = 1
        s.not_locked_repeat_minutes = 30
        return s
    T = now + timedelta(hours=3)
    def step(minutes, a, b, after_hours=True, tg_ok=True):
        t = T + timedelta(minutes=minutes)
        s = nl_settings(t, after_hours)
        s.last_check_at = t - timedelta(minutes=5)
        out, texts, _c, _p = run(s, t, probes=probes(a, b), doors=sdoors, tg_ok=tg_ok)
        return out, "".join(texts)
    out, body = step(0, 0, 1)
    check("lần đầu thấy chưa khoá: chưa báo (chờ 2 phút)", out["events"] == 0)
    out, body = step(1, 0, 1)
    check("mới 1 phút: chưa báo", out["events"] == 0)
    out, body = step(2, 0, 1)
    check("2 phút: báo 'chưa khoá' 1 cửa", out["events"] == 1 and "Door not locked after hours" in body and "ZZ Test Door A" in body, body[-120:])
    out, body = step(20, 0, 1)
    check("trong 30 phút: không nhắc lại", out["events"] == 0)
    out, body = step(33, 0, 1)
    check("30 phút sau: nhắc lại", out["events"] == 1 and "Door still not locked" in body and "33 minutes" in body, body[-120:])
    out, body = step(40, 1, 1)
    check("đã khoá: 1 tin 'đã khoá'", out["events"] == 1 and "Door locked" in body and "40 minutes" in body, body[-120:])
    out, body = step(42, 1, 1)
    check("sau khi khoá: im lặng", out["events"] == 0)
    # short release (fingerprint / ERP open) never alerts
    step(50, 0, 1); out, body = step(51, 1, 1)
    check("nhả < 2 phút rồi khoá: không báo gì", out["events"] == 0)
    # working hours: drop silently
    step(60, 0, 1); step(62, 0, 1)
    out, body = step(63, 0, 1, after_hours=False)
    check("vào giờ làm: im lặng", out["events"] == 0)
    check("vào giờ làm: xoá trạng thái", frappe.cache.get_value(f"door_alerts:not_locked:{DOORS[0]['device_name']}") is None)
    # failed send: first alert retried
    step(70, 0, 1); out, body = step(72, 0, 1, tg_ok=False)
    check("gửi lỗi: có sự kiện", out["events"] == 1)
    out, body = step(74, 0, 1)
    check("gửi lỗi thì lần sau gửi lại tin đầu", out["events"] == 1 and "Door not locked after hours" in body)
    # mismatch / offline keep state, no event
    s = nl_settings(T + timedelta(minutes=80)); s.last_check_at = T + timedelta(minutes=75)
    bad = {DOORS[0]["device_name"]: {"online": True, "sensor_raw": 0, "device_sensor_mode": "NC"}, DOORS[1]["device_name"]: {"online": False}}
    out, _t, _c, _p = run(s, T + timedelta(minutes=80), probes=bad, doors=sdoors)
    check("lệch Door Sensor Mode / offline: không báo về khoá", out["events"] == 0)
    s = nl_settings(T); s.use_lock_sensor = 0
    out, _t, _c, _p = run(s, T + timedelta(minutes=90), probes=probes(0, 0), doors=sdoors, force=True)
    check("cờ Use Lock Sensor tắt: không có sự kiện khoá", out["events"] == 0)
    for d in DOORS:
        frappe.cache.delete_value(f"door_alerts:not_locked:{d['device_name']}")

    print("10. An toàn nội dung")
    check("escape HTML", "&lt;b&gt;" in da._esc("<b>"))
    long_text = "\n".join("x" * 100 for _ in range(200))
    parts = da._split(long_text)
    check("tách tin dài ≤ 3800 ký tự", len(parts) > 1 and all(len(p) <= da.MAX_MESSAGE_CHARS for p in parts), str(len(parts)))

    print("11. Chỉ ID nhân viên (bỏ ID đối tác ≥ 6000)")
    t11 = now_datetime()
    punch("6001", t11 - timedelta(seconds=20))      # ID đối tác, không khớp NV
    punch("5999", t11 - timedelta(seconds=10))      # ID < 6000, không khớp NV
    s = make_settings(t11)
    s.only_staff_user_ids, s.staff_user_id_limit = 1, 6000
    until11 = now_datetime() + timedelta(seconds=1)   # sau khi insert: lọc theo creation <= until
    ev = da._punch_events(s, DOORS, t11 - timedelta(minutes=2), until11)
    lines = " ".join(e[2] for e in ev)
    check("bật lọc: KHÔNG báo ID 6001", "ID 6001" not in lines, lines[:120])
    check("bật lọc: VẪN báo ID 5999", "ID 5999" in lines)
    check("ID không phải số không bị coi là đối tác", not da._is_partner_id(s, "abc"))
    s.only_staff_user_ids = 0
    ev = da._punch_events(s, DOORS, t11 - timedelta(minutes=2), until11)
    check("tắt lọc: báo cả ID 6001", "ID 6001" in " ".join(e[2] for e in ev))
    s.only_staff_user_ids = 1
    summary = da.build_daily_summary(s, DOORS[:1], t11.date())
    s.only_staff_user_ids = 0
    summary_all = da.build_daily_summary(s, DOORS[:1], t11.date())
    import re as _re
    n_on = int(_re.search(r"(\d+) punches", summary).group(1))
    n_off = int(_re.search(r"(\d+) punches", summary_all).group(1))
    check("báo cáo ngày: bật lọc đếm ít hơn tắt lọc (bỏ ID ≥ 6000)", n_on < n_off, f"{n_on} vs {n_off}")
finally:
    frappe.db.rollback()
    for k in cache_keys:
        frappe.cache.delete_value(k)
    print(f"\n{ok} PASS / {fail} FAIL  (đã rollback + xoá cache test)")
