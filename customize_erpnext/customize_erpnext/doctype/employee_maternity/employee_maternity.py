# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, add_days, add_months, today
from frappe.model.document import Document
from datetime import date
from dateutil.relativedelta import relativedelta
import json


def _gestational_age_months(estimated_due_date, on_date=None):
	"""Gestational age in months, clamped to [0, 9.5].
	Formula: 9.5 - (DATEDIF(on_date, estimated_due_date, 'm') + 1)"""
	if not estimated_due_date:
		return 0
	on_date = on_date or date.today()
	edd = getdate(estimated_due_date)
	if edd <= on_date:
		return 9.5
	rd = relativedelta(edd, on_date)
	months_diff = rd.years * 12 + rd.months
	return max(0, min(9.5, round(9.5 - (months_diff + 1), 1)))


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
		return _gestational_age_months(self.estimated_due_date)

	# =========================================================================
	# Validation
	# =========================================================================

	def validate(self):
		self.calculate_derived_dates()
		self.validate_dates()
		self.validate_date_overlap()
		self.calculate_status()

	def calculate_derived_dates(self):
		"""Auto-calculate derived dates. Mirrors _recalculate_derived() in employee_maternity.js
		so UI save and Data Import produce the same result.

		effective maternity start = maternity_from_date, fallback maternity_from_date_estimate.

		Rules:
		  pregnant_to_date     = effective maternity start - 1 day
		                         (fallback: estimated_due_date; never cleared)
		  maternity_to_date    = effective maternity start + 6 months (only if empty)
		  youg_child_from_date = maternity_to_date + 1 day
		  youg_child_to_date   = date_of_birth + 364 days

		During Data Import, values are never cleared — only overridden when a
		source field to derive from is present (imported legacy records may have
		phase dates without the source fields).
		"""
		in_import = bool(frappe.flags.in_import)
		effective_mat_from = self.maternity_from_date or self.maternity_from_date_estimate

		if self.pregnant_from_date:
			if effective_mat_from:
				self.pregnant_to_date = add_days(getdate(effective_mat_from), -1)
			elif self.estimated_due_date:
				self.pregnant_to_date = getdate(self.estimated_due_date)

		if effective_mat_from and not self.maternity_to_date:
			self.maternity_to_date = add_months(getdate(effective_mat_from), 6)

		if self.maternity_to_date:
			self.youg_child_from_date = add_days(getdate(self.maternity_to_date), 1)
		elif not in_import:
			self.youg_child_from_date = None

		if self.date_of_birth:
			self.youg_child_to_date = add_days(getdate(self.date_of_birth), 364)

	def validate_dates(self):
		"""Validate from <= to for each date pair (a phase may be a single day)."""
		pairs = [
			("pregnant_from_date", "pregnant_to_date", _("Pregnant")),
			("maternity_from_date", "maternity_to_date", _("Maternity Leave")),
			("youg_child_from_date", "youg_child_to_date", _("Young Child")),
		]

		for from_field, to_field, label in pairs:
			from_date = self.get(from_field)
			to_date = self.get(to_field)
			if from_date and to_date:
				if getdate(from_date) > getdate(to_date):
					frappe.throw(
						_("{0}: From Date cannot be after To Date").format(label)
					)

	def calculate_status(self):
		"""Set status field based on which date period today falls into.
		If today falls in multiple periods (data legacy), pick the one with the latest from_date.
		Maternity phase falls back to maternity_from_date_estimate when the actual date
		is not yet known, so status is not blank during actual leave."""
		today_date = date.today()
		effective_mat_from = self.maternity_from_date or self.maternity_from_date_estimate

		active = []  # list of (from_date, status_label)
		checks = [
			(self.pregnant_from_date, self.pregnant_to_date, "Pregnant"),
			(effective_mat_from,      self.maternity_to_date, "Maternity Leave"),
			(self.youg_child_from_date, self.youg_child_to_date, "Young Child"),
		]
		for from_val, to_val, label in checks:
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

		# Period không có end_date được coi là open-ended (kéo dài vô hạn)
		names = list(periods.keys())

		for i in range(len(names)):
			for j in range(i + 1, len(names)):
				a_name, b_name = names[i], names[j]
				a_from, a_to = periods[a_name]
				b_from, b_to = periods[b_name]
				# Overlap nếu: a_from <= b_to AND b_from <= a_to
				if a_from <= (b_to or date.max) and b_from <= (a_to or date.max):
					frappe.throw(
						_("Date periods overlap between {0} ({1} → {2}) and {3} ({4} → {5})").format(
							_(a_name), a_from, a_to or _("ongoing"),
							_(b_name), b_from, b_to or _("ongoing"),
						)
					)

	# =========================================================================
	# Attendance Recalculation Triggers
	# =========================================================================

	def before_save(self):
		self._collect_affected_dates()

	def _collect_affected_dates(self):
		"""So sánh old vs new để tìm các ngày cần recalc attendance.
		Nếu đổi employee, thu thập ngày cho CẢ employee cũ lẫn mới
		(employee cũ cần clear trạng thái maternity trên attendance)."""
		jobs = {}  # employee -> set of date strings

		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc:
				# Kiểm tra có thay đổi không
				# Include source fields that trigger derived-date recalculation
				tracked_fields = [
					"employee",
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

				# Collect all old date ranges (theo employee cũ)
				old_dates = set()
				self._add_all_ranges(old_dates, old_doc)
				if old_dates:
					jobs.setdefault(old_doc.employee, set()).update(old_dates)

		# Collect new date ranges
		new_dates = set()
		self._add_all_ranges(new_dates, self)
		if new_dates:
			jobs.setdefault(self.employee, set()).update(new_dates)

		if jobs:
			self._maternity_recalc_jobs = {emp: sorted(dates) for emp, dates in jobs.items()}

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

def on_maternity_update(doc, method):
	# Frappe chạy on_update sau CẢ insert lẫn save — không cần hook after_insert riêng
	# (dates đã được thu thập trong before_save, hook này chạy cho cả doc mới)
	_queue_attendance_recalculation(doc, "on_update")


def on_maternity_delete(doc, method):
	affected_dates = set()
	doc._add_all_ranges(affected_dates, doc)

	if affected_dates:
		doc._maternity_recalc_jobs = {doc.employee: sorted(affected_dates)}
		_queue_attendance_recalculation(doc, "on_trash")


def _queue_attendance_recalculation(doc, trigger):
	"""Queue background job để recalculate attendance cho các ngày bị ảnh hưởng
	(mỗi employee bị ảnh hưởng 1 job — thường 1, là 2 khi record đổi employee).
	Hoạt động cho cả: UI save, Data Import (add new / update if exist), on_trash.

	Gated by setting recalc_attendance_on_maternity_change
	(label: "Recalc Attendance on Maternity Save/Delete", default OFF):
	khi tắt, attendance cập nhật ở lần chạy full kế tiếp hoặc Bulk Update thủ công.
	"""
	try:
		from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
			get_attendance_settings,
		)
		if not frappe.utils.cint(get_attendance_settings().recalc_attendance_on_maternity_change):
			return

		jobs = getattr(doc, "_maternity_recalc_jobs", None)
		if not jobs:
			return

		for employee, affected_dates in jobs.items():
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
				# Job chỉ được đẩy vào queue sau khi transaction commit —
				# tránh worker recalc khi record chưa thực sự lưu/xóa
				enqueue_after_commit=True,
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
		from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import is_peak_time

		# Skip during check-in/out peak windows — next full run catches up
		if is_peak_time():
			frappe.logger().info(f"[Maternity] Peak time — skipped recalc for {employee}")
			return

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


@frappe.whitelist()
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
	Requires an authenticated session or API key
	(Authorization: token <api_key>:<api_secret>) — dữ liệu thai sản nhạy cảm,
	không mở allow_guest.

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
		r["gestational_age"] = _gestational_age_months(edd, today_date) if edd else ""

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
