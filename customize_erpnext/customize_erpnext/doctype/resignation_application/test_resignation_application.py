"""Kiểm `Resignation Application` — đặt tên, validate, sync sang Employee, rút đơn, job 00:00.

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/customize_erpnext/doctype/resignation_application/test_resignation_application.py').read())"

⚠ Test TẠO đơn thật + sửa Employee thật rồi `rollback()`. Không commit gì.

🔴 KHÔNG dọn dẹp bằng `delete from tabSeries where name like 'RA-%'`. Xoá bộ đếm là đơn mới phát
lại từ 00001 và đụng tên đã tồn tại — đúng sự cố đã xảy ra với Leave Application (xem
`scripts/repair_leave_application_series.sql`). `rollback()` là đủ. PHẦN 7 canh chính điều này.
"""

import frappe
from frappe.utils import add_days, getdate

from customize_erpnext.customize_erpnext.doctype.resignation_application.resignation_application import (
	HANDOVER_FIELDS,
	withdraw,
)

ok = fail = 0


def check(label, got, want=True):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<58} {'' if good else f'{got!r} ← cần {want!r}'}")


def throws(label, fn, fragment=None):
	"""Gọi `fn` và kỳ vọng nó throw. `fragment` = một mẩu chuỗi phải có trong thông báo."""
	global ok, fail
	try:
		fn()
	except Exception as e:
		msg = str(e)
		good = (fragment.lower() in msg.lower()) if fragment else True
		ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
		print(f"  {'✅' if good else '❌'} {label:<58} {'' if good else f'throw nhưng sai nội dung: {msg[:80]}'}")
		return
	fail += 1
	print(f"  ❌ {label:<58} lẽ ra phải throw nhưng không")


def counter(pfx):
	row = frappe.db.sql("select current from tabSeries where name=%s", (pfx,))
	return int(row[0][0]) if row else 0


def seq(name):
	return int(name.rsplit("-", 1)[1])


def new_app(**kw):
	d = frappe.new_doc("Resignation Application")
	d.update({
		"employee": EMP,
		"resignation_letter_date": POSTING,
		"relieving_date": RELIEVING,
		"reason_for_leaving_group": GROUP,
		"reason_for_leaving_group_2": REASON,
		**kw,
	})
	d.insert(ignore_permissions=True)
	return d


def emp_snapshot():
	return frappe.db.get_value(
		"Employee", EMP,
		["status", "relieving_date", "resignation_letter_date",
		 "custom_reason_for_leaving_group", "custom_reason_for_leaving_group_2",
		 "reason_for_leaving"],
		as_dict=True,
	)


# Nhân viên Active, chưa có relieving_date, không ai reports_to (tránh vướng validate_status
# của core khi test job 00:00).
EMP = frappe.db.sql("""
	SELECT e.name FROM tabEmployee e
	WHERE e.status = 'Active' AND e.relieving_date IS NULL
	  AND NOT EXISTS (SELECT 1 FROM tabEmployee s WHERE s.reports_to = e.name AND s.status = 'Active')
	ORDER BY e.name LIMIT 1
""", pluck=True)[0]
GROUP = frappe.db.get_value("Resignation Reason Group", {"is_active": 1}, "name")
# Sau đợt rename 21/08: field của doctype danh mục TRÙNG TÊN với field của đơn, nên không
# còn cái bẫy "khoá filter khác tên vế phải" nữa.
REASON = frappe.db.get_value(
	"Resignation Reason Group 2", {"reason_for_leaving_group": GROUP, "is_active": 1}, "name"
)
DOJ = frappe.db.get_value("Employee", EMP, "date_of_joining")

POSTING = frappe.utils.nowdate()
RELIEVING = add_days(POSTING, 45)

before_emp = emp_snapshot()
series_before = dict(frappe.db.sql("select name, current from tabSeries where name like 'RA-%'"))

try:
	print(f"nhân viên {EMP} · vào làm {DOJ} · lý do {GROUP} / {REASON}\n")

	print("PHẦN 1 — đặt tên RA-YYYY-MM-##### theo resignation_letter_date")
	# `.YYYY.`/`.MM.` của Frappe lấy theo NGÀY CHẠY, nên đơn nhận tháng 3 nhập vào tháng 8 sẽ
	# mang số tháng 8. Đó là lý do phải tự viết autoname().
	past = add_days(POSTING, -160)          # chắc chắn khác tháng hiện tại
	pfx = f"RA-{getdate(past).year:04d}-{getdate(past).month:02d}-"
	n0 = counter(pfx)
	d1 = new_app(resignation_letter_date=past, relieving_date=add_days(past, 45))
	check(f"resignation_letter_date {past} → {pfx}…", d1.name.startswith(pfx))
	check("số phát ra = bộ đếm cũ + 1", seq(d1.name), n0 + 1)
	check("KHÔNG lấy theo tháng hôm nay", d1.name.startswith(f"RA-{POSTING[:7].replace('-', '-')}-"), False)
	d1.delete()

	print("\nPHẦN 2 — validate")
	throws("ngày nghỉ TRƯỚC ngày vào làm → chặn",
	       lambda: new_app(relieving_date=add_days(DOJ, -1)), "Relieving Date")
	# Vào làm rồi bỏ ngay hôm đó — có thật, 3 hồ sơ trong file import của HR.
	same_day = new_app(resignation_letter_date=DOJ, relieving_date=DOJ)
	check("nghỉ ĐÚNG ngày vào làm → cho phép", bool(same_day.name))
	same_day.delete()
	# Nghỉ ngang: ngày nghỉ có trước, quyết định có sau — hợp lệ, chỉ cảnh báo.
	ok_late = new_app(resignation_letter_date=add_days(RELIEVING, 14))
	check("đơn lập sau ngày nghỉ 14 ngày → VẪN LƯU ĐƯỢC", bool(ok_late.name))
	check("notice_days âm", ok_late.notice_days, -14)
	ok_late.delete()
	throws("lệch quá 30 ngày → chặn (gần như chắc chắn gõ nhầm năm)",
	       lambda: new_app(resignation_letter_date=add_days(RELIEVING, 31)),
	       "almost always a typo")

	other_group = frappe.db.get_value(
		"Resignation Reason Group", {"name": ("!=", GROUP), "is_active": 1}, "name")
	if other_group:
		throws("lý do không thuộc nhóm đã chọn → chặn",
		       lambda: new_app(reason_for_leaving_group=other_group), "group")
	else:
		print("     ⏭ bỏ qua: danh mục chỉ có 1 nhóm")

	print("\nPHẦN 3 — notice_days + handover_progress")
	d = new_app()
	check("notice_days = hiệu hai ngày", d.notice_days, 45)
	check("handover_progress khi chưa tick gì", d.handover_progress, f"0/{len(HANDOVER_FIELDS)}")
	d.handover_id_card = 1
	d.handover_uniform = 1
	d.save()
	check("handover_progress đếm đúng", d.handover_progress, f"2/{len(HANDOVER_FIELDS)}")
	# Bàn giao xảy ra SAU khi duyệt (những ngày làm việc cuối) nên mọi field của mục này phải
	# sửa được trên đơn đã submit — kể cả file đính kèm.
	meta_ra = frappe.get_meta("Resignation Application")
	not_editable = [f.fieldname for f in meta_ra.fields
	                if f.fieldname.startswith("handover") and not f.allow_on_submit]
	check("mọi field handover đều allow_on_submit", not_editable, [])
	check("có field đính kèm kiểu Attach",
	      meta_ra.get_field("handover_attachment").fieldtype, "Attach")

	print("\nPHẦN 4 — SUBMIT: ghi relieving_date + lý do, KHÔNG đụng status")
	# 🔴 Đây là điểm mấu chốt. Đổi status = Left ngay lúc duyệt thì 45 ngày còn lại nhân viên
	# mất chấm công (shift_type_optimized bỏ qua NV Left) và bị xếp vào diện xoá vân tay.
	d.submit()
	after = emp_snapshot()
	check("Employee.relieving_date đã ghi", str(after.relieving_date), str(getdate(RELIEVING)))
	check("Employee.resignation_letter_date = resignation_letter_date của đơn",
	      str(after.resignation_letter_date), str(getdate(POSTING)))
	check("Employee nhóm lý do đã ghi", after.custom_reason_for_leaving_group, GROUP)
	check("Employee lý do đã ghi", after.custom_reason_for_leaving_group_2, REASON)
	check("🔴 Employee.status VẪN Active", after.status, "Active")

	print("\nPHẦN 5 — đơn thứ hai cho cùng người bị chặn")
	throws("đã có đơn submitted → chặn đơn mới", lambda: new_app(), "already has a submitted")

	print("\nPHẦN 6 — WITHDRAW: hoàn nguyên Employee")
	withdraw(d.name, POSTING, "test rút đơn")
	d.reload()
	check("đơn về docstatus 2", d.docstatus, 2)
	check("có withdrawal_date", str(getdate(d.withdrawal_date)), str(getdate(POSTING)))
	rev = emp_snapshot()
	check("relieving_date đã xoá", rev.relieving_date, None)
	check("resignation_letter_date đã xoá", rev.resignation_letter_date, None)
	check("nhóm lý do đã xoá", rev.custom_reason_for_leaving_group, None)
	check("lý do đã xoá", rev.custom_reason_for_leaving_group_2, None)
	check("status vẫn Active", rev.status, "Active")

	print("     — rút rồi thì nộp lại được")
	d2 = new_app()
	d2.submit()
	check("đơn mới submit được sau khi rút", d2.docstatus, 1)

	print("\n     — HR sửa tay sau khi duyệt thì rút đơn KHÔNG được xoá đè")
	# Chỉ xoá field nào CÒN đúng giá trị đơn này đã ghi.
	manual = add_days(RELIEVING, 10)
	frappe.db.set_value("Employee", EMP, "relieving_date", manual)
	withdraw(d2.name, POSTING, "test không đè")
	check("giữ nguyên giá trị HR đã sửa tay",
	      str(frappe.db.get_value("Employee", EMP, "relieving_date")), str(getdate(manual)))

	print("\nPHẦN 7 — job 00:00 auto_mark_employees_as_left")
	from customize_erpnext.overrides.employee import employee as emp_mod
	import inspect

	src = inspect.getsource(emp_mod.auto_mark_employees_as_left)
	check("dùng business_today(), không phải today()", "business_today()" in src)
	check("có lọc status = Active", '["status", "=", "Active"]' in src)
	check("không commit() trong vòng lặp", "frappe.db.commit()" not in src)
	# 🔴 KHÔNG được dùng doc.save(): 796 nhân viên Active mang custom_driving_license='0'
	# (không hợp lệ so với options) nên mọi save() đều throw và job im lặng bỏ sót họ.
	# Bỏ docstring trước khi dò: docstring cố tình NHẮC "doc.save()" để giải thích vì sao không
	# dùng, tìm mù trong cả source sẽ dương tính giả.
	body = src.split('"""')[2] if src.count('"""') >= 2 else src
	check("không dùng doc.save() trên Employee", "doc.save(" not in body)

	frappe.db.set_value("Employee", EMP, "relieving_date", add_days(frappe.utils.nowdate(), -1))
	res = emp_mod.auto_mark_employees_as_left()
	check("nhân viên tới hạn được chuyển Left", EMP in res["updated"])
	check("Employee.status = Left", frappe.db.get_value("Employee", EMP, "status"), "Left")

	res2 = emp_mod.auto_mark_employees_as_left()
	check("chạy lại KHÔNG đụng người đã Left", EMP in res2["updated"], False)
	# 1.388 người đã Left mà bản cũ vẫn UPDATE mỗi đêm, bump `modified` của từng người.
	check("lượt hai không đụng ai", len(res2["updated"]), 0)

	print("\n     — người còn cấp dưới Active thì bỏ qua, không phải báo lỗi")
	boss = frappe.db.sql("""
		SELECT e.name FROM tabEmployee e
		WHERE e.status = 'Active' AND e.relieving_date IS NULL
		  AND EXISTS (SELECT 1 FROM tabEmployee s WHERE s.reports_to = e.name AND s.status = 'Active')
		LIMIT 1
	""", pluck=True)
	if boss:
		frappe.db.set_value("Employee", boss[0], "relieving_date", add_days(frappe.utils.nowdate(), -1))
		res3 = emp_mod.auto_mark_employees_as_left()
		check("còn cấp dưới → vào danh sách skipped",
		      any(r["employee"] == boss[0] for r in res3["skipped"]))
		check("còn cấp dưới → KHÔNG bị đổi status",
		      frappe.db.get_value("Employee", boss[0], "status"), "Active")
		check("còn cấp dưới → KHÔNG tính là lỗi",
		      any(r["employee"] == boss[0] for r in res3["errors"]), False)
	else:
		print("     ⏭ bỏ qua: không có ai đang có cấp dưới Active")

	print("\n     — dữ liệu cũ không hợp lệ vẫn phải chuyển được")
	# Đây là ca đã làm hỏng bản dùng doc.save().
	dirty = frappe.db.sql("""
		SELECT e.name FROM tabEmployee e
		WHERE e.status = 'Active' AND e.relieving_date IS NULL AND e.custom_driving_license = '0'
		  AND NOT EXISTS (SELECT 1 FROM tabEmployee s WHERE s.reports_to = e.name AND s.status = 'Active')
		LIMIT 1
	""", pluck=True)
	if dirty:
		frappe.db.set_value("Employee", dirty[0], "relieving_date", add_days(frappe.utils.nowdate(), -1))
		res4 = emp_mod.auto_mark_employees_as_left()
		check(f"{dirty[0]} (driving_license='0') vẫn chuyển được", dirty[0] in res4["updated"])
	else:
		print("     ⏭ bỏ qua: không còn hồ sơ nào dính lỗi đó")

	print("\nPHẦN 8 — ngày nghỉ ĐÃ QUA thì submit là chuyển Left ngay, không đợi job")
	# Nhập đơn lùi ngày (người đã nghỉ rồi) mà bắt HR đợi tới nửa đêm mới thấy đúng trạng thái
	# là vô nghĩa — lý do phải đợi (giữ ngày công) không còn đúng khi ngày nghỉ đã qua.
	back = frappe.db.sql("""
		SELECT e.name FROM tabEmployee e
		WHERE e.status = 'Active' AND e.relieving_date IS NULL
		  AND NOT EXISTS (SELECT 1 FROM tabEmployee s WHERE s.reports_to = e.name AND s.status = 'Active')
		  AND e.name <> %s
		ORDER BY e.name LIMIT 1
	""", (EMP,), pluck=True)[0]

	d3 = frappe.new_doc("Resignation Application")
	d3.update({
		"employee": back,
		"resignation_letter_date": add_days(frappe.utils.nowdate(), -10),
		"relieving_date": add_days(frappe.utils.nowdate(), -3),
		"reason_for_leaving_group": GROUP, "reason_for_leaving_group_2": REASON,
	})
	d3.insert(ignore_permissions=True)
	check("trước submit vẫn Active", frappe.db.get_value("Employee", back, "status"), "Active")
	d3.submit()
	check("🔴 submit đơn lùi ngày → Left NGAY", frappe.db.get_value("Employee", back, "status"), "Left")

	print("     — rút đơn thì mở lại")
	withdraw(d3.name, frappe.utils.nowdate(), "test")
	check("rút đơn → về Active", frappe.db.get_value("Employee", back, "status"), "Active")
	check("relieving_date đã xoá", frappe.db.get_value("Employee", back, "relieving_date"), None)

	print("     — ngày nghỉ TƯƠNG LAI thì vẫn KHÔNG đụng status")
	d4 = frappe.new_doc("Resignation Application")
	d4.update({
		"employee": back, "resignation_letter_date": frappe.utils.nowdate(),
		"relieving_date": add_days(frappe.utils.nowdate(), 30),
		"reason_for_leaving_group": GROUP, "reason_for_leaving_group_2": REASON,
	})
	d4.insert(ignore_permissions=True)
	d4.submit()
	check("ngày nghỉ tương lai → status giữ Active",
	      frappe.db.get_value("Employee", back, "status"), "Active")

	print("\n     — hai đường vào dùng CHUNG một hàm")
	import inspect as _i
	from customize_erpnext.customize_erpnext.doctype.resignation_application import (
		resignation_application as ra_mod,
	)
	check("đường của đơn gọi mark_employee_left",
	      "mark_employee_left(" in _i.getsource(ra_mod._reconcile_status))
	check("sync_to_employee đi qua _reconcile_status",
	      "_reconcile_status(" in _i.getsource(ra_mod.sync_to_employee))
	check("job 00:00 cũng gọi mark_employee_left",
	      "mark_employee_left(" in _i.getsource(emp_mod.auto_mark_employees_as_left))

	print("\nPHẦN 9 — SỬA NGÀY NGHỈ SAU KHI DUYỆT (hai bên thoả thuận lại)")
	# Đơn là nguồn, Employee là bản sao. Sửa trên đơn phải đẩy sang hồ sơ, và trạng thái phải
	# đối chiếu lại theo CẢ HAI hướng.
	who = frappe.db.sql("""
		SELECT e.name FROM tabEmployee e
		WHERE e.status='Active' AND e.relieving_date IS NULL
		  AND NOT EXISTS (SELECT 1 FROM `tabResignation Application` r WHERE r.employee=e.name)
		  AND NOT EXISTS (SELECT 1 FROM tabEmployee s WHERE s.reports_to=e.name AND s.status='Active')
		LIMIT 1
	""", pluck=True)[0]

	d6 = frappe.new_doc("Resignation Application")
	d6.update({"employee": who, "resignation_letter_date": frappe.utils.nowdate(),
	           "relieving_date": add_days(frappe.utils.nowdate(), 20),
	           "reason_for_leaving_group": GROUP, "reason_for_leaving_group_2": REASON})
	d6.insert(ignore_permissions=True)
	d6.submit()
	check("ngày tương lai → Employee còn Active",
	      frappe.db.get_value("Employee", who, "status"), "Active")

	print("     — dời ngày sớm hơn, về ĐÚNG HÔM NAY")
	# Không lùi hẳn về quá khứ được: luật `resignation_letter_date <= relieving_date` chặn, mà resignation_letter_date
	# là hôm nay. Chính luật này cũng đang chặn 124 dòng import — xem mục "Bẫy" trong .md.
	d6.relieving_date = frappe.utils.nowdate()
	d6.save()
	e6 = frappe.db.get_value("Employee", who, ["status", "relieving_date"], as_dict=True)
	check("Employee.relieving_date đi theo đơn",
	      str(e6.relieving_date), str(getdate(frappe.utils.nowdate())))
	check("🔴 ngày đã tới → chuyển Left", e6.status, "Left")
	check("notice_days tính lại", d6.notice_days, 0)

	print("     — thoả thuận lại, ĐẨY NGÀY RA TƯƠNG LAI")
	# Không mở lại thì những ngày còn đi làm đó không sinh chấm công (engine bỏ qua NV Left).
	d6.reload()
	d6.relieving_date = add_days(frappe.utils.nowdate(), 15)
	d6.save()
	e6 = frappe.db.get_value("Employee", who, ["status", "relieving_date"], as_dict=True)
	check("🔴 ngày lùi ra tương lai → MỞ LẠI Active", e6.status, "Active")
	check("Employee.relieving_date đi theo đơn",
	      str(e6.relieving_date), str(getdate(add_days(frappe.utils.nowdate(), 15))))

	print("     — validate vẫn chạy trên đường update-after-submit")
	d6.reload()
	d6.relieving_date = add_days(frappe.db.get_value("Employee", who, "date_of_joining"), -1)
	throws("ngày nghỉ trước ngày vào làm → vẫn chặn", d6.save, "Relieving Date")
	d6.reload()

	print("     — KHÔNG có chiều ngược: sửa tay Employee thì đơn giữ nguyên")
	frappe.db.set_value("Employee", who, "relieving_date", add_days(frappe.utils.nowdate(), 99))
	check("đơn không đổi theo Employee",
	      str(frappe.db.get_value("Resignation Application", d6.name, "relieving_date")),
	      str(getdate(add_days(frappe.utils.nowdate(), 15))))

	print("\nPHẦN 10 — link ngược virtual trên Employee")
	F = "custom_resignation_application"
	meta_f = frappe.get_meta("Employee").get_field(F)
	check("field tồn tại và là virtual", bool(meta_f) and bool(meta_f.is_virtual))
	# Không có cột trong DB — đó là điểm mấu chốt, đừng để ai vô tình biến nó thành cột thật.
	col = frappe.db.sql("""SELECT COUNT(*) FROM information_schema.COLUMNS
	                       WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tabEmployee'
	                         AND COLUMN_NAME=%s""", (F,))[0][0]
	check("KHÔNG sinh cột trong tabEmployee", col, 0)

	back2 = frappe.db.sql("""
		SELECT e.name FROM tabEmployee e
		WHERE e.status='Active' AND e.relieving_date IS NULL
		  AND NOT EXISTS (SELECT 1 FROM `tabResignation Application` r WHERE r.employee=e.name)
		  AND NOT EXISTS (SELECT 1 FROM tabEmployee s WHERE s.reports_to=e.name AND s.status='Active')
		LIMIT 1
	""", pluck=True)[0]
	check("chưa có đơn → trống", getattr(frappe.get_doc("Employee", back2), F), None)

	d5 = frappe.new_doc("Resignation Application")
	d5.update({"employee": back2, "resignation_letter_date": frappe.utils.nowdate(),
	           "relieving_date": add_days(frappe.utils.nowdate(), 30),
	           "reason_for_leaving_group": GROUP, "reason_for_leaving_group_2": REASON})
	d5.insert(ignore_permissions=True)
	check("đơn còn Draft → vẫn trống", getattr(frappe.get_doc("Employee", back2), F), None)

	d5.submit()
	check("đơn đã submit → hiện tên đơn", getattr(frappe.get_doc("Employee", back2), F), d5.name)
	# ⚠ Phải kiểm bằng `as_dict()` — đó là đường form desk và `savedocs` thật sự đi qua.
	# `doc.get(F)` LUÔN trả None với field ảo vì nó đọc `__dict__`, không chạm tới property.
	check("as_dict() (đường UI) trả đúng tên đơn",
	      frappe.get_doc("Employee", back2).as_dict().get(F), d5.name)
	check("as_dict(no_nulls) (đường savedocs) cũng đúng",
	      frappe.get_doc("Employee", back2).as_dict(no_nulls=True).get(F), d5.name)

	withdraw(d5.name, frappe.utils.nowdate(), "test")
	check("rút đơn → trống trở lại", getattr(frappe.get_doc("Employee", back2), F), None)

finally:
	frappe.db.rollback()
	frappe.clear_cache()
	after_emp = emp_snapshot()
	series_after = dict(frappe.db.sql("select name, current from tabSeries where name like 'RA-%'"))
	print(f"\n     đã rollback · Employee {EMP}: {before_emp.status} → {after_emp.status}")
	if after_emp != before_emp:
		print(f"     ❌ RÒ DỮ LIỆU: Employee đổi sau rollback\n        trước {before_emp}\n        sau   {after_emp}")
		fail += 1
	if series_after != series_before:
		print(f"     ❌ HỎNG BỘ ĐẾM: {series_before} → {series_after}")
		fail += 1
	else:
		ok += 1
		print("     ✅ bộ đếm RA-* nguyên vẹn")

print(f"\n{'=' * 70}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
