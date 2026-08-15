"""Hồi quy Attendance Request (bổ sung giờ công) — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/overrides/attendance_request/test_regression.py').read())"

Kết thúc bằng frappe.db.rollback() nên KHÔNG để lại dữ liệu. Cố ý không đụng
on_submit/on_cancel đầy đủ: engine tính công có frappe.db.commit() bên trong nên
rollback không cứu được — nhánh dọn dẹp được test riêng qua delete_supplement_checkins().

⚠ Một số assert bám số liệu thật ngày 2026-08-14 (9 ứng viên, 5 ngày đã đủ giờ).
Nếu dữ liệu ngày đó thay đổi thì chỉnh hằng số ở phần 2, đừng sửa code nghiệp vụ.
"""

import frappe
from frappe.utils import getdate

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


def throws(label, fn, expect_substr=None):
    global ok, fail
    try:
        fn()
    except frappe.ValidationError as e:
        if expect_substr and expect_substr.lower() not in str(e).lower():
            fail += 1
            print(f"  FAIL  {label} -> throw sai nội dung: {str(e)[:90]}")
        else:
            ok += 1
            print(f"  PASS  {label} -> chặn đúng: {str(e)[:70]}")
        return
    fail += 1
    print(f"  FAIL  {label} -> KHÔNG throw")


from customize_erpnext.overrides.attendance_request.attendance_request import (
    get_existing_attendance_info, get_attendance_map, get_checkin_map,
)
from customize_erpnext.overrides.attendance_request.bulk_create import (
    get_incomplete_candidates, bulk_create_requests,
)
from customize_erpnext.overrides.attendance_request.confirmation_form import build_pages, _logo_base64

DAY = "2026-08-14"

print("\n=== 1. API đọc (permission-checked) ===")
info = get_existing_attendance_info("TIQN-0148", "2026-08-15", "2026-08-15")
d0 = info["days"][0]
check("get_existing_attendance_info trả đúng ngày", d0["date"] == "2026-08-15", d0["date"])
check("có giờ vào thật", d0["in_time"] == "07:37", str(d0["in_time"]))
check("liệt kê checkin thô", len(d0["checkins"]) >= 1, f"{len(d0['checkins'])} log")
check("khoảng ngày rỗng -> không lỗi", get_existing_attendance_info("TIQN-0148", None, None) == {"days": []})

print("\n=== 2. Dò ca thiếu công ===")
res = get_incomplete_candidates(DAY, DAY)
rows = res["rows"]
check("tìm được ứng viên", len(rows) == 9, f"{len(rows)} dòng")
resolved = [r for r in rows if r["resolved"]]
check("nhận ra ngày đã đủ giờ", len(resolved) == 5, f"{len(resolved)} dòng ĐỦ")
check("dòng ĐỦ không đề xuất giờ",
      all(not r["new_in_time"] and not r["new_out_time"] for r in resolved))
check("dòng ĐỦ bị bỏ tick", all(not r["selected"] for r in resolved))
todo = [r for r in rows if r["selected"]]
check("còn 4 dòng cần xử lý", len(todo) == 4, f"{len(todo)} dòng")
check("mọi dòng cần xử lý đều có đề xuất",
      all(r["new_in_time"] or r["new_out_time"] for r in todo))
canteen = next(r for r in rows if r["employee"] == "TIQN-0351")
check("ca lạ vẫn lấy được giờ từ Shift Type",
      canteen["new_out_time"] == "15:30:00", str(canteen["new_out_time"]))
dbl = next(r for r in rows if r["employee"] == "TIQN-1331")
check("quẹt đúp vẫn kết luận thiếu VÀO", dbl["missing_side"] == "in", str(dbl["missing_side"]))

print("\n=== 3. Tạo hàng loạt (draft) ===")
out = bulk_create_requests(todo, "Forget Check In/Out", None)
check("tạo đủ phiếu", len(out["created"]) == 4 and not out["failed"],
      f"created={len(out['created'])} failed={out['failed']}")
doc = frappe.get_doc("Attendance Request", out["created"][0])
check("phiếu ở trạng thái draft", doc.docstatus == 0)
check("có shift", bool(doc.shift), str(doc.shift))
check("bảng con khớp ngày", len(doc.custom_checkin_details) == 1)
check("cột existing được đổ", doc.custom_checkin_details[0].existing_in_time is not None,
      str(doc.custom_checkin_details[0].existing_in_time))

print("\n=== 4. Validate — các nhánh chặn ===")
def _new(reason="Forget Check In/Out", rows_=None, expl=None):
    d = frappe.new_doc("Attendance Request")
    d.employee = "TIQN-0148"
    d.company = frappe.db.get_value("Employee", "TIQN-0148", "company")
    d.from_date = d.to_date = "2026-08-15"
    d.reason = reason
    d.explanation = expl
    for r in (rows_ or []):
        d.append("custom_checkin_details", r)
    return d

throws("không nhập giờ nào", lambda: _new().run_method("validate"), "at least one")
throws("reason Other thiếu diễn giải",
       lambda: _new("Other", [{"date": "2026-08-15", "new_out_time": "17:00:00"}]).run_method("validate"),
       "explanation")
throws("New In >= New Out",
       lambda: _new(rows_=[{"date": "2026-08-15", "new_in_time": "18:00:00", "new_out_time": "09:00:00"}]).run_method("validate"),
       "earlier than")
throws("New Out sớm hơn giờ vào đã có",
       lambda: _new(rows_=[{"date": "2026-08-15", "new_out_time": "05:00:00"}]).run_method("validate"),
       "later than")
throws("trùng giờ checkin đã có",
       lambda: _new(rows_=[{"date": "2026-08-15", "new_in_time": "07:37:00"}]).run_method("validate"),
       "already exists")

good = _new(rows_=[{"date": "2026-08-15", "new_out_time": "17:00:00"}])
good.run_method("validate")
check("ca hợp lệ qua được validate", True)
check("sync sinh đúng số dòng", len(good.custom_checkin_details) == 1)

multi = _new(rows_=[{"date": "2026-08-15", "new_out_time": "17:00:00"}])
multi.to_date = "2026-08-17"
multi.run_method("validate")
check("mở rộng khoảng ngày -> sinh thêm dòng", len(multi.custom_checkin_details) == 3,
      str([str(r.date) for r in multi.custom_checkin_details]))
check("giữ nguyên giờ đã nhập", str(multi.custom_checkin_details[0].new_out_time) == "17:00:00")
multi.to_date = "2026-08-15"
multi.run_method("validate")
check("thu hẹp khoảng ngày -> bỏ dòng thừa", len(multi.custom_checkin_details) == 1)

print("\n=== 5. Chế độ HRMS gốc không bị đụng ===")
wfh = _new("Work From Home")
check("WFH không vào chế độ bổ sung", wfh.is_supplement is False)
check("banner warnings vẫn chạy ở chế độ gốc", isinstance(wfh.get_attendance_warnings(), list))
sup = _new()
check("supplement tắt banner", sup.get_attendance_warnings() == [])

print("\n=== 6. Dọn dẹp khi Cancel (link phải clear trước) ===")
target = frappe.get_doc("Attendance Request", out["created"][0])
row = target.custom_checkin_details[0]
ci = frappe.new_doc("Employee Checkin")
ci.employee = target.employee
ci.time = f"{row.date} 21:00:00"
ci.log_type = "OUT"
ci.custom_attendance_request = target.name
ci.insert(ignore_permissions=True)
row.db_set("created_checkin_out", ci.name)
check("dựng được checkin gắn phiếu", bool(frappe.db.exists("Employee Checkin", ci.name)))
n = target.delete_supplement_checkins()
check("xoá được, không LinkExistsError", n == 1, f"xoá {n}")
check("checkin đã biến mất", not frappe.db.exists("Employee Checkin", ci.name))
check("link trên bảng con đã clear",
      frappe.db.get_value("Attendance Request Checkin Detail", row.name, "created_checkin_out") is None)

print("\n=== 7. Bản in PDF ===")
pages = build_pages(out["created"])
check("gom theo group", len(pages) == 4, f"{len(pages)} trang")
check("không chừa dòng trống", all("blank_rows" not in p for p in pages))
check("có tên công ty", all(p["company"] for p in pages))
allrows = [r for p in pages for r in p["rows"]]
check("mọi dòng có Chức vụ", all(r["designation"] for r in allrows))
check("giữ được giờ thật khi thiếu VÀO",
      any(r["in_supplemented"] and r["out_time"] for r in allrows))
html = frappe.render_template(
    "customize_erpnext/overrides/attendance_request/confirmation_form.html",
    {"pages": pages, "logo_b64": _logo_base64()})
from frappe.utils.pdf import get_pdf
pdf = get_pdf(html, options={"page-size": "A4", "orientation": "Portrait", "margin-top": "10mm",
                             "margin-bottom": "8mm", "margin-left": "10mm", "margin-right": "10mm",
                             "encoding": "UTF-8"})
check("dựng được PDF", len(pdf) > 50000, f"{len(pdf)} bytes")

print(f"\n{'='*60}\nPASS {ok}   FAIL {fail}\n{'='*60}")
frappe.db.rollback()
print("rolled back — không để lại dữ liệu")
