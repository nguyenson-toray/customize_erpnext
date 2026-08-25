# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Shared logic for Employee Promotion / Employee Transfer.

Two jobs:

1. Keep the property rows honest — only the six organisational fields may be changed,
   and `property` / `current` are filled in automatically so a Data Import file only
   needs `fieldname` and `new`.

2. Rebuild `Employee.internal_work_history` from scratch instead of appending to it.

Why rebuild rather than append (what HRMS does in hrms/hr/utils.py):

  - `update_employee_work_history` blindly does `setattr(employee, fieldname, item.new)`,
    so importing a transfer dated 2023 overwrites the employee's CURRENT department with
    a three-year-old value. Only a strictly chronological import survives that.
  - its seed row (utils.py:65-74) is stamped with the employee's values AS OF THE FIRST
    SUBMIT plus `date_of_joining`, so a backfill starts the timeline with the newest
    department attributed to the joining date.
  - `delete_employee_work_history` (utils.py:129) cancels by `frappe.db.delete` on a
    loosely built filter dict, which can take out rows belonging to a different document.

Recomputing the whole timeline from every submitted document, sorted by date, makes the
result independent of import order and idempotent — re-running can never drift.

Keep ALLOWED_FIELDS in sync with ALLOWED_PROPERTY_FIELDS in
customize_erpnext/public/js/custom_scripts/employee_property_update_override.js.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

# Thời điểm gửi hồ sơ.
#
# True  = giữ nguyên luật HRMS gốc: chỉ Submit được vào ĐÚNG NGÀY hoặc SAU
#         Transfer Date / Promotion Date. Phiếu ghi ngày tương lai bị chặn
#         (EmployeeTransfer.before_submit / EmployeePromotion.before_submit).
# False = cho phép Submit cả phiếu ghi ngày TƯƠNG LAI, dùng khi cần lên phiếu trước.
#
# ⚠ Đặt False thì phiếu ngày tương lai ăn vào Employee master NGAY khi submit, chứ
# không đợi tới ngày đó: rebuild luôn lấy giá trị của sự kiện có ngày mới nhất. Nhập
# dữ liệu QUÁ KHỨ thì không cần đụng tới cờ này — ngày quá khứ vốn đã không bị chặn.
ENFORCE_EFFECTIVE_DATE_NOT_FUTURE = True

# The only Employee fields a promotion / transfer may change.
ALLOWED_FIELDS = (
	"department",
	"custom_section",
	"custom_group",
	"designation",
	"reports_to",
	"employment_type",
)

# Fields mirrored into each Employee Internal Work History row. `branch` is never in
# ALLOWED_FIELDS (it is hidden on Employee here) but belongs to the stock child table,
# so it is carried through unchanged rather than blanked out.
HISTORY_FIELDS = (
	"branch",
	"department",
	"custom_section",
	"custom_group",
	"designation",
)

# Every field whose value has to be tracked across the timeline.
TRACKED_FIELDS = tuple(dict.fromkeys(ALLOWED_FIELDS + HISTORY_FIELDS))

# `property` is only a display label; `fieldname` is the key that collect_events,
# validate_allowed_fields and the rebuild all work from. An import template built from
# the UI carries a "Property (Employee Transfer Detail)" column and NO field name
# column, so without resolving the label back to a fieldname those documents submit
# cleanly and change absolutely nothing.
PROPERTY_ALIASES = {
	# Typo in Employee Transfer.xlsx imported 2026-08-25 — 25 rows spell it this way.
	"desination": "designation",
}


def resolve_fieldname(value: str | None) -> str | None:
	"""Map a `property` label (or a fieldname) onto one of ALLOWED_FIELDS."""
	if not value:
		return None

	key = value.strip().lower()
	meta = frappe.get_meta("Employee")
	for fieldname in ALLOWED_FIELDS:
		df = meta.get_field(fieldname)
		labels = {fieldname.lower(), (df.label or "").strip().lower() if df else ""}
		if key in labels:
			return fieldname

	return PROPERTY_ALIASES.get(key)


# (doctype, date field, property table field)
SOURCES = (
	("Employee Promotion", "promotion_date", "promotion_details"),
	("Employee Transfer", "transfer_date", "transfer_details"),
)


def same_value(a, b) -> bool:
	"""So sánh 2 giá trị field, bỏ qua hoa/thường.

	MySQL đối chiếu không phân biệt hoa thường và Frappe nắn Link về tên canonical khi
	lưu, nên file import ghi 'Sub leader' trong khi DB lưu 'Sub Leader' là BÌNH THƯỜNG,
	không phải lệch.
	"""
	return (a or "").strip().lower() == (b or "").strip().lower()


def source_for(doctype: str) -> tuple[str, str, str]:
	for row in SOURCES:
		if row[0] == doctype:
			return row
	frappe.throw(_("{0} is not an employee property document").format(doctype))


# ----------------------------------------------------------------------------------
# reading the timeline
# ----------------------------------------------------------------------------------
def collect_events(employee: str, exclude: tuple[str, str] | None = None) -> list[dict]:
	"""Every submitted promotion/transfer of `employee`, oldest first.

	`exclude` is a (doctype, name) pair to leave out — used while cancelling, because
	`on_cancel` may run before the new docstatus is visible to a fresh query.
	"""
	events = []

	for doctype, date_field, table_field in SOURCES:
		docs = frappe.get_all(
			doctype,
			filters={"employee": employee, "docstatus": 1},
			fields=["name", f"{date_field} as event_date", "creation"],
		)
		docs = [d for d in docs if not (exclude and exclude == (doctype, d.name))]
		if not docs:
			continue

		rows = frappe.get_all(
			"Employee Property History",
			filters={
				"parenttype": doctype,
				"parentfield": table_field,
				"parent": ("in", [d.name for d in docs]),
			},
			fields=["parent", "fieldname", "current", "new", "idx"],
			order_by="parent asc, idx asc",
			parent_doctype=doctype,
		)

		by_parent: dict[str, list] = {}
		for row in rows:
			by_parent.setdefault(row.parent, []).append(row)

		for d in docs:
			if not d.event_date:
				continue
			changes = {}
			for row in by_parent.get(d.name, []):
				if row.fieldname in TRACKED_FIELDS:
					changes[row.fieldname] = {
						"current": row.current or None,
						"new": row.new or None,
					}
			events.append(
				{
					"doctype": doctype,
					"name": d.name,
					"event_date": getdate(d.event_date),
					"creation": get_datetime(d.creation),
					"changes": changes,
				}
			)

	events.sort(key=lambda e: (e["event_date"], e["creation"]))
	return events


def baseline_state(employee, events: list[dict]) -> dict:
	"""Value of every tracked field on the employee's joining date.

	Taken from the `current` recorded by the FIRST event that touches a field. A field
	no event ever touched has never changed, so today's value is also its value then.
	"""
	state = {fieldname: employee.get(fieldname) or None for fieldname in TRACKED_FIELDS}

	seen = set()
	for event in events:
		for fieldname, change in event["changes"].items():
			if fieldname in seen:
				continue
			seen.add(fieldname)
			state[fieldname] = change["current"]

	return state


def state_at(employee, events: list[dict], upto: tuple | None = None) -> dict:
	"""Tracked field values after replaying every event before `upto`.

	`upto` is a (date, creation) pair; pass None to replay all of them.
	"""
	state = baseline_state(employee, events)

	for event in events:
		if upto and (event["event_date"], event["creation"]) >= upto:
			break
		for fieldname, change in event["changes"].items():
			state[fieldname] = change["new"]

	return state


# ----------------------------------------------------------------------------------
# validation / autofill, called from the doctype overrides
# ----------------------------------------------------------------------------------
def validate_allowed_fields(doc):
	_doctype, _date_field, table_field = source_for(doc.doctype)

	for row in doc.get(table_field) or []:
		if not (row.fieldname or row.property or row.new):
			continue

		if not row.fieldname:
			frappe.throw(
				_("Row #{0}: cannot tell which Employee field {1} refers to. Use one of: {2}").format(
					row.idx, frappe.bold(row.property or "(empty)"), ", ".join(ALLOWED_FIELDS)
				),
				title=_("Unknown Property"),
			)

		if row.fieldname not in ALLOWED_FIELDS:
			frappe.throw(
				_("Row #{0}: {1} cannot be changed by a promotion or transfer. Allowed properties: {2}").format(
					row.idx, frappe.bold(row.fieldname), ", ".join(ALLOWED_FIELDS)
				),
				title=_("Property Not Allowed"),
			)

		# Dòng có `current` == `new` không đổi gì cả: nó submit sạch sẽ nhưng không sinh
		# mốc work history nào. Dialog của HRMS đã chặn ("Nothing to change") nhưng Data
		# Import đi thẳng vào doc nên lọt — 4 phiếu promotion ngày 2026-04-13 / 2025-09-01
		# dính đúng lỗi này.
		if same_value(row.current, row.new):
			label = frappe.get_meta("Employee").get_label(row.fieldname)
			frappe.throw(
				_("Row #{0}: {1} is already {2} — nothing would change").format(
					row.idx, _(label), frappe.bold(row.new or "(empty)")
				),
				title=_("Nothing to Change"),
			)


def validate_link_values(doc):
	"""Reject `current` / `new` values that do not exist in the target Link doctype.

	`_validate_links()` runs before `run_before_save_methods()` (document.py:591), so the
	`ignore_validate` flag used by rebuild_work_history does NOT let a broken link
	through — but the failure surfaces on the Employee document, naming neither the row
	nor the transfer being submitted. Checking here fails on the document the user is
	actually looking at.

	Both columns matter: `new` lands on the Employee master, and `current` becomes the
	baseline of the very first internal_work_history row.
	"""
	_doctype, _date_field, table_field = source_for(doc.doctype)
	meta = frappe.get_meta("Employee")

	for row in doc.get(table_field) or []:
		if not row.fieldname:
			continue

		df = meta.get_field(row.fieldname)
		if not df or df.fieldtype != "Link" or not df.options:
			continue

		for column in ("current", "new"):
			value = row.get(column)
			if value and not frappe.db.exists(df.options, value):
				frappe.throw(
					_("Row #{0}: {1} {2} does not exist in {3}").format(
						row.idx, _(column.title()), frappe.bold(value), frappe.bold(_(df.options))
					),
					title=_("Invalid Value"),
				)


def autofill_property_rows(doc):
	"""Fill in `property` and `current` so an import file only needs fieldname + new.

	`current` is the value the field held immediately before this document's date,
	replayed from the other submitted documents — not the employee's value today,
	which for a backfilled record is usually several transfers newer.
	"""
	_doctype, date_field, table_field = source_for(doc.doctype)

	for row in doc.get(table_field) or []:
		if not row.fieldname:
			row.fieldname = resolve_fieldname(row.property)

	rows = [row for row in (doc.get(table_field) or []) if row.fieldname]
	if not rows:
		return

	meta = frappe.get_meta("Employee")
	for row in rows:
		df = meta.get_field(row.fieldname)
		if df and not row.property:
			row.property = df.label

	if not (doc.employee and doc.get(date_field)):
		return
	if all(row.current for row in rows):
		return

	employee = frappe.get_doc("Employee", doc.employee)
	events = collect_events(doc.employee, exclude=(doc.doctype, doc.name))
	state = state_at(
		employee,
		events,
		upto=(
			getdate(doc.get(date_field)),
			get_datetime(doc.creation) if doc.creation else now_datetime(),
		),
	)

	for row in rows:
		if not row.current:
			row.current = state.get(row.fieldname)


# ----------------------------------------------------------------------------------
# rebuilding
# ----------------------------------------------------------------------------------
def build_timeline(employee, events: list[dict]) -> list[dict]:
	state = baseline_state(employee, events)
	rows = [{fieldname: state[fieldname] for fieldname in HISTORY_FIELDS}]
	rows[0]["from_date"] = getdate(employee.date_of_joining) if employee.date_of_joining else None

	for event in events:
		changed = False
		for fieldname, change in event["changes"].items():
			if fieldname in HISTORY_FIELDS and not same_value(state.get(fieldname), change["new"]):
				changed = True
			state[fieldname] = change["new"]

		if not changed:
			# A promotion that only moved reports_to / employment_type is a real event,
			# but the work history table has no column for it — no new row.
			continue

		row = {fieldname: state[fieldname] for fieldname in HISTORY_FIELDS}
		row["from_date"] = event["event_date"]

		# Two documents on the same day (or one dated on/before the joining date)
		# collapse into a single row holding the final state of that day.
		previous_from = rows[-1]["from_date"]
		if previous_from and row["from_date"] <= previous_from:
			row["from_date"] = previous_from
			rows[-1] = row
		else:
			rows.append(row)

	for idx, row in enumerate(rows[:-1]):
		next_from = rows[idx + 1]["from_date"]
		row["to_date"] = add_days(next_from, -1) if next_from else None

	if employee.relieving_date:
		# `relieving_date` at TIQN is the first day NOT worked, not the last day worked:
		# across the whole site only 6 employees have non-Absent attendance ON their
		# relieving_date, against 281 on the day before it. So the last day spent in the
		# final department/designation is relieving_date - 1 — which also matches every
		# other row, where to_date is the day before the next state begins.
		last_day = add_days(getdate(employee.relieving_date), -1)
		if rows[-1]["from_date"] and last_day < rows[-1]["from_date"]:
			# Transferred on (or after) the day they left — keep the row valid instead of
			# emitting from_date > to_date.
			last_day = rows[-1]["from_date"]
		rows[-1]["to_date"] = last_day
	else:
		rows[-1]["to_date"] = None

	return rows


def _apply_fetch_from(doc):
	"""Tính lại các field `fetch_from` có nguồn nằm trong ALLOWED_FIELDS.

	Hai lý do phải làm tay:

	1. `rebuild_work_history` lưu Employee với `flags.ignore_validate = True` (xem lý do
	   ở đó), mà chính `_validate()` mới là chỗ áp dụng `fetch_from`.
	2. Quan trọng hơn: 3/4 field dẫn xuất trên Employee để `fetch_if_empty = 1`, nên
	   **kể cả Frappe bản gốc cũng không bao giờ làm mới chúng** khi field nguồn đổi —
	   nó chỉ điền khi đang trống. Hậu quả: thăng chức từ QC Worker lên QC Sub Leader
	   mà `custom_designation_vietnamese` vẫn đứng ở "Công nhân Kiểm hàng".

	    grade                         <- designation.custom_grade          (fetch_if_empty)
	    custom_designation_vietnamese <- designation.custom_designation_vn (fetch_if_empty)
	    custom_probation_days         <- designation.custom_probation_days
	    payroll_cost_center           <- department.payroll_cost_center    (fetch_if_empty)

	Đọc thẳng từ meta thay vì liệt kê cứng, để thêm field dẫn xuất mới không phải nhớ
	quay lại sửa chỗ này.
	"""
	meta = frappe.get_meta("Employee")

	for df in meta.fields:
		if not df.fetch_from:
			continue

		source_field, _, target_field = df.fetch_from.partition(".")
		if source_field not in ALLOWED_FIELDS or not target_field:
			continue

		# `set_only_once` = chốt một lần rồi thôi. custom_probation_days để cờ này vì
		# một người chỉ thử việc đúng một lần, lúc vào làm — thăng chức về sau không
		# được kéo số ngày thử việc của chức danh mới sang.
		if df.set_only_once:
			continue

		link_doctype = meta.get_field(source_field).options
		source_name = doc.get(source_field)
		value = (
			frappe.db.get_value(link_doctype, source_name, target_field) if source_name else None
		)

		# Nguồn rỗng thì GIỮ NGUYÊN giá trị đang có, đừng xoá trắng. Trên site có 16/115
		# Designation chưa điền custom_designation_vn; ép theo nguồn sẽ thổi bay tên tiếng
		# Việt của những người đang mang các chức danh đó (4 chức danh, 4 người).
		# Thiếu thì phải điền vào Designation, không phải xoá bên Employee.
		if value in (None, ""):
			continue

		# Cố ý BỎ QUA fetch_if_empty. 3/4 field dẫn xuất để cờ đó, nên Frappe bản gốc
		# không bao giờ làm mới chúng khi nguồn đổi — thăng chức QC Worker -> QC Sub
		# Leader mà custom_designation_vietnamese vẫn đứng ở "Công nhân Kiểm hàng".
		# Ở đây rebuild là nguồn sự thật cho ALLOWED_FIELDS nên field dẫn xuất phải theo.
		doc.set(df.fieldname, value)


def rebuild_work_history(employee: str, revert=None, exclude: tuple[str, str] | None = None):
	"""Recompute Employee master fields and internal_work_history from every event."""
	if frappe.flags.skip_work_history_rebuild:
		return

	doc = frappe.get_doc("Employee", employee)
	events = collect_events(employee, exclude=exclude)

	if revert is not None:
		# The cancelled document is already out of `events`. Put back the values it had
		# overwritten, so a field no other event ever touched returns to its old value
		# instead of being read back as a baseline from the value this document set.
		_doctype, _date_field, table_field = source_for(revert.doctype)
		for row in revert.get(table_field) or []:
			if row.fieldname in TRACKED_FIELDS:
				doc.set(row.fieldname, row.current or None)

	final = state_at(doc, events)
	for fieldname in ALLOWED_FIELDS:
		doc.set(fieldname, final.get(fieldname))

	_apply_fetch_from(doc)

	doc.set("internal_work_history", build_timeline(doc, events))

	# Backfilling touches employees who left years ago, and Employee.validate rejects
	# them for reasons that have nothing to do with work history: 1386 records carry
	# status "Left " with a trailing space, which fails validate_status() outright, and
	# a Left employee whose subordinates are still Active is thrown out by
	# Employee.validate_status(). NestedSet.on_update still runs, so a changed
	# reports_to keeps lft/rgt correct.
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def audit(doctype: str | None = None, employee: str | None = None) -> dict:
	"""Đối chiếu phiếu đã submit với Employee master + internal_work_history.

	    bench --site <site> execute \
	        customize_erpnext.overrides.employee_property.work_history.audit
	    bench --site <site> execute ...audit --kwargs "{'doctype': 'Employee Promotion'}"

	Chỉ ĐỌC, không ghi gì. Bắt 5 loại lệch:

	  no_property     phiếu submit nhưng không có dòng nào có fieldname -> đổi 0 field
	  master_mismatch giá trị hiện tại của Employee != `new` của sự kiện MỚI NHẤT
	  missing_row     có đổi field thuộc work history nhưng không có dòng bắt đầu đúng ngày đó
	  row_value       dòng work history tại ngày đó mang giá trị khác `new`
	  timeline        to_date không liền mạch với from_date của dòng kế, hoặc dòng cuối
	                  không khớp relieving_date - 1
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	filters = {"docstatus": 1}
	if employee:
		filters["employee"] = employee

	employees = set()
	doctypes = [doctype] if doctype else [row[0] for row in SOURCES]
	for dt in doctypes:
		employees.update(
			d.employee for d in frappe.get_all(dt, filters=filters, fields=["employee"]) if d.employee
		)

	issues = []
	for name in sorted(employees):
		issues += _audit_employee(name, doctypes)

	by_kind = {}
	for issue in issues:
		by_kind.setdefault(issue["kind"], []).append(issue)

	print(f"đã rà {len(employees)} nhân viên, {len(issues)} điểm lệch")
	for kind, found in sorted(by_kind.items()):
		print(f"\n--- {kind}: {len(found)}")
		for issue in found[:20]:
			print(f"    {issue['employee']:12} {issue['detail']}")
		if len(found) > 20:
			print(f"    ... còn {len(found) - 20} dòng nữa")
	if not issues:
		print("KHÔNG có điểm lệch nào")

	return {
		"employees": len(employees),
		"issues": len(issues),
		"by_kind": {k: len(v) for k, v in sorted(by_kind.items())},
	}


def _audit_employee(name: str, doctypes: list[str]) -> list[dict]:
	found = []

	def add(kind, detail):
		found.append({"employee": name, "kind": kind, "detail": detail})

	doc = frappe.get_doc("Employee", name)

	# Luôn rà trên TOÀN BỘ sự kiện của nhân viên. `doctypes` chỉ dùng để chọn xem nhân
	# viên nào cần rà — nếu lọc luôn cả events thì "sự kiện mới nhất" sẽ tính thiếu và
	# báo lệch nhầm cho người có promotion cũ rồi transfer mới đè lên sau đó.
	events = collect_events(name)

	for event in events:
		if event["doctype"] in doctypes and not event["changes"]:
			add("no_property", f"{event['name']} {event['event_date']} không đổi field nào")

	# master phải bằng `new` của sự kiện mới nhất chạm vào field đó
	latest = {}
	for event in events:
		for fieldname, change in event["changes"].items():
			latest[fieldname] = (change["new"], event["name"], event["event_date"])
	for fieldname, (value, source, date) in latest.items():
		actual = doc.get(fieldname)
		if not same_value(actual, value):
			add(
				"master_mismatch",
				f"{fieldname}: master={actual!r} nhưng {source} ({date}) đặt {value!r}",
			)

	rows = sorted(
		doc.internal_work_history,
		key=lambda r: (getdate(r.from_date) if r.from_date else getdate("1900-01-01"), r.idx),
	)

	# mỗi sự kiện chạm HISTORY_FIELDS phải có dòng bắt đầu đúng ngày đó
	by_from = {getdate(r.from_date): r for r in rows if r.from_date}
	for event in events:
		touched = {f: c for f, c in event["changes"].items() if f in HISTORY_FIELDS}
		if not touched:
			continue
		row = by_from.get(event["event_date"])
		if not row:
			add("missing_row", f"{event['name']} {event['event_date']} không có dòng work history")
			continue
		for fieldname, change in touched.items():
			if not same_value(row.get(fieldname), change["new"]):
				add(
					"row_value",
					f"{event['event_date']} {fieldname}: dòng={row.get(fieldname)!r} "
					f"nhưng phiếu đặt {change['new']!r}",
				)

	# `current` ghi trên phiếu phải khớp giá trị đang có hiệu lực ngay trước ngày đó.
	# Lệch = 2 phiếu mâu thuẫn nhau, không tự quyết được phiếu nào đúng.
	for event in events:
		if event["doctype"] not in doctypes:
			continue
		before = state_at(doc, events, upto=(event["event_date"], event["creation"]))
		for fieldname, change in event["changes"].items():
			if change["current"] and not same_value(before.get(fieldname), change["current"]):
				add(
					"stale_current",
					f"{event['name']} {event['event_date']} {fieldname}: phiếu ghi "
					f"current={change['current']!r} nhưng lúc đó đang là {before.get(fieldname)!r}",
				)

	for idx, row in enumerate(rows[:-1]):
		nxt = rows[idx + 1]
		if not (row.to_date and nxt.from_date):
			add("timeline", f"dòng {row.idx} thiếu ngày (to_date={row.to_date}, kế={nxt.from_date})")
			continue
		if getdate(row.to_date) != add_days(getdate(nxt.from_date), -1):
			add(
				"timeline",
				f"hở/chồng ngày: {row.from_date}..{row.to_date} rồi tới {nxt.from_date}",
			)

	if rows:
		last = rows[-1]
		expected = add_days(getdate(doc.relieving_date), -1) if doc.relieving_date else None
		if (getdate(last.to_date) if last.to_date else None) != expected:
			add(
				"timeline",
				f"dòng cuối to_date={last.to_date} nhưng relieving_date={doc.relieving_date} "
				f"-> phải là {expected}",
			)

	return found


@frappe.whitelist()
def repair_missing_fieldnames(apply: bool = False) -> dict:
	"""Backfill `fieldname` on rows imported with only a `property` label.

	A Data Import template exported from the UI has a "Property" column and no field
	name column, so every row it creates has `fieldname` NULL — the documents submit
	without error and change nothing. This repairs rows already in the database;
	`resolve_fieldname` stops new ones from being created that way.

	Dry run by default:

	    bench --site <site> execute \
	        customize_erpnext.overrides.employee_property.work_history.repair_missing_fieldnames
	    bench --site <site> execute \
	        customize_erpnext.overrides.employee_property.work_history.repair_missing_fieldnames \
	        --kwargs "{'apply': True}"
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	rows = frappe.db.sql(
		"""
		select h.name, h.parent, h.parenttype, h.idx, h.property, t.docstatus, t.employee
		from `tabEmployee Property History` h
		join `tabEmployee Transfer` t on t.name = h.parent and h.parenttype = 'Employee Transfer'
		where ifnull(h.fieldname, '') = ''
		union all
		select h.name, h.parent, h.parenttype, h.idx, h.property, p.docstatus, p.employee
		from `tabEmployee Property History` h
		join `tabEmployee Promotion` p on p.name = h.parent and h.parenttype = 'Employee Promotion'
		where ifnull(h.fieldname, '') = ''
		""",
		as_dict=True,
	)

	resolved, unresolved, submitted_employees = {}, {}, set()
	for row in rows:
		fieldname = resolve_fieldname(row.property)
		if not fieldname:
			unresolved.setdefault(row.property, []).append(row.parent)
			continue

		resolved.setdefault((row.property, fieldname), []).append(row)
		if row.docstatus == 1:
			submitted_employees.add(row.employee)

	print(f"{len(rows)} dòng thiếu fieldname")
	for (label, fieldname), matched in sorted(resolved.items()):
		print(f"  {label!r:16} -> {fieldname:16} {len(matched)} dòng")
	for label, parents in sorted(unresolved.items()):
		print(f"  {label!r:16} -> KHÔNG map được, {len(parents)} dòng, ví dụ {parents[0]}")

	if not apply:
		print("\nDRY RUN — chưa ghi gì. Chạy lại với --kwargs \"{'apply': True}\" để áp dụng.")
		return {"rows": len(rows), "resolved": {f"{k[0]}->{k[1]}": len(v) for k, v in resolved.items()},
			"unresolved": {k: len(v) for k, v in unresolved.items()}}

	for (_label, fieldname), matched in resolved.items():
		for row in matched:
			# db-level write: the child rows of an already submitted document cannot be
			# edited through the document API, and `fieldname` is a hidden key field.
			frappe.db.set_value(
				"Employee Property History", row.name, "fieldname", fieldname, update_modified=False
			)
	frappe.db.commit()
	print(f"đã ghi fieldname cho {sum(len(v) for v in resolved.values())} dòng")

	rebuilt = []
	for employee in sorted(submitted_employees):
		rebuild_work_history(employee)
		frappe.db.commit()
		rebuilt.append(employee)
	print(f"đã dựng lại work history cho {len(rebuilt)} NV có doc ĐÃ SUBMIT: {rebuilt}")

	return {
		"rows": len(rows),
		"resolved": {f"{k[0]}->{k[1]}": len(v) for k, v in resolved.items()},
		"unresolved": {k: len(v) for k, v in unresolved.items()},
		"rebuilt": rebuilt,
	}


@frappe.whitelist()
def rebuild_all(employees: list[str] | str | None = None) -> dict:
	"""Rebuild every employee that has at least one submitted promotion / transfer.

	Meant for after a bulk Data Import that ran with
	`frappe.flags.skip_work_history_rebuild` set:

	    bench --site <site> execute \
	        customize_erpnext.overrides.employee_property.work_history.rebuild_all
	"""
	frappe.only_for(("HR Manager", "System Manager"))

	if isinstance(employees, str):
		employees = frappe.parse_json(employees)

	if not employees:
		names = set()
		for doctype, _date_field, _table_field in SOURCES:
			names.update(
				d.employee
				for d in frappe.get_all(doctype, filters={"docstatus": 1}, fields=["employee"])
				if d.employee
			)
		employees = sorted(names)

	frappe.flags.skip_work_history_rebuild = False

	done, failed = [], {}
	for name in employees:
		try:
			rebuild_work_history(name)
			frappe.db.commit()
			done.append(name)
		except Exception:
			frappe.db.rollback()
			failed[name] = frappe.get_traceback()

	print(f"rebuilt {len(done)} employee(s), {len(failed)} failed")
	for name, traceback in failed.items():
		print(f"--- {name}\n{traceback}")

	return {"rebuilt": done, "failed": failed}
