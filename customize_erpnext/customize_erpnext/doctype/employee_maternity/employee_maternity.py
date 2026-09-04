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


def _has_left(relieving_date, employee_status, on_date):
	"""Nhân viên đã rời công ty tính đến `on_date` chưa?

	⚠ `relieving_date` là ngày **bắt đầu** nghỉ việc, không phải ngày làm cuối —
	ngày làm cuối là `relieving_date - 1`. Nên "còn làm tại ngày X" là
	`relieving_date > X`, và đã nghỉ là `relieving_date <= X`.

	`relieving_date` được ưu tiên hơn `Employee.status`: job `auto_mark_employees_as_left`
	chạy 00:00 chỉ đổi status cho người đang `Active`, nên một người đang thai sản
	(status = `Inactive`) tới ngày nghỉ vẫn không được đổi sang `Left`. Chỉ nhìn status
	là bỏ sót đúng nhóm người mà module này quan tâm.

	⚠ `.strip()` là bắt buộc: trên site này **1.393 Employee mang status `"Left "` có dấu
	cách ở cuối**. MySQL so sánh kiểu PAD SPACE nên `WHERE status = 'Left'` vẫn khớp và
	không ai phát hiện ra, nhưng `"Left " == "Left"` trong Python là **False** — so trần
	thì nhánh fallback này im lặng bỏ sót đúng những người nó sinh ra để bắt.
	"""
	if relieving_date and getdate(relieving_date) <= on_date:
		return True
	return (employee_status or "").strip() == "Left"


def make_maternity_name(employee, exclude=None):
	"""Tên hồ sơ thai sản: `HR-EM-{employee}`.

	Một nhân viên có thể có nhiều chu kỳ thai sản, nên hồ sơ thứ 2, 3... được
	thêm hậu tố `-1`, `-2`. `exclude` là tên hiện tại của record đang được đổi
	tên — nó không bị coi là trùng với chính nó.
	"""
	if not employee:
		frappe.throw(_("Employee is required before naming an Employee Maternity record"))

	base = f"HR-EM-{employee}"
	candidate = base
	idx = 0
	while candidate != exclude and frappe.db.exists("Employee Maternity", candidate):
		idx += 1
		candidate = f"{base}-{idx}"

	return candidate


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
		"""Tuổi thai — CHỈ có nghĩa ở giai đoạn `Pregnant`.

		Sau khi sinh, `estimated_due_date` đã lùi vào quá khứ nên
		`_gestational_age_months()` kẹp về 9,5 và giai đoạn `Maternity Leave` /
		`Young Child` hiện "tuổi thai 9,5 tháng" — vô nghĩa với người đã sinh xong.
		Đo 04/09/2026: HR-EM-TIQN-0919 (Young Child, con sinh 15/03/2026) và
		HR-EM-TIQN-1478 (Maternity Leave) đều báo 9,5.

		Report `employee_maternity_report` vốn đã chặn đúng (`period["type"] ==
		"Pregnant"`); đây là chỗ form và API Excel còn sót.

		⚠ Trả `None` KHÔNG đủ để ô trống: field là `Float` nên Frappe ép về `0.0` khi
		dựng doc. Vì vậy field còn mang `depends_on: eval:doc.status=="Pregnant"` trong
		doctype json — đó mới là thứ giấu hẳn ô khỏi form. API Excel trả chuỗi rỗng.
		"""
		if (self.status or "") != "Pregnant":
			return None
		return _gestational_age_months(self.estimated_due_date)

	# =========================================================================
	# Naming
	# =========================================================================

	def autoname(self):
		"""HR-EM-{employee}, thêm hậu tố -1, -2... cho hồ sơ thứ 2, 3 của cùng
		nhân viên (mỗi record là 1 chu kỳ thai sản)."""
		self.name = make_maternity_name(self.employee)

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
		  maternity_to_date    = effective maternity start + 6 months - 1 day (only if empty)
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
			# +6 tháng rồi lùi 1 ngày: nghỉ từ 19/01 thì hết ngày 18/07, đúng 6 tháng.
			# Không trừ 1 ngày thì thành 6 tháng 1 ngày.
			self.maternity_to_date = add_days(add_months(getdate(effective_mat_from), 6), -1)

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

	def employee_has_left(self, on_date=None, employment=None):
		"""Nhân viên của record này đã nghỉ việc tính đến `on_date` chưa?

		`employment`: dict `{relieving_date, status}` đã tra sẵn — batch truyền vào để
		khỏi bắn thêm một query cho mỗi record. Truyền `{}` nghĩa là "đã tra, không có
		dữ liệu"; để `None` thì tự tra.
		"""
		if not self.employee:
			return False
		if employment is None:
			employment = frappe.db.get_value(
				"Employee", self.employee, ["relieving_date", "status"], as_dict=True
			) or {}
		if not employment:
			return False
		return _has_left(
			employment.get("relieving_date"), employment.get("status"), on_date or date.today()
		)

	def calculate_status(self, employment=None):
		"""Set status field based on which date period today falls into.
		If today falls in multiple periods (data legacy), pick the one with the latest from_date.
		Maternity phase falls back to maternity_from_date_estimate when the actual date
		is not yet known, so status is not blank during actual leave.

		Nghỉ việc thì cắt hết: xem `employee_has_left()`.
		"""
		today_date = date.today()

		if self.employee_has_left(today_date, employment):
			# Đã nghỉ việc = chấm dứt chế độ, kể cả khi ngày kết thúc giai đoạn còn ở
			# tương lai. Không có "con nhỏ" hay "nghỉ thai sản" cho người không còn
			# trong bảng lương — cứ để status chạy tiếp thì report, dashboard và
			# `custom_sub_status` trên form Employee đều báo họ đang hưởng chế độ.
			# Ngày tháng của record giữ nguyên: đó là lịch sử, chỉ trạng thái là đóng.
			self.status = "Inactive"
			return

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
					"apply_hour_reduction",
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
	_sync_maternity_flag_on_save(doc)


def _sync_maternity_flag_on_save(doc):
	"""Ghi lại `Employee.custom_is_maternity_leave` cho nhân viên của record này.

	Đổi employee giữa chừng: phải ghi lại cho CẢ HAI, vì record này không còn mô tả
	người cũ nữa. `sync_maternity_flag` tự tra lại DB nên không cần truyền trạng thái
	cũ/mới — một nhân viên có thể giữ nhiều hồ sơ, rời khỏi một hồ sơ không chứng minh
	được họ đã đi làm lại.
	"""
	from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
		sync_maternity_flag,
	)

	old_doc = None if doc.is_new() else doc.get_doc_before_save()
	if old_doc and old_doc.employee and old_doc.employee != doc.employee:
		sync_maternity_flag(old_doc.employee)

	sync_maternity_flag(doc.employee)


def on_maternity_delete(doc, method):
	affected_dates = set()
	doc._add_all_ranges(affected_dates, doc)

	if affected_dates:
		doc._maternity_recalc_jobs = {doc.employee: sorted(affected_dates)}
		_queue_attendance_recalculation(doc, "on_trash")

	from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
		sync_maternity_flag,
	)

	# Record biến mất = giai đoạn của nó cũng biến mất theo. `on_trash` chạy TRƯỚC khi
	# dòng bị xoá khỏi DB nên phải loại nó ra, nếu không record đang xoá vẫn tự đếm
	# mình và cờ không bao giờ được gỡ.
	sync_maternity_flag(doc.employee, exclude_record=doc.name)


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
	Returns: { updated: N, total: N, closed_for_left: N }

	`closed_for_left` đếm riêng số record bị đóng vì nhân viên đã nghỉ việc — đây là
	nhóm không tự đóng theo ngày tháng, nên tách ra để đọc log cho rõ.
	"""
	if names:
		if isinstance(names, str):
			names = json.loads(names)
		records = frappe.get_all(
			"Employee Maternity",
			filters=[["name", "in", names]],
			fields=["name", "employee"],
			order_by="creation desc",
		)
	else:
		records = frappe.get_all(
			"Employee Maternity",
			fields=["name", "employee"],
			order_by="creation desc",
		)

	# Tra một lần cho cả lô: job này quét toàn bảng, hỏi Employee từng record là
	# thêm vài trăm query mỗi đêm chỉ để đọc 2 field.
	employee_ids = sorted({r.employee for r in records if r.employee})
	employment = {}
	if employee_ids:
		employment = {
			row.name: row
			for row in frappe.get_all(
				"Employee",
				filters=[["name", "in", employee_ids]],
				fields=["name", "relieving_date", "status"],
			)
		}

	from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
		sync_all_maternity_flags,
	)

	updated = 0
	closed_for_left = 0
	for r in records:
		doc = frappe.get_doc("Employee Maternity", r.name)
		old_status = doc.status or ""
		# `or {}` chứ không để None: nhân viên đã bị xoá thì coi như "đã tra, không có
		# dữ liệu", tránh doc tự bắn lại query chỉ để nhận cùng một kết quả rỗng.
		doc.calculate_status(employment=employment.get(doc.employee) or {})
		new_status = doc.status or ""
		if new_status != old_status:
			doc.db_set("status", new_status, update_modified=False)
			updated += 1
			if doc.employee_has_left(employment=employment.get(doc.employee) or {}):
				closed_for_left += 1

	# 🔴 Khẳng định lại cờ cho TOÀN BỘ nhân viên, không chỉ record vừa đổi giai đoạn.
	# Bản cũ chỉ đồng bộ khi có chuyển tiếp, nên khi một thao tác cập nhật Employee
	# hàng loạt ghi đè mất giá trị (25/08/2026, 34 người) thì không lần chạy nào sau
	# đó sửa lại. Hai câu UPDATE theo tập, rẻ hơn nhiều so với lặp từng người.
	flags = sync_all_maternity_flags()

	return {
		"updated": updated,
		"total": len(records),
		"closed_for_left": closed_for_left,
		"flags_set": flags["set"],
		"flags_cleared": flags["cleared"],
	}


def scheduled_calculate_all_maternity_statuses():
	"""Scheduler wrapper — called by hooks.py cron at 00:10 daily.

	⚠ 00:10 chứ không 00:00: `auto_mark_employees_as_left` chạy lúc 00:00 và phải
	xong trước, để người vừa tới ngày nghỉ việc đã mang status `Left` khi job này
	quét qua. Đổi giờ một trong hai job thì phải giữ nguyên thứ tự này.
	"""
	try:
		result = calculate_all_maternity_statuses()
		frappe.logger().info(
			f"[Scheduler] Employee Maternity status recalc: "
			f"updated {result['updated']} / {result['total']} records "
			f"({result['closed_for_left']} đóng vì nhân viên đã nghỉ việc); "
			f"cờ thai sản: bật {result['flags_set']}, gỡ {result['flags_cleared']}"
		)
	except Exception as e:
		frappe.log_error(str(e), "Employee Maternity Scheduled Status Recalc Error")


# =============================================================================
# PowerQuery / Excel API
# =============================================================================

_MATERNITY_FIELDS = [
	"name", "employee", "employee_name", "group", "designation",
	"date_of_joining", "status", "apply_hour_reduction", "note",
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
	"apply_hour_reduction": "Apply Hour Reduction",
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
	"apply_hour_reduction": "Áp dụng giảm 1 giờ",
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
				em.status, em.apply_hour_reduction, em.note,
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
				em.status, em.apply_hour_reduction, em.note,
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

		# gestational_age — chỉ giai đoạn Pregnant, xem property cùng tên
		edd = row.get("estimated_due_date")
		r["gestational_age"] = (
			_gestational_age_months(edd, today_date)
			if edd and (row.get("status") or "") == "Pregnant"
			else ""
		)

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
