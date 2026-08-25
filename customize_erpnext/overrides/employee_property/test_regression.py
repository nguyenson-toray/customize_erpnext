"""Hồi quy Employee Promotion / Employee Transfer override — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/overrides/employee_property/test_regression.py').read())"

Kết thúc bằng frappe.db.rollback() nên KHÔNG để lại dữ liệu.

⚠ Phần 3 trở đi cần override_doctype_class đã có hiệu lực -> phải `bench restart`
trước khi chạy. Phần 1-2 chỉ gọi hàm thuần nên chạy được ngay.
"""

import frappe
from frappe.utils import add_days, getdate

from customize_erpnext.overrides.employee_property import work_history
from customize_erpnext.overrides.employee_property.work_history import (
	ALLOWED_FIELDS,
	HISTORY_FIELDS,
	baseline_state,
	build_timeline,
	collect_events,
	rebuild_work_history,
	state_at,
)

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


# ----------------------------------------------------------------------------------
# dữ liệu mượn từ site
# ----------------------------------------------------------------------------------
# NV test phải CHƯA có phiếu thuyên chuyển/thăng chức nào, nếu không timeline dựng ra
# sẽ lẫn sự kiện thật của site và các assert đếm số dòng sẽ lệch.
_busy = {
	d.employee
	for doctype in ("Employee Transfer", "Employee Promotion")
	for d in frappe.get_all(doctype, fields=["employee"])
}
EMP = next(
	d.name
	for d in frappe.get_all(
		"Employee",
		filters={"status": "Active", "date_of_joining": ("<", "2023-01-01")},
		fields=["name"],
		order_by="name",
	)
	if d.name not in _busy
)
DEPARTMENTS = [d.name for d in frappe.get_all("Department", limit=3, order_by="name")]
DESIGNATIONS = [d.name for d in frappe.get_all("Designation", limit=2, order_by="name")]
GROUPS = [g.name for g in frappe.get_all("Group", limit=1, order_by="name")]

print(f"\nEmployee test: {EMP} | departments: {DEPARTMENTS} | designations: {DESIGNATIONS} | groups: {GROUPS}")
assert EMP and len(DEPARTMENTS) >= 3 and len(DESIGNATIONS) >= 2 and GROUPS, "site thiếu dữ liệu master để test"

JOIN = getdate(frappe.db.get_value("Employee", EMP, "date_of_joining"))
D1 = add_days(JOIN, 400)
D2 = add_days(JOIN, 800)


def make_transfer(date, changes, submit=True, fill_current=False):
	"""changes = {fieldname: new}. fill_current=False -> để override tự điền `current`."""
	doc = frappe.new_doc("Employee Transfer")
	doc.employee = EMP
	doc.transfer_date = date
	for fieldname, new in changes.items():
		doc.append("transfer_details", {"fieldname": fieldname, "new": new})
	doc.insert()
	if submit:
		doc.submit()
	return doc.reload() or doc


# ----------------------------------------------------------------------------------
print("\n=== 1. Hàm thuần: timeline dựng từ events ===")
# ----------------------------------------------------------------------------------
employee = frappe.get_doc("Employee", EMP)
fake_events = [
	{
		"doctype": "Employee Transfer",
		"name": "T1",
		"event_date": D1,
		"creation": getdate(D1),
		"changes": {"department": {"current": DEPARTMENTS[0], "new": DEPARTMENTS[1]}},
	},
	{
		"doctype": "Employee Transfer",
		"name": "T2",
		"event_date": D2,
		"creation": getdate(D2),
		"changes": {"department": {"current": DEPARTMENTS[1], "new": DEPARTMENTS[2]}},
	},
]

base = baseline_state(employee, fake_events)
check("baseline lấy `current` của event ĐẦU TIÊN, không lấy giá trị hôm nay",
	base["department"] == DEPARTMENTS[0], f"-> {base['department']}")

final = state_at(employee, fake_events)
check("state cuối = `new` của event mới nhất",
	final["department"] == DEPARTMENTS[2], f"-> {final['department']}")

mid = state_at(employee, fake_events, upto=(D2, getdate(D2)))
check("state ngay trước D2 = giá trị của D1",
	mid["department"] == DEPARTMENTS[1], f"-> {mid['department']}")

rows = build_timeline(employee, fake_events)
check("timeline có 3 dòng (seed + 2 sự kiện)", len(rows) == 3, f"-> {len(rows)}")
check("dòng seed bắt đầu từ date_of_joining", rows[0]["from_date"] == JOIN, f"-> {rows[0]['from_date']}")
check("dòng seed mang giá trị GỐC", rows[0]["department"] == DEPARTMENTS[0])
check("to_date nối liền mạch, không hở ngày",
	rows[0]["to_date"] == add_days(D1, -1) and rows[1]["to_date"] == add_days(D2, -1),
	f"-> {rows[0]['to_date']} / {rows[1]['to_date']}")
check("dòng cuối để mở (NV chưa nghỉ)", rows[-1]["to_date"] is None)

# NV đã nghỉ: to_date của dòng cuối = relieving_date - 1 (relieving_date là ngày ĐÃ nghỉ)
left = frappe.get_doc("Employee", EMP)
left.relieving_date = add_days(D2, 30)
check("NV có relieving_date -> to_date = relieving_date - 1",
	build_timeline(left, fake_events)[-1]["to_date"] == add_days(D2, 29),
	f"-> {build_timeline(left, fake_events)[-1]['to_date']} (relieving {left.relieving_date})")

# Thuyên chuyển đúng ngày nghỉ việc: không được sinh from_date > to_date
left.relieving_date = D2
edge = build_timeline(left, fake_events)[-1]
check("chuyển đúng ngày nghỉ -> to_date không lùi trước from_date",
	edge["to_date"] >= edge["from_date"], f"-> {edge['from_date']} .. {edge['to_date']}")
left.relieving_date = None
check("mọi cột HISTORY_FIELDS đều có mặt", all(f in rows[0] for f in HISTORY_FIELDS))

# Sự kiện chỉ đổi reports_to thì không sinh dòng lịch sử (bảng không có cột đó)
only_reports_to = [
	{
		"doctype": "Employee Promotion",
		"name": "P1",
		"event_date": D1,
		"creation": getdate(D1),
		"changes": {"reports_to": {"current": None, "new": EMP}},
	}
]
check("đổi mỗi reports_to -> không thêm dòng work history",
	len(build_timeline(employee, only_reports_to)) == 1)

# Hai doc cùng ngày gộp làm một dòng
same_day = fake_events + [
	{
		"doctype": "Employee Promotion",
		"name": "P2",
		"event_date": D2,
		"creation": getdate(add_days(D2, 1)),
		"changes": {"designation": {"current": DESIGNATIONS[0], "new": DESIGNATIONS[1]}},
	}
]
merged = build_timeline(employee, same_day)
check("2 doc cùng ngày gộp thành 1 dòng", len(merged) == 3, f"-> {len(merged)}")
check("dòng gộp giữ trạng thái CUỐI của ngày đó",
	merged[-1]["department"] == DEPARTMENTS[2] and merged[-1]["designation"] == DESIGNATIONS[1])

# ----------------------------------------------------------------------------------
print("\n=== 2. rebuild trên dữ liệu thật (rollback sau đó) ===")
# ----------------------------------------------------------------------------------
has_doc = frappe.db.get_value("Employee Promotion", {"docstatus": 1}, ["name", "employee"], as_dict=True)
if has_doc:
	before = frappe.db.get_value("Employee", has_doc.employee, ALLOWED_FIELDS, as_dict=True)
	rebuild_work_history(has_doc.employee)
	rebuild_work_history(has_doc.employee)  # idempotent: chạy 2 lần phải ra y hệt
	after = frappe.db.get_value("Employee", has_doc.employee, ALLOWED_FIELDS, as_dict=True)
	check("rebuild 2 lần không làm trôi giá trị Employee", before == after, f"{before} vs {after}")
	timeline = frappe.get_all(
		"Employee Internal Work History",
		filters={"parent": has_doc.employee, "parenttype": "Employee"},
		fields=["from_date", "to_date", "department"],
		order_by="idx",
		parent_doctype="Employee",
	)
	check("rebuild sinh timeline không rỗng", bool(timeline), f"-> {len(timeline)} dòng")
else:
	print("  SKIP  site chưa có Employee Promotion đã submit")

# ----------------------------------------------------------------------------------
print("\n=== 3. Vòng đời doc (CẦN bench restart trước) ===")
# ----------------------------------------------------------------------------------
from frappe.model.base_document import get_controller

active_override = get_controller("Employee Transfer").__name__ == "CustomEmployeeTransfer"
check("override_doctype_class đã có hiệu lực", active_override,
	"" if active_override else "-> chạy `bench restart` rồi chạy lại file này")

if active_override:
	orig = frappe.db.get_value("Employee", EMP, ALLOWED_FIELDS, as_dict=True)

	# Import ĐẢO thứ tự: doc mới nhất vào trước, doc cũ vào sau.
	t2 = make_transfer(D2, {"department": DEPARTMENTS[2]})
	t1 = make_transfer(D1, {"department": DEPARTMENTS[1]})

	check("import đảo thứ tự vẫn ra giá trị của doc MỚI NHẤT",
		frappe.db.get_value("Employee", EMP, "department") == DEPARTMENTS[2],
		f"-> {frappe.db.get_value('Employee', EMP, 'department')}")

	t1.reload()
	check("`current` được tự điền từ timeline, không phải giá trị hôm nay",
		t1.transfer_details[0].current == orig["department"],
		f"-> {t1.transfer_details[0].current} (gốc {orig['department']})")
	check("`property` được tự điền nhãn field",
		t1.transfer_details[0].property == "Department",
		f"-> {t1.transfer_details[0].property}")

	rows = frappe.get_all(
		"Employee Internal Work History",
		filters={"parent": EMP, "parenttype": "Employee"},
		fields=["from_date", "to_date", "department"],
		order_by="idx",
		parent_doctype="Employee",
	)
	check("timeline 3 dòng theo đúng thứ tự ngày", len(rows) == 3, f"-> {len(rows)}")
	check("thứ tự ngày tăng dần bất kể thứ tự nhập",
		[r.from_date for r in rows] == sorted(r.from_date for r in rows))

	# Huỷ doc mới nhất -> quay về giá trị của doc trước đó
	t2.reload()
	t2.cancel()
	check("huỷ doc mới nhất -> Employee về giá trị doc trước",
		frappe.db.get_value("Employee", EMP, "department") == DEPARTMENTS[1],
		f"-> {frappe.db.get_value('Employee', EMP, 'department')}")

	# Huỷ nốt doc còn lại -> về giá trị gốc
	t1.reload()
	t1.cancel()
	check("huỷ hết -> Employee về giá trị gốc ban đầu",
		frappe.db.get_value("Employee", EMP, "department") == orig["department"],
		f"-> {frappe.db.get_value('Employee', EMP, 'department')}")

	# Import kiểu file của HR: chỉ có cột Property (label), không có Field Name
	doc = frappe.new_doc("Employee Transfer")
	doc.employee = EMP
	doc.transfer_date = D1
	doc.append("transfer_details", {"property": "Group", "new": GROUPS[0]})
	doc.append("transfer_details", {"property": "Desination", "new": DESIGNATIONS[1]})
	doc.insert()
	check("label 'Group' -> custom_group", doc.transfer_details[0].fieldname == "custom_group",
		f"-> {doc.transfer_details[0].fieldname}")
	check("label sai chính tả 'Desination' -> designation",
		doc.transfer_details[1].fieldname == "designation", f"-> {doc.transfer_details[1].fieldname}")

	def unknown_property():
		bad = frappe.new_doc("Employee Transfer")
		bad.employee = EMP
		bad.transfer_date = D1
		bad.append("transfer_details", {"property": "Bank A/C No.", "new": "123"})
		bad.insert()

	throws("property không map được thì THROW chứ không submit thành no-op",
		unknown_property, "cannot tell which employee field")

	def noop_row():
		bad = frappe.new_doc("Employee Transfer")
		bad.employee = EMP
		bad.transfer_date = D1
		bad.append("transfer_details", {"fieldname": "custom_group",
			"current": GROUPS[0], "new": GROUPS[0]})
		bad.insert()

	throws("dòng current == new (không đổi gì) bị chặn", noop_row, "nothing would change")

	def noop_row_case():
		bad = frappe.new_doc("Employee Transfer")
		bad.employee = EMP
		bad.transfer_date = D1
		bad.append("transfer_details", {"fieldname": "custom_group",
			"current": GROUPS[0].lower(), "new": GROUPS[0]})
		bad.insert()

	throws("chỉ khác hoa/thường vẫn là không đổi gì", noop_row_case, "nothing would change")

	def bad_link():
		bad = frappe.new_doc("Employee Transfer")
		bad.employee = EMP
		bad.transfer_date = D1
		bad.append("transfer_details", {"fieldname": "custom_group", "new": "Trainee-khong-ton-tai"})
		bad.insert()

	throws("giá trị `new` không có trong doctype đích thì chặn ngay trên phiếu",
		bad_link, "does not exist in")

	# Field ngoài allow-list bị chặn
	throws(
		"field ngoài allow-list bị chặn",
		lambda: make_transfer(D1, {"bank_ac_no": "123"}, submit=False),
		"cannot be changed",
	)

	# Cờ ENFORCE_EFFECTIVE_DATE_NOT_FUTURE
	future = add_days(getdate(), 30)
	throws("cờ BẬT (mặc định) -> phiếu ngày tương lai bị chặn như HRMS gốc",
		lambda: make_transfer(future, {"department": DEPARTMENTS[1]}),
		"cannot be submitted before")

	import customize_erpnext.overrides.employee_property.employee_transfer as et
	work_history.ENFORCE_EFFECTIVE_DATE_NOT_FUTURE = False
	et.ENFORCE_EFFECTIVE_DATE_NOT_FUTURE = False
	try:
		doc = make_transfer(future, {"department": DEPARTMENTS[1]})
		check("cờ TẮT -> phiếu ngày tương lai submit được", doc.docstatus == 1)
		check("⚠ phiếu tương lai ăn vào Employee master NGAY, không đợi tới ngày",
			frappe.db.get_value("Employee", EMP, "department") == DEPARTMENTS[1],
			f"-> {frappe.db.get_value('Employee', EMP, 'department')}")
		doc.reload()
		doc.cancel()
	finally:
		work_history.ENFORCE_EFFECTIVE_DATE_NOT_FUTURE = True
		et.ENFORCE_EFFECTIVE_DATE_NOT_FUTURE = True

	# NV đã nghỉ (status "Left " có dấu cách) vẫn ghi được bản ghi quá khứ
	left_emp = frappe.db.get_value("Employee", {"status": ("like", "Left%")}, "name")
	if left_emp:
		doc = frappe.new_doc("Employee Transfer")
		doc.employee = left_emp
		doc.transfer_date = D1
		doc.append("transfer_details", {"fieldname": "department", "new": DEPARTMENTS[1]})
		doc.insert()
		doc.submit()
		check("NV đã nghỉ (status 'Left ') vẫn submit + rebuild được", doc.docstatus == 1)
	else:
		print("  SKIP  site không có NV status Left")

# ----------------------------------------------------------------------------------
frappe.db.rollback()
print(f"\n=== KẾT QUẢ: {ok} PASS / {fail} FAIL === (đã rollback, không để lại dữ liệu)")
