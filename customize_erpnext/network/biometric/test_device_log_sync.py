"""Hồi quy lấy log tự động (device_log_sync) — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/network/biometric/test_device_log_sync.py').read())"

KHÔNG kết nối máy thật, KHÔNG ghi Employee Checkin, KHÔNG gửi mail: máy, đọc log,
_add_checkin, cursor và frappe.sendmail đều bị thay. Setting dựng trong bộ nhớ.
Kết thúc xoá các cache key test.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch

import frappe

import customize_erpnext.network.biometric.device_log_sync as dls

ok = fail = 0
# the job writes REAL production keys (last cycle, last report, stall flag, last mail):
# keep them and put them back at the end, whatever the tests below do
_PROD_KEYS = (dls.HEARTBEAT_KEY, dls.LAST_REPORT_KEY, dls.HEARTBEAT_ALERT_KEY, dls.LAST_EMAIL_KEY)
_prod_saved = {k: frappe.cache().get_value(k) for k in _PROD_KEYS}
_queue_patch = patch.object(dls, "_recalc_queue_busy", lambda: False)
_queue_patch.start()
_real_logger = dls._logger
dls._logger = lambda: NS(info=lambda *a: None)  # keep test lines out of the real log


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def W(fetch):
    """old-style fetch(cfg, label, clear_after) -> read_attendance(...) returning (records, warning)."""
    def read(cfg, label, clear_after=False):
        return fetch(cfg, label, clear_after=clear_after), None
    return read


def rec(user_id, ts, uid=1):
    return NS(uid=uid, user_id=user_id, timestamp=ts)


NOW = datetime(2026, 10, 23, 10, 0, 0)
MACHINES = [{"name": "ZZ Test 1", "device_name": "ZZ Test 1", "ip_address": "192.0.2.1"},
            {"name": "ZZ Test 2", "device_name": "ZZ Test 2", "ip_address": "192.0.2.2"}]


def settings(**kw):
    base = dict(auto_sync_logs=1, import_start_date="2026-09-25", clear_from_device_on_fetch=0,
                send_error_email=0, error_email_recipients="", error_email_cooldown_minutes=30,
                peak_times="", peak_window_minutes=15)
    base.update(kw)
    return frappe._dict(base)


def clear_cache():
    for m in MACHINES:
        frappe.cache().delete_value(dls.FAIL_KEY.format(m["device_name"]))
    frappe.cache().delete_value(dls.LAST_EMAIL_KEY)


print("1. lower_bound")
check("cursor sau ngày bắt đầu → cursor", dls.lower_bound("2026-10-23 08:00:00", "2026-09-25") == datetime(2026, 10, 23, 8))
check("cursor trước ngày bắt đầu → ngày bắt đầu", dls.lower_bound("2026-01-01 08:00:00", "2026-09-25") == datetime(2026, 9, 25))
check("chưa có checkin → ngày bắt đầu", dls.lower_bound(None, "2026-09-25") == datetime(2026, 9, 25))
check("không có cả hai → đầu hôm nay", dls.lower_bound(None, None).time() == datetime.min.time())

print("2. select_new_records")
lower = datetime(2026, 10, 23, 8, 0)
records = [
    rec("100", datetime(2026, 10, 23, 9, 0)),
    rec("101", datetime(2026, 10, 23, 8, 0)),           # = cursor → gửi lại, _add_checkin bỏ trùng
    rec("102", datetime(2026, 10, 23, 7, 59)),          # cũ
    rec("", datetime(2026, 10, 23, 9, 0)),              # user_id rỗng
    rec("103", datetime(2000, 1, 1), uid=0),            # rác
    rec("104", NOW + timedelta(minutes=5)),             # đồng hồ máy nhanh 5' → vẫn nhận
    rec("105", NOW + timedelta(hours=2)),               # tương lai → bỏ
]
selected, counts = dls.select_new_records(records, lower, NOW)
check("chọn đúng 3 bản ghi, cũ nhất trước", [r.user_id for r in selected] == ["101", "100", "104"], [r.user_id for r in selected])
check("đếm bỏ qua", counts == {"junk": 2, "old": 1, "future": 1}, counts)

print("3. job: lỗi ghi → dừng máy đó, máy khác vẫn chạy")
calls = []


def fake_add(user_id, ts, device):
    calls.append((device, user_id))
    if user_id == "201":
        return "error", "boom"
    return {"200": "processed", "202": "processed", "300": "skipped"}.get(user_id, "skipped_no_employee"), None


def fake_fetch(cfg, label, clear_after=False):
    return {"ZZ Test 1": [rec("200", NOW - timedelta(minutes=3)), rec("201", NOW - timedelta(minutes=2)),
                          rec("202", NOW - timedelta(minutes=1))],
            "ZZ Test 2": [rec("300", NOW - timedelta(minutes=1)), rec("999", NOW - timedelta(minutes=1))]}[label]


clear_cache()
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES), \
     patch.object(dls, "read_attendance", W(fake_fetch)), \
     patch.object(dls, "_add_checkin", fake_add), \
     patch.object(dls, "_cursor", lambda name: NOW - timedelta(hours=1)), \
     patch.object(dls, "now_datetime", lambda: NOW), \
     patch.object(frappe, "get_single", lambda name: settings()), \
     patch.object(frappe, "log_error", lambda **kw: None), \
     patch.object(frappe, "sendmail", lambda **kw: calls.append(("MAIL", kw))):
    report = dls._run_device_log_sync()
r1, r2 = report
check("máy 1 dừng ở lượt lỗi (202 không gửi)", [c for c in calls if c[0] == "ZZ Test 1"] == [("ZZ Test 1", "200"), ("ZZ Test 1", "201")], calls)
check("máy 1 báo lỗi", not r1["ok"] and r1["errors"] == 1 and r1["processed"] == 1, r1.get("error"))
check("máy 2 chạy đủ", r2["ok"] and r2["skipped"] == 1 and r2["skipped_no_employee"] == 1, r2)
check("email tắt → không gửi", not any(c[0] == "MAIL" for c in calls))

print("4. mất kết nối: chỉ tính lỗi từ lần thứ 3 liên tiếp; email theo cooldown")


def offline_fetch(cfg, label, clear_after=False):
    raise ConnectionError(f"Cannot connect to {label}")


mails = []
clear_cache()
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", W(offline_fetch)), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings(send_error_email=1, error_email_recipients="son.nt@tiqn.com.vn")), \
     patch.object(frappe, "log_error", lambda **kw: None), \
     patch.object(frappe, "sendmail", lambda **kw: mails.append(kw)):
    for i in range(4):
        rows = dls._run_device_log_sync()
        check(f"lần {i + 1}: đếm {rows[0].get('consecutive_failures')}", rows[0]["consecutive_failures"] == i + 1)
check("chỉ 1 mail (lần 3; lần 4 trong cooldown)", len(mails) == 1, len(mails))
check("mail gửi đúng người nhận test", mails and mails[0]["recipients"] == ["son.nt@tiqn.com.vn"])

print("5. kết nối lại → reset bộ đếm; dry_run không ghi")
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", W(lambda cfg, label, clear_after=False: [rec("200", NOW)])), \
     patch.object(dls, "_add_checkin", lambda *a: ("processed", None)), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings()):
    dls._run_device_log_sync()
check("bộ đếm đã xoá", frappe.cache().get_value(dls.FAIL_KEY.format("ZZ Test 1")) is None)

seen = {}


def dry_fetch(cfg, label, clear_after=False):
    seen["clear_after"] = clear_after
    return [rec("200", NOW)]


with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", W(dry_fetch)), \
     patch.object(dls, "_add_checkin", lambda *a: (_ for _ in ()).throw(AssertionError("must not insert"))), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings(auto_sync_logs=0, clear_from_device_on_fetch=1)):
    rows = dls._run_device_log_sync(dry_run=1)
check("dry_run chạy cả khi tắt auto, không ghi", rows[0]["new"] == 1 and rows[0]["processed"] == 0)
check("dry_run không bao giờ xoá log trên máy", seen.get("clear_after") is False)

with patch.object(frappe, "get_single", lambda name: settings(auto_sync_logs=0)):
    check("auto tắt → job không làm gì", dls._run_device_log_sync() == [])

print("6. in_peak (mặc định 07:30,07:45,17:00,18:00 / 15')")
D = lambda hm: datetime(2026, 10, 23, int(hm[:2]), int(hm[3:5]), int(hm[6:8] or 0) if len(hm) > 5 else 0)
never_set = frappe._dict(peak_times=None, peak_window_minutes=None)
for hm, want in [("07:29:59", False), ("07:30:00", True), ("07:59:59", True), ("08:00:00", False),
                 ("16:59:59", False), ("17:14:59", True), ("17:15:00", False), ("18:05:00", True), ("19:05:00", False)]:
    check(f"chưa đặt → mặc định: {hm} = {want}", dls.in_peak(never_set, D(hm)) is want)
check("xoá trống = tắt (17:05 không peak)", dls.in_peak(frappe._dict(peak_times="", peak_window_minutes=15), D("17:05")) is False)
check("giá trị hỏng → vẫn dùng mặc định (17:05 peak)", dls.in_peak(frappe._dict(peak_times="5pm", peak_window_minutes=15), D("17:05")) is True)
check("window 30: 17:29 peak", dls.in_peak(frappe._dict(peak_times="17:00", peak_window_minutes=30), D("17:29")) is True)

print("7. sắp tới giờ cao điểm (trong PEAK_START_MARGIN) → không bắt đầu đọc")
fetched = []
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES), \
     patch.object(dls, "in_peak", side_effect=[False, True]), \
     patch.object(dls, "read_attendance", W(lambda cfg, label, clear_after=False: fetched.append(label) or [])), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings()):
    rows = dls._run_device_log_sync()
check("không đọc máy nào", fetched == [], fetched)
check("cả 2 máy skipped (peak window)", all(r.get("skip_reason") == "peak window" for r in rows), rows)

print("8. ghi dồn: tối đa MAX_INSERTS_PER_MACHINE / máy / chu kỳ (test với giới hạn 50)")
_cap = patch.object(dls, "MAX_INSERTS_PER_MACHINE", 50)
_cap.start()
many = [rec(str(1000 + i), NOW - timedelta(minutes=60) + timedelta(seconds=i)) for i in range(120)]
inserted = []
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", W(lambda cfg, label, clear_after=False: many)), \
     patch.object(dls, "_add_checkin", lambda u, ts, d: inserted.append(ts) or ("processed", None)), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(dls, "now_datetime", lambda: NOW), \
     patch.object(frappe, "get_single", lambda name: settings(send_error_email=1, error_email_recipients="son.nt@tiqn.com.vn")), \
     patch.object(frappe, "sendmail", lambda **kw: inserted.append("MAIL")):
    rows = dls._run_device_log_sync()
check(f"ghi đúng {dls.MAX_INSERTS_PER_MACHINE}, cũ nhất trước", inserted == [r.timestamp for r in many[:dls.MAX_INSERTS_PER_MACHINE]], len(inserted))
_cap.stop()
check("deferred=insert cap, không phải lỗi, không mail", rows[0]["deferred"] == "insert cap" and rows[0]["ok"] and "MAIL" not in inserted, rows[0]["deferred"])

print("9. queue short đầy → không đọc máy nào")
fetched = []
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES), \
     patch.object(dls, "_recalc_queue_busy", lambda: True), \
     patch.object(dls, "read_attendance", W(lambda cfg, label, clear_after=False: fetched.append(label) or [])), \
     patch.object(frappe, "get_single", lambda name: settings()):
    rows = dls._run_device_log_sync()
check("không đọc máy nào, cả 2 skipped", not fetched and all(r.get("skip_reason") == "queue short busy" for r in rows), rows)

print("10. QueueOverloaded khi ghi → hoãn, không tính lỗi")
logged = []
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", W(lambda cfg, label, clear_after=False: many[:3])), \
     patch.object(dls, "_add_checkin", lambda u, ts, d: ("error", dls.QUEUE_OVERLOADED_MARK + " Quá nhiều công việc nền (550)")), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(dls, "now_datetime", lambda: NOW), \
     patch.object(frappe, "get_single", lambda name: settings(send_error_email=1, error_email_recipients="son.nt@tiqn.com.vn")), \
     patch.object(frappe, "log_error", lambda **kw: logged.append(kw)), \
     patch.object(frappe, "sendmail", lambda **kw: logged.append("MAIL")):
    rows = dls._run_device_log_sync()
check("deferred=queue short full, errors=0", rows[0]["deferred"] == "queue short full" and rows[0]["errors"] == 0, rows[0])
check("không Error Log, không mail", not logged, logged)

print("11. cron trong giờ cao điểm → không enqueue")
queued = []
with patch.object(frappe, "get_cached_doc", lambda name: settings(peak_times="17:00")), \
     patch.object(dls, "now_datetime", lambda: D("17:05")), \
     patch.object(frappe, "enqueue", lambda *a, **kw: queued.append(a)):
    dls.enqueue_device_log_sync()
check("17:05 không enqueue", not queued)
with patch.object(frappe, "get_cached_doc", lambda name: settings(peak_times="17:00")), \
     patch.object(dls, "now_datetime", lambda: D("17:20")), \
     patch.object(frappe, "enqueue", lambda *a, **kw: queued.append(a)):
    dls.enqueue_device_log_sync()
check("17:20 có enqueue", len(queued) == 1)

print("12. đọc song song: 3 máy × 0,5 s < 1,2 s, và không đọc trong thread chính")
import threading
import time as _t
MACH3 = MACHINES + [{"name": "ZZ Test 3", "device_name": "ZZ Test 3", "ip_address": "192.0.2.3"}]
threads = []


def slow_read(cfg, label, clear_after=False):
    threads.append(threading.current_thread() is threading.main_thread())
    _t.sleep(0.5)
    return [rec("200", NOW)], None


with patch.object(dls, "get_machines", lambda enabled_only: MACH3), \
     patch.object(dls, "read_attendance", slow_read), \
     patch.object(dls, "_add_checkin", lambda *a: ("skipped", None)), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings()):
    t0 = _t.time()
    rows = dls._run_device_log_sync()
    took = _t.time() - t0
check("tổng < 1,2 s", took < 1.2, f"{took:.2f}s")
check("cả 3 máy đọc ngoài thread chính", threads == [False, False, False], threads)
check("thứ tự báo cáo giữ đúng thứ tự máy", [r["machine"] for r in rows] == ["ZZ Test 1", "ZZ Test 2", "ZZ Test 3"])

print("13. không mở khoá lại được máy → lỗi + Error Log + mail")
logged, mails = [], []
clear_cache()
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", lambda cfg, label, clear_after=False: ([], "Failed to re-enable device ZZ Test 1: timeout")), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings(send_error_email=1, error_email_recipients="son.nt@tiqn.com.vn")), \
     patch.object(frappe, "log_error", lambda **kw: logged.append(kw)), \
     patch.object(frappe, "sendmail", lambda **kw: mails.append(kw)):
    rows = dls._run_device_log_sync()
check("row lỗi, có nhắc re-enable", not rows[0]["ok"] and "re-enable" in rows[0]["error"], rows[0].get("error"))
check("1 Error Log + 1 mail", len(logged) == 1 and len(mails) == 1, (len(logged), len(mails)))

print("14. gộp khung cao điểm + thời gian trùng cao điểm")
dflt = frappe._dict(peak_times=None, peak_window_minutes=None)
iv = dls.peak_intervals(dflt, NOW.date())
check("07:30+07:45 gộp thành 07:30–08:00", [(a.strftime("%H:%M"), b.strftime("%H:%M")) for a, b in iv] == [("07:30", "08:00"), ("17:00", "17:15"), ("18:00", "18:15")], iv)
check("07:25→08:10 trùng 30 phút", dls.peak_overlap(dflt, D("07:25"), D("08:10")) == timedelta(minutes=30))
check("qua đêm 23:00→09:00 hôm sau trùng 30 phút", dls.peak_overlap(dflt, datetime(2026, 10, 22, 23), datetime(2026, 10, 23, 9)) == timedelta(minutes=30))
check("current_peak 07:50 → 07:30–08:00", dls.current_peak(dflt, D("07:50")) == (D("07:30"), D("08:00")))

print("15. kiểm tra job còn sống (check_heartbeat)")
_saved = {k: frappe.cache().get_value(k) for k in (dls.HEARTBEAT_KEY, dls.HEARTBEAT_ALERT_KEY, dls.LAST_EMAIL_KEY)}
hb_logs, hb_mails = [], []


def hb(now_hm, last, cfg=None):
    if last is None:
        frappe.cache().delete_value(dls.HEARTBEAT_KEY)
    elif last != "keep":
        frappe.cache().set_value(dls.HEARTBEAT_KEY, str(D(last)))
    with patch.object(frappe, "get_cached_doc", lambda name: cfg or settings(peak_times=None, peak_window_minutes=None, send_error_email=1, error_email_recipients="son.nt@tiqn.com.vn")), \
         patch.object(dls, "now_datetime", lambda: D(now_hm)), \
         patch.object(frappe, "log_error", lambda **kw: hb_logs.append(kw)), \
         patch.object(frappe, "sendmail", lambda **kw: hb_mails.append(kw)):
        dls.check_heartbeat()


frappe.cache().delete_value([dls.HEARTBEAT_ALERT_KEY, dls.LAST_EMAIL_KEY])
hb("10:00", None)
check("chưa có mốc → đặt mốc = bây giờ, không báo", frappe.cache().get_value(dls.HEARTBEAT_KEY) == str(D("10:00")) and not hb_logs)
hb("10:12", "10:00")
check("12 phút → bình thường", not hb_logs and not hb_mails)
hb("10:20", "10:00")
check("20 phút → 1 Error Log + 1 mail", len(hb_logs) == 1 and len(hb_mails) == 1, (len(hb_logs), len(hb_mails)))
hb("10:35", "keep")
check("vẫn treo → không thêm Error Log, mail chờ cooldown", len(hb_logs) == 1 and len(hb_mails) == 1)
hb("10:36", "10:35")
check("chạy lại → xoá cờ treo", frappe.cache().get_value(dls.HEARTBEAT_ALERT_KEY) is None)
frappe.cache().delete_value(dls.LAST_EMAIL_KEY)
hb_logs.clear(); hb_mails.clear()
hb("08:10", "07:29")
check("07:29→08:10 (41', trừ 30' cao điểm = 11') → bình thường", not hb_logs)
hb("08:10", "07:20")
check("07:20→08:10 (50' − 30' = 20') → báo", len(hb_logs) == 1)
hb("10:00", "06:00", cfg=settings(auto_sync_logs=0))
check("tắt auto → xoá mốc + cờ (bật lại không bị coi là treo)", frappe.cache().get_value(dls.HEARTBEAT_KEY) is None and frappe.cache().get_value(dls.HEARTBEAT_ALERT_KEY) is None)
for k, v in _saved.items():
    if v is None:
        frappe.cache().delete_value(k)
    else:
        frappe.cache().set_value(k, v)

print("16. chu kỳ đọc máy xong → ghi mốc; bị bỏ qua → không ghi")
_saved_hb = frappe.cache().get_value(dls.HEARTBEAT_KEY)
frappe.cache().delete_value(dls.HEARTBEAT_KEY)
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "_recalc_queue_busy", lambda: True), \
     patch.object(frappe, "get_single", lambda name: settings()):
    dls._run_device_log_sync()
check("queue bận (không đọc) → không ghi mốc", frappe.cache().get_value(dls.HEARTBEAT_KEY) is None)
with patch.object(dls, "get_machines", lambda enabled_only: MACHINES[:1]), \
     patch.object(dls, "read_attendance", lambda cfg, label, clear_after=False: ([], None)), \
     patch.object(dls, "_cursor", lambda name: None), \
     patch.object(frappe, "get_single", lambda name: settings()):
    dls._run_device_log_sync()
check("đọc xong → có mốc", frappe.cache().get_value(dls.HEARTBEAT_KEY) is not None)
if _saved_hb is None:
    frappe.cache().delete_value(dls.HEARTBEAT_KEY)
else:
    frappe.cache().set_value(dls.HEARTBEAT_KEY, _saved_hb)

print("17. Log Viewer: số lượt trùng ≠ lý do bỏ qua (lỗi 'skipped (1)' 23/10)")
from customize_erpnext.network.biometric import log_viewer as lv
_saved_rep = frappe.cache().get_value(dls.LAST_REPORT_KEY)
frappe.cache().set_value(dls.LAST_REPORT_KEY, {"finished": str(NOW), "rows": [
    {"machine": "ZZ Test 1", "ok": True, "read": 10, "new": 2, "processed": 1, "skipped": 1, "seconds": 1.0},
    {"machine": "ZZ Test 2", "ok": True, "skip_reason": "peak window"},
    {"machine": "ZZ Test 3", "ok": True, "skipped": "queue short busy"},   # format cũ trong cache
]})
M3 = MACHINES + [{"name": "ZZ Test 3", "device_name": "ZZ Test 3", "ip_address": "192.0.2.3"}]
with patch("customize_erpnext.network.biometric.machines.get_machines", lambda enabled_only: M3), \
     patch.object(dls, "_cursor", lambda name: None):
    ms = {m["machine"]: m for m in lv.get_sync_status()["machines"]}
check("chu kỳ thường: duplicates=1, không có skip_reason", ms["ZZ Test 1"]["duplicates"] == 1 and ms["ZZ Test 1"]["skip_reason"] is None, ms["ZZ Test 1"])
check("bỏ qua vì cao điểm → skip_reason", ms["ZZ Test 2"]["skip_reason"] == "peak window")
check("format cũ 'skipped' là chuỗi → skip_reason", ms["ZZ Test 3"]["skip_reason"] == "queue short busy" and ms["ZZ Test 3"]["duplicates"] is None)
if _saved_rep is None:
    frappe.cache().delete_value(dls.LAST_REPORT_KEY)
else:
    frappe.cache().set_value(dls.LAST_REPORT_KEY, _saved_rep)

print("18. _add_checkin: user_id rỗng (log rác) không bao giờ khớp nhân viên")
from customize_erpnext.network.biometric.resync import _add_checkin
for v in ("", "  ", None):
    st, msg = _add_checkin(v, NOW, "ZZ Test 1")
    check(f"user_id {v!r} → skipped_no_employee, không ghi", st == "skipped_no_employee", msg)

clear_cache()
_queue_patch.stop()
for _k, _v in _prod_saved.items():
    if _v is None:
        frappe.cache().delete_value(_k)
    else:
        frappe.cache().set_value(_k, _v)
dls._logger = _real_logger
print(f"\n{ok} PASS / {fail} FAIL  (đã xoá cache test)")
