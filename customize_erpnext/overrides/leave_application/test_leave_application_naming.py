"""Kiểm cách đặt tên Leave Application: `LA-YYYY-MM-#####` theo `from_date`.

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/leave_application/test_leave_application_naming.py').read())"

⚠ Test TẠO đơn thật rồi `rollback()`. Không commit gì.

🔴 KHÔNG BAO GIỜ dọn dẹp bằng `delete from tabSeries where name like 'LA-%'`.
Bản đầu của test này làm đúng vậy (kèm `commit()`) vì lúc viết DB chưa có đơn `LA-` nào nên xoá
thấy vô hại. Sau khi import 7.096 đơn thật, mỗi lần chạy test là **xoá sạch bộ đếm production**:
`getseries()` không thấy dòng nào thì phát lại từ 00001, đụng ngay tên đã tồn tại và HR không tạo
được đơn nghỉ nào nữa (`DuplicateEntryError`). `rollback()` là đủ — bộ đếm nằm trong cùng
transaction. PHẦN 5 canh chính điều này.
"""

import frappe
from frappe.utils import add_months, getdate

ok = fail = 0


def check(label, got, want=True):
	global ok, fail
	good = got == want
	ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
	print(f"  {'✅' if good else '❌'} {label:<56} {'' if good else f'{got!r} ← cần {want!r}'}")


def _new(from_date, **kw):
	d = frappe.new_doc("Leave Application")
	d.update({
		"employee": EMP, "leave_type": LT, "company": CO,
		"from_date": from_date, "to_date": from_date, "status": "Open",
		**kw,
	})
	d.flags.ignore_validate = True
	d.flags.ignore_mandatory = True
	d.insert(ignore_permissions=True, ignore_mandatory=True)
	return d


def prefix_of(d):
	"""`LA-2026-03-` — tiền tố bộ đếm ứng với một ngày."""
	return f"LA-{getdate(d).year:04d}-{getdate(d).month:02d}-"


def counter(pfx):
	"""Giá trị bộ đếm hiện tại; 0 nếu tháng đó chưa phát số nào."""
	row = frappe.db.sql("select current from tabSeries where name=%s", (pfx,))
	return int(row[0][0]) if row else 0


def seq(name):
	"""5 chữ số cuối của tên đơn."""
	return int(name.rsplit("-", 1)[1])


def other_month(offset):
	"""Ngày thuộc tháng KHÁC tháng hiện tại — để chứng minh tên không lấy theo ngày chạy test."""
	return add_months(getdate(frappe.utils.nowdate()), offset).replace(day=5)


EMP = frappe.db.get_value("Employee", {"status": "Active"}, "name")
LT = frappe.db.get_value("Leave Type", {"is_earned_leave": 1}, "name")
CO = frappe.db.get_value("Employee", EMP, "company")
before_count = frappe.db.count("Leave Application")
today = frappe.utils.nowdate()

# Ảnh chụp MỌI bộ đếm LA-* trước khi chạy. PHẦN 5 đối chiếu lại để bắt rò rỉ.
series_before = dict(frappe.db.sql("select name, current from tabSeries where name like 'LA-%'"))

try:
	print(f"hôm nay {today} · nhân viên {EMP} · {len(series_before)} bộ đếm LA-* đang có\n")

	print("PHẦN 1 — YYYY-MM lấy từ from_date, KHÔNG phải ngày hôm nay")
	# 🔴 Đây là lý do phải viết autoname() tay: `.YYYY.`/`.MM.` của Frappe lấy theo ngày chạy,
	# nên đơn nghỉ tháng 3 nhập vào tháng 8 sẽ mang số tháng 8 — sai với cách HR tra cứu.
	past, future = other_month(-5), other_month(5)
	check("hai mốc test phải khác tháng hiện tại",
	      today[:7] not in (str(past)[:7], str(future)[:7]))
	n0 = counter(prefix_of(past))
	d1 = _new(past)
	check(f"from_date {past} → {prefix_of(past)}…", d1.name.startswith(prefix_of(past)))
	check("số phát ra = bộ đếm cũ + 1", seq(d1.name), n0 + 1)

	m0 = counter(prefix_of(future))
	d2 = _new(future)
	check(f"from_date {future} → {prefix_of(future)}…", d2.name.startswith(prefix_of(future)))
	check("số phát ra = bộ đếm cũ + 1", seq(d2.name), m0 + 1)

	print("\nPHẦN 2 — mỗi tháng một bộ đếm riêng")
	aug = other_month(4)
	a0 = counter(prefix_of(aug))
	check("tháng khác, đơn thứ nhất", seq(_new(aug).name), a0 + 1)
	check("tháng khác, đơn thứ hai", seq(_new(aug).name), a0 + 2)
	check("tháng đầu vẫn đếm riêng, không bị cộng lây", seq(_new(past).name), n0 + 2)

	print("\nPHẦN 3 — không bao giờ phát trùng tên đã có trong DB")
	# Bẫy thật đã xảy ra: bộ đếm bị xoá → phát lại 00001 → đụng đơn đã tồn tại.
	dup = frappe.db.sql("""
		select count(*) from `tabLeave Application`
		 where name regexp '^LA-[0-9]{4}-[0-9]{2}-[0-9]{5}$'
		 group by left(name, 11), cast(right(name, 5) as unsigned) having count(*) > 1
	""")
	check("không có tên đơn nào trùng", len(dup), 0)
	# ⚠ Bảng dẫn xuất, không phải HAVING với subquery tương quan: MariaDB không cho tham chiếu
	# `la.name` bên trong subquery ở HAVING (`Unknown column ... in 'WHERE'`).
	lag = frappe.db.sql("""
		select t.pfx from (
			select left(name, 11) pfx, max(cast(right(name, 5) as unsigned)) mx
			  from `tabLeave Application`
			 where name regexp '^LA-[0-9]{4}-[0-9]{2}-[0-9]{5}$'
			 group by 1
		) t
		where t.mx > ifnull((select s.current from tabSeries s where s.name = t.pfx), 0)
	""")
	check("mọi bộ đếm >= số lớn nhất đang dùng", [r[0] for r in lag], [])

	print("\nPHẦN 4 — bản amend giữ tên đơn gốc, KHÔNG tiêu số mới")
	# frappe/model/naming.py:177 — nhánh `amended_from` chạy TRƯỚC `run_method("autoname")`
	# rồi `return`, nên autoname của ta không bao giờ chạy cho bản amend.
	may = other_month(-3)
	parent = _new(may)
	after_parent = counter(prefix_of(may))
	frappe.db.sql("update `tabLeave Application` set docstatus=2 where name=%s", (parent.name,))
	amend = frappe.copy_doc(parent)
	amend.amended_from = parent.name
	amend.docstatus = 0
	amend.flags.ignore_validate = True
	amend.flags.ignore_mandatory = True
	amend.insert(ignore_permissions=True, ignore_mandatory=True)
	check("amend = tên gốc + hậu tố", amend.name, parent.name + "-1")
	check("amend không làm bộ đếm nhích lên", counter(prefix_of(may)), after_parent)

	print("\nPHẦN 5 — đơn CŨ và bộ đếm CŨ không bị đụng")
	check("bộ đếm cũ HR-LAP-2026- còn nguyên", bool(frappe.db.exists("Series", "HR-LAP-2026-")))
	kept = frappe.db.sql("""
		select count(*) from `tabLeave Application` where name not like 'LA-%'
	""")[0][0]
	print(f"     {kept} đơn mang tên hệ cũ (không đổi tên hồi tố — đúng yêu cầu)")

finally:
	frappe.db.rollback()
	frappe.clear_cache()
	after = frappe.db.count("Leave Application")
	series_after = dict(frappe.db.sql("select name, current from tabSeries where name like 'LA-%'"))
	print(f"\n     đã rollback · số đơn {before_count} → {after}"
	      f" · bộ đếm {len(series_before)} → {len(series_after)}")
	if after != before_count:
		print("     ❌ RÒ DỮ LIỆU: số đơn thay đổi sau khi rollback")
		fail += 1
	if series_after != series_before:
		lost = set(series_before) - set(series_after)
		moved = {k: (series_before[k], series_after[k])
		         for k in series_before if k in series_after and series_before[k] != series_after[k]}
		print(f"     ❌ HỎNG BỘ ĐẾM production — mất {sorted(lost)} · lệch {moved}")
		print("        HR sẽ không tạo được đơn nghỉ mới (DuplicateEntryError). Xem docstring.")
		fail += 1
	else:
		ok += 1
		print("     ✅ bộ đếm LA-* nguyên vẹn sau khi chạy")

print(f"\n{'=' * 68}\nKẾT QUẢ: {ok} đạt / {fail} lỗi")
