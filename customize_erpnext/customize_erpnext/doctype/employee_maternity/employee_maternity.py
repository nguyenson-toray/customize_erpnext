# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, add_days, today
from frappe.model.document import Document
from datetime import date
from dateutil.relativedelta import relativedelta
import json


class EmployeeMaternity(Document):
	# =========================================================================
	# Virtual Fields
	# =========================================================================

	@property
	def seniority(self):
		"""Seniority in months from date_of_joining to today"""
		if not self.date_of_joining:
			return 0
		doj = getdate(self.date_of_joining)
		today_date = date.today()
		rd = relativedelta(today_date, doj)
		return rd.years * 12 + rd.months

	@property
	def gestational_age(self):
		"""Gestational age in months. Formula: 9.5 - (DATEDIF(TODAY, estimated_due_date, 'm') + 1)"""
		if not self.estimated_due_date:
			return 0
		today_date = date.today()
		edd = getdate(self.estimated_due_date)
		if edd <= today_date:
			return 9.5
		rd = relativedelta(edd, today_date)
		months_diff = rd.years * 12 + rd.months
		return round(9.5 - (months_diff + 1), 1)

	# =========================================================================
	# Validation
	# =========================================================================

	def validate(self):
		self.calculate_derived_dates()
		self.validate_dates()
		self.validate_date_overlap()
		self.calculate_status()

	def calculate_derived_dates(self):
		"""Auto-calculate derived dates — always overrides, no conditions.

		Rules:
		  pregnant_to_date     = maternity_from_date - 1 day
		  youg_child_from_date = maternity_to_date + 1 day
		  youg_child_to_date   = date_of_birth + 364 days
		"""
		if self.maternity_from_date:
			self.pregnant_to_date = add_days(getdate(self.maternity_from_date), -1)

		if self.maternity_to_date:
			self.youg_child_from_date = add_days(getdate(self.maternity_to_date), 1)
		else:
			self.youg_child_from_date = None

		if self.date_of_birth:
			self.youg_child_to_date = add_days(getdate(self.date_of_birth), 364)

	def validate_dates(self):
		"""Validate from < to for each date pair.
		Note: pregnant_to_date and youg_child_from_date are auto-derived,
		so the 'to without from' check is skipped for those.
		"""
		pairs = [
			("pregnant_from_date", "pregnant_to_date", _("Pregnant")),
			("maternity_from_date", "maternity_to_date", _("Maternity Leave")),
			("youg_child_from_date", "youg_child_to_date", _("Young Child")),
		]
		derived_to_fields = {"pregnant_to_date", "youg_child_from_date"}

		for from_field, to_field, label in pairs:
			from_date = self.get(from_field)
			to_date = self.get(to_field)
			if from_date and to_date:
				if getdate(from_date) >= getdate(to_date):
					frappe.throw(
						_("{0}: From Date must be earlier than To Date").format(label)
					)
			# if to_date and not from_date and to_field not in derived_to_fields:
			# 	frappe.throw(
			# 		_("{0}: To Date is set but From Date is missing").format(label)
			# 	)

	def calculate_status(self):
		"""Set status field based on which date period today falls into.
		If today falls in multiple periods (data legacy), pick the one with the latest from_date."""
		from datetime import date as _date
		today_date = _date.today()

		active = []  # list of (from_date, status_label)
		checks = [
			("pregnant_from_date",    "pregnant_to_date",    "Pregnant"),
			("maternity_from_date",   "maternity_to_date",   "Maternity Leave"),
			("youg_child_from_date",  "youg_child_to_date",  "Young Child"),
		]
		for from_field, to_field, label in checks:
			from_val = self.get(from_field)
			to_val   = self.get(to_field)
			if not from_val:
				continue
			f = getdate(from_val)
			t = getdate(to_val) if to_val else None
			if f <= today_date and (t is None or today_date <= t):
				active.append((f, label))

		if not active:
			# Hết chế độ: all phases done and today is past young-child end date
			if self.youg_child_to_date and today_date > getdate(self.youg_child_to_date):
				self.status = "Inactive"
			else:
				self.status = ""
		else:
			# Priority: period with the latest from_date
			active.sort(key=lambda x: x[0], reverse=True)
			self.status = active[0][1]

	def validate_date_overlap(self):
		"""Validate 3 giai đoạn không overlap nhau trong cùng 1 record.
		After calculate_derived_dates(), periods are always consecutive (1 day apart),
		so this acts as a safety check for manually overridden values.
		"""
		effective_mat_from = self.maternity_from_date or self.maternity_from_date_estimate
		periods = {}
		if self.pregnant_from_date:
			periods["Pregnant"] = (
				getdate(self.pregnant_from_date),
				getdate(self.pregnant_to_date) if self.pregnant_to_date else None,
			)
		if effective_mat_from:
			periods["Maternity Leave"] = (
				getdate(effective_mat_from),
				getdate(self.maternity_to_date) if self.maternity_to_date else None,
			)
		if self.youg_child_from_date:
			periods["Young Child"] = (
				getdate(self.youg_child_from_date),
				getdate(self.youg_child_to_date) if self.youg_child_to_date else None,
			)

		# Cần ít nhất end_date để kiểm tra overlap
		valid_periods = {k: v for k, v in periods.items() if v[1] is not None}
		names = list(valid_periods.keys())

		for i in range(len(names)):
			for j in range(i + 1, len(names)):
				a_name, b_name = names[i], names[j]
				a_from, a_to = valid_periods[a_name]
				b_from, b_to = valid_periods[b_name]
				# Overlap nếu: a_from <= b_to AND b_from <= a_to
				if a_from <= b_to and b_from <= a_to:
					frappe.throw(
						_("Date periods overlap between {0} ({1} → {2}) and {3} ({4} → {5})").format(
							_(a_name), a_from, a_to,
							_(b_name), b_from, b_to,
						)
					)

	# =========================================================================
	# Attendance Recalculation Triggers
	# =========================================================================

	def before_save(self):
		self._collect_affected_dates()

	def _collect_affected_dates(self):
		"""So sánh old vs new để tìm các ngày cần recalc attendance"""
		affected_dates = set()

		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc:
				# Collect all old date ranges
				self._add_all_ranges(affected_dates, old_doc)

				# Kiểm tra có thay đổi không
				# Include source fields that trigger derived-date recalculation
				tracked_fields = [
					"pregnant_from_date", "pregnant_to_date",
					"maternity_from_date", "maternity_from_date_estimate",
					"maternity_to_date",
					"youg_child_from_date", "youg_child_to_date",
					"estimated_due_date", "date_of_birth",
					"apply_benefit",
				]
				changed = any(
					str(getattr(old_doc, f, "") or "") != str(getattr(self, f, "") or "")
					for f in tracked_fields
				)
				if not changed:
					return

		# Collect new date ranges
		self._add_all_ranges(affected_dates, self)

		if affected_dates:
			self._maternity_affected_dates = list(affected_dates)
			self._maternity_employee = self.employee

	def _add_all_ranges(self, date_set, doc):
		"""Thu thập dates từ cả 3 giai đoạn của doc"""
		pairs = [
			("pregnant_from_date", "pregnant_to_date"),
			("maternity_from_date", "maternity_to_date"),
			("youg_child_from_date", "youg_child_to_date"),
		]
		for from_field, to_field in pairs:
			from_date = doc.get(from_field)
			to_date = doc.get(to_field)
			if from_date and to_date:
				self._add_date_range(date_set, from_date, to_date, doc.employee)

	def _add_date_range(self, date_set, from_date, to_date, employee):
		"""Thêm date range vào set, giới hạn đến today và relieving_date"""
		current_date = getdate(from_date)
		end_date = getdate(to_date)

		today_date = getdate(today())
		if end_date > today_date:
			end_date = today_date

		relieving_date = frappe.db.get_value("Employee", employee, "relieving_date")
		if relieving_date:
			last_working_day = add_days(getdate(relieving_date), -1)
			if end_date > last_working_day:
				end_date = last_working_day

		while current_date <= end_date:
			date_set.add(str(current_date))
			current_date = add_days(current_date, 1)


# =============================================================================
# Hook Functions
# =============================================================================

def validate_maternity(doc, method):
	doc.validate()


def on_maternity_update(doc, method):
	_queue_attendance_recalculation(doc, "on_update")


def on_maternity_insert(doc, method):
	if not hasattr(doc, "_maternity_affected_dates"):
		affected_dates = set()
		doc._add_all_ranges(affected_dates, doc)
		if affected_dates:
			doc._maternity_affected_dates = list(affected_dates)
			doc._maternity_employee = doc.employee

	_queue_attendance_recalculation(doc, "after_insert")


def on_maternity_delete(doc, method):
	affected_dates = set()
	doc._add_all_ranges(affected_dates, doc)

	if affected_dates:
		doc._maternity_affected_dates = list(affected_dates)
		doc._maternity_employee = doc.employee
		_queue_attendance_recalculation(doc, "on_trash")


def _queue_attendance_recalculation(doc, trigger):
	"""Queue background job để recalculate attendance cho các ngày bị ảnh hưởng.
	Hoạt động cho cả: UI save, Data Import (add new / update if exist), on_trash.
	"""
	try:
		if not hasattr(doc, "_maternity_affected_dates") or not doc._maternity_affected_dates:
			return

		affected_dates = doc._maternity_affected_dates
		employee = getattr(doc, "_maternity_employee", doc.employee)

		affected_dates_sorted = sorted([getdate(d) for d in affected_dates])
		from_date  = str(affected_dates_sorted[0])
		to_date    = str(affected_dates_sorted[-1])
		total_days = len(affected_dates_sorted)

		job_id = f"maternity_attendance_{employee}_{int(frappe.utils.now_datetime().timestamp())}"

		frappe.enqueue(
			"customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.background_update_attendance_for_maternity",
			queue="long",
			timeout=1800,
			job_id=job_id,
			employee=employee,
			affected_dates_json=json.dumps([str(d) for d in affected_dates_sorted]),
			from_date=from_date,
			to_date=to_date,
		)

		# Skip popup during Data Import (no active web request)
		if not getattr(frappe.flags, "in_import", False):
			frappe.msgprint(
				msg=_("Maternity period changed. Updating attendance for {0} days ({1} → {2})...").format(
					total_days, from_date, to_date
				),
				title=_("Attendance Update Queued"),
				indicator="blue",
			)

		frappe.logger().info(
			f"[Maternity] {trigger} — {employee}: queued {total_days} days "
			f"({from_date} → {to_date}). job_id={job_id}"
		)

	except Exception as e:
		frappe.log_error(
			f"Error in _queue_attendance_recalculation for {doc.name}: {str(e)}",
			"Employee Maternity Attendance Update Error",
		)


def background_update_attendance_for_maternity(employee, affected_dates_json, from_date, to_date):
	"""Background job: recalculate attendance cho đúng những ngày bị ảnh hưởng.

	Gọi _core_process_attendance_logic_optimized với list ngày cụ thể
	(không xử lý toàn bộ range from_date→to_date) và fore_get_logs=True.
	"""
	import time
	from datetime import date as _date

	start_time = time.time()

	try:
		from customize_erpnext.overrides.shift_type.shift_type_optimized import (
			_core_process_attendance_logic_optimized,
		)

		# Parse và lọc ngày <= today
		raw_dates   = json.loads(affected_dates_json)
		today       = _date.today()
		days_list   = sorted([getdate(d) for d in raw_dates if getdate(d) <= today])

		if not days_list:
			frappe.logger().info(f"[Maternity] No past/today dates for {employee} — skip.")
			return

		total_days = len(days_list)
		frappe.logger().info(
			f"[Maternity] Background job started — {employee}: "
			f"{total_days} days ({from_date} → {to_date})"
		)

		stats = _core_process_attendance_logic_optimized(
			employees=[employee],
			days=days_list,
			from_date=from_date,
			to_date=to_date,
			fore_get_logs=True,
		)

		processing_time = round(time.time() - start_time, 2)
		frappe.logger().info(
			f"[Maternity] Done — {employee}: {total_days} days in {processing_time}s. "
			f"stats={stats}"
		)
		return stats

	except Exception as e:
		frappe.log_error(
			f"[Maternity] Background job failed for {employee}: {str(e)}",
			"Maternity Attendance Update Background Job Error",
		)
		raise


# =============================================================================
# Status Calculation API
# =============================================================================

@frappe.whitelist()
def calculate_all_maternity_statuses(names=None):
	"""
	Batch-recalculate `status` for Employee Maternity records.
	- names=None  → all records
	- names=[...] → only the given record names (JSON list or Python list)
	Returns: { updated: N, total: N }
	"""
	if names:
		if isinstance(names, str):
			names = json.loads(names)
		records = frappe.get_all(
			"Employee Maternity",
			filters=[["name", "in", names]],
			fields=["name"],
			order_by="creation desc",
		)
	else:
		records = frappe.get_all(
			"Employee Maternity",
			fields=["name"],
			order_by="creation desc",
		)

	updated = 0
	for r in records:
		doc = frappe.get_doc("Employee Maternity", r.name)
		old_status = doc.status or ""
		doc.calculate_status()
		new_status = doc.status or ""
		if new_status != old_status:
			doc.db_set("status", new_status, update_modified=False)
			updated += 1

	return {"updated": updated, "total": len(records)}


def scheduled_calculate_all_maternity_statuses():
	"""Scheduler wrapper — called by hooks.py cron at 00:00 daily."""
	try:
		result = calculate_all_maternity_statuses()
		frappe.logger().info(
			f"[Scheduler] Employee Maternity status recalc: "
			f"updated {result['updated']} / {result['total']} records"
		)
	except Exception as e:
		frappe.log_error(str(e), "Employee Maternity Scheduled Status Recalc Error")


# =============================================================================
# PowerQuery / Excel API
# =============================================================================

_MATERNITY_FIELDS = [
	"name", "employee", "employee_name", "group", "designation",
	"date_of_joining", "status", "apply_benefit", "note",
	"pregnant_from_date", "pregnant_to_date", "estimated_due_date",
	"maternity_from_date", "maternity_to_date", "date_of_birth",
	"youg_child_from_date", "youg_child_to_date",
	"gestational_age", "seniority",
]

_MATERNITY_LABELS_EN = {
	"name":               "ID",
	"employee":           "Employee ID",
	"employee_name":      "Full Name",
	"group":              "Group",
	"designation":        "Designation",
	"date_of_joining":    "Date of Joining",
	"status":             "Status",
	"apply_benefit":      "Apply Benefit",
	"note":               "Note",
	"pregnant_from_date": "Pregnant From",
	"pregnant_to_date":   "Pregnant To",
	"estimated_due_date": "Estimated Due Date",
	"maternity_from_date":"Maternity Leave From",
	"maternity_to_date":  "Maternity Leave To",
	"date_of_birth":      "Date of Birth (Child)",
	"youg_child_from_date":"Young Child From",
	"youg_child_to_date": "Young Child To",
	"gestational_age":    "Gestational Age (months)",
	"seniority":          "Seniority (months)",
}

_MATERNITY_LABELS_VI = {
	"name":               "Mã hồ sơ",
	"employee":           "Mã NV",
	"employee_name":      "Họ và tên",
	"group":              "Nhóm",
	"designation":        "Chức danh",
	"date_of_joining":    "Ngày vào làm",
	"status":             "Trạng thái",
	"apply_benefit":      "Áp dụng quyền lợi",
	"note":               "Ghi chú",
	"pregnant_from_date": "Ngày bắt đầu thai kỳ",
	"pregnant_to_date":   "Ngày kết thúc thai kỳ",
	"estimated_due_date": "Ngày dự sinh",
	"maternity_from_date":"Ngày bắt đầu nghỉ thai sản",
	"maternity_to_date":  "Ngày kết thúc nghỉ thai sản",
	"date_of_birth":      "Ngày sinh (con)",
	"youg_child_from_date":"Ngày bắt đầu con nhỏ",
	"youg_child_to_date": "Ngày kết thúc con nhỏ",
	"gestational_age":    "Tuổi thai (tháng)",
	"seniority":          "Thâm niên (tháng)",
}


@frappe.whitelist(allow_guest=True)
def get_employee_maternity_for_excel(
	employee=None,
	status=None,
	group=None,
	page=1,
	page_size=500,
	lang="en",
):
	"""
	API for Excel / Power Query – returns Employee Maternity list.

	Params:
		employee  : filter by employee ID
		status    : 'Pregnant' | 'Maternity Leave' | 'Young Child' | '' | None
		group     : filter by group
		page / page_size : pagination (page_size=0 → return all)
		lang      : 'en' (default) | 'vi'

	Returns:
		{ data, columns, col_keys, total, page, page_size, total_pages }
	"""
	from math import ceil
	from datetime import date as _date
	from dateutil.relativedelta import relativedelta as _rd

	page      = frappe.utils.cint(page)
	page_size = frappe.utils.cint(page_size)
	load_all  = page_size == 0
	if not load_all and (page_size < 0 or page_size > 2000):
		page_size = 500
	if page < 1:
		page = 1

	# Build WHERE
	conditions = []
	params = {}

	if employee:
		conditions.append("em.employee = %(employee)s")
		params["employee"] = employee

	if status is not None and status != "":
		conditions.append("em.status = %(status)s")
		params["status"] = status

	if group:
		conditions.append("em.`group` = %(group)s")
		params["group"] = group

	where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

	# Count
	total = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabEmployee Maternity` em {where_sql}",
		params,
	)[0][0]

	# Fetch rows (exclude virtual fields gestational_age & seniority)
	if load_all:
		rows = frappe.db.sql(
			f"""
			SELECT
				em.name, em.employee, emp.employee_name,
				em.`group`, em.designation, em.date_of_joining,
				em.status, em.apply_benefit, em.note,
				em.pregnant_from_date, em.pregnant_to_date, em.estimated_due_date,
				em.maternity_from_date, em.maternity_to_date, em.date_of_birth,
				em.youg_child_from_date, em.youg_child_to_date
			FROM `tabEmployee Maternity` em
			LEFT JOIN `tabEmployee` emp ON emp.name = em.employee
			{where_sql}
			ORDER BY em.employee
			""",
			params,
			as_dict=True,
		)
		page_size = total or 0
		page = 1
	else:
		offset = (page - 1) * page_size
		params["limit"]  = page_size
		params["offset"] = offset
		rows = frappe.db.sql(
			f"""
			SELECT
				em.name, em.employee, emp.employee_name,
				em.`group`, em.designation, em.date_of_joining,
				em.status, em.apply_benefit, em.note,
				em.pregnant_from_date, em.pregnant_to_date, em.estimated_due_date,
				em.maternity_from_date, em.maternity_to_date, em.date_of_birth,
				em.youg_child_from_date, em.youg_child_to_date
			FROM `tabEmployee Maternity` em
			LEFT JOIN `tabEmployee` emp ON emp.name = em.employee
			{where_sql}
			ORDER BY em.employee
			LIMIT %(limit)s OFFSET %(offset)s
			""",
			params,
			as_dict=True,
		)

	# Compute virtual fields + sanitize
	today_date = _date.today()
	cleaned = []
	for row in rows:
		r = {}
		for k, v in row.items():
			if v is None:
				r[k] = ""
			elif hasattr(v, "isoformat"):
				r[k] = v.isoformat()
			else:
				r[k] = v

		# gestational_age
		edd = row.get("estimated_due_date")
		if edd:
			edd_date = getdate(edd)
			if edd_date <= today_date:
				r["gestational_age"] = 9.5
			else:
				diff = _rd(edd_date, today_date)
				months_diff = diff.years * 12 + diff.months
				r["gestational_age"] = round(9.5 - (months_diff + 1), 1)
		else:
			r["gestational_age"] = ""

		# seniority
		doj = row.get("date_of_joining")
		if doj:
			diff = _rd(today_date, getdate(doj))
			r["seniority"] = diff.years * 12 + diff.months
		else:
			r["seniority"] = ""

		cleaned.append(r)

	label_dict = _MATERNITY_LABELS_VI if lang == "vi" else _MATERNITY_LABELS_EN
	columns    = [label_dict.get(f, f) for f in _MATERNITY_FIELDS]

	return {
		"data":        cleaned,
		"columns":     columns,
		"col_keys":    _MATERNITY_FIELDS,
		"total":       total,
		"page":        page,
		"page_size":   page_size,
		"total_pages": ceil(total / page_size) if page_size else 1,
	}


# =============================================================================
# Invalid Records API
# =============================================================================

@frappe.whitelist()
def get_invalid_maternity_records():
	"""
	Find Employee Maternity records where consecutive phases are not exactly 1 day apart:
	  - pregnant_to_date → maternity_from_date gap ≠ 1 day
	  - maternity_to_date → youg_child_from_date gap ≠ 1 day

	Returns list of { name, employee, employee_name, issues: [...] }
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			em.name, em.employee, emp.employee_name,
			em.pregnant_to_date, em.maternity_from_date,
			em.maternity_to_date, em.youg_child_from_date
		FROM `tabEmployee Maternity` em
		LEFT JOIN `tabEmployee` emp ON emp.name = em.employee
		WHERE
			(em.pregnant_to_date IS NOT NULL AND em.maternity_from_date IS NOT NULL
			 AND DATEDIFF(em.maternity_from_date, em.pregnant_to_date) != 1)
			OR
			(em.maternity_to_date IS NOT NULL AND em.youg_child_from_date IS NOT NULL
			 AND DATEDIFF(em.youg_child_from_date, em.maternity_to_date) != 1)
		ORDER BY em.employee
		""",
		as_dict=True,
	)

	result = []
	for r in rows:
		issues = []
		if r.pregnant_to_date and r.maternity_from_date:
			gap = (getdate(r.maternity_from_date) - getdate(r.pregnant_to_date)).days
			if gap != 1:
				issues.append(
					f"Pregnant → Maternity Leave: gap {gap} day(s) "
					f"({r.pregnant_to_date} → {r.maternity_from_date})"
				)
		if r.maternity_to_date and r.youg_child_from_date:
			gap = (getdate(r.youg_child_from_date) - getdate(r.maternity_to_date)).days
			if gap != 1:
				issues.append(
					f"Maternity Leave → Young Child: gap {gap} day(s) "
					f"({r.maternity_to_date} → {r.youg_child_from_date})"
				)
		if issues:
			result.append({
				"name":          r.name,
				"employee":      r.employee,
				"employee_name": r.employee_name or "",
				"issues":        issues,
			})

	return result
