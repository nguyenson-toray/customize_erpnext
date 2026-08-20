# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Attendance Request override — supplement missing check in / check out.

The stock HRMS Attendance Request marks attendance for a period (Work From Home /
On Duty). At TIQN the doctype is also used for a second, more common purpose:
requesting that a MISSING check in or check out be added, because the employee
forgot to scan, the machine failed, or it was their first working day.

Mode is derived from `reason`:
  - reason in SUPPLEMENT_REASONS  -> supplement mode (this file's logic)
  - reason in (Work From Home, On Duty) -> untouched HRMS behaviour via super()

Supplement mode flow:
  validate  -> sync one child row per date, refresh the "existing" columns
  on_submit -> create Employee Checkin records, then re-run the attendance engine
  on_cancel -> delete those check-ins, then re-run the attendance engine

See docs/attendance_request_supplement_plan.md for the full design.
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	date_diff,
	flt,
	format_date,
	get_datetime,
	get_link_to_form,
	get_time,
	getdate,
)

from hrms.hr.doctype.attendance_request.attendance_request import AttendanceRequest
from hrms.hr.utils import validate_active_employee, validate_dates

# Reasons that switch the request into "supplement check in/out" mode.
# These values MUST stay identical to the options of
# Employee Checkin.custom_reason_for_manual_check_in so the reason can be copied
# straight onto the created check-in with no mapping table.
# Mirrored in public/js/custom_scripts/attendance_request.js — keep both in sync.
SUPPLEMENT_REASONS = (
	"Forget Check In/Out",
	"Machine Error",
	"First Working Day",
	"Other",
)

# Two check-ins closer than this are treated as the same scan.
DUPLICATE_TOLERANCE_MINUTES = 1


class CustomAttendanceRequest(AttendanceRequest):
	# ------------------------------------------------------------------
	# mode
	# ------------------------------------------------------------------
	@property
	def is_supplement(self) -> bool:
		return self.reason in SUPPLEMENT_REASONS

	# ------------------------------------------------------------------
	# validate
	# ------------------------------------------------------------------
	def validate(self):
		if not self.is_supplement:
			return super().validate()

		validate_active_employee(self.employee)
		validate_dates(self, self.from_date, self.to_date, False)
		self.validate_shifts()

		self.sync_checkin_rows()
		self.refresh_existing_times()
		self.validate_supplement_rows()
		self.validate_supplement_overlap()

		# Deliberately NOT calling three HRMS validations here:
		# - validate_no_attendance_to_create(): the dates being supplemented almost
		#   always already have an Attendance record, so it throws "Attendance status
		#   unchanged" and would block every single supplement request.
		# - validate_request_overlap(): blocks on the whole from_date..to_date period,
		#   which makes it impossible to file one request for a missing IN and another
		#   for a missing OUT on the same day. Replaced by validate_supplement_overlap(),
		#   which collides per date AND per side.
		# - validate_half_day(): half day is irrelevant here (the field is hidden by JS).

	def sync_checkin_rows(self):
		"""Keep exactly one child row per date in from_date..to_date.

		Rows already carrying user-entered times are preserved; rows that fall
		outside the (possibly edited) period are dropped.
		"""
		wanted = [
			getdate(add_days(self.from_date, day))
			for day in range(date_diff(self.to_date, self.from_date) + 1)
		]
		existing = {getdate(row.date): row for row in (self.custom_checkin_details or []) if row.date}

		rows = []
		for day in wanted:
			row = existing.get(day)
			if not row:
				row = frappe.new_doc("Attendance Request Checkin Detail")
				row.date = day
			row.day_of_week = day.strftime("%a")
			rows.append(row)

		self.set("custom_checkin_details", [])
		for idx, row in enumerate(rows, start=1):
			row.idx = idx
			self.append("custom_checkin_details", row)

	def refresh_existing_times(self):
		"""Fill the read-only existing_* columns from the Attendance of that date.

		Runs on every save so the stored snapshot is never stale. The client fills
		the same columns live (before any save) via get_existing_attendance_info().
		"""
		attendance_map = self._get_attendance_map()

		for row in self.custom_checkin_details:
			att = attendance_map.get(getdate(row.date))
			row.existing_status = att.status if att else "-"
			row.existing_in_time = _format_hhmm(att.in_time) if att else None
			row.existing_out_time = _format_hhmm(att.out_time) if att else None
			row.existing_working_hours = flt(att.working_hours, 2) if att else 0

	def validate_supplement_rows(self):
		rows_with_time = [
			row for row in self.custom_checkin_details if row.new_in_time or row.new_out_time
		]
		if not rows_with_time:
			frappe.throw(
				_("Enter at least one New In or New Out time to supplement."),
				title=_("Nothing to Supplement"),
			)

		if self.reason == "Other" and not (self.explanation or "").strip():
			frappe.throw(_("Explanation is mandatory when the reason is {0}.").format(frappe.bold(_("Other"))))

		checkin_map = self._get_checkin_map()
		attendance_map = self._get_attendance_map()

		for row in rows_with_time:
			day = getdate(row.date)
			label = format_date(day)
			new_in = get_time(row.new_in_time) if row.new_in_time else None
			new_out = get_time(row.new_out_time) if row.new_out_time else None

			if new_in and new_out and new_in >= new_out:
				frappe.throw(
					_("Row #{0} ({1}): New In must be earlier than New Out.").format(row.idx, label)
				)

			# The supplemented time must stay on the correct side of what is already there
			if new_in and row.existing_out_time and str(new_in)[:5] >= row.existing_out_time:
				frappe.throw(
					_("Row #{0} ({1}): New In {2} must be earlier than the existing check out {3}.").format(
						row.idx, label, str(new_in)[:5], row.existing_out_time
					)
				)
			if new_out and row.existing_in_time and str(new_out)[:5] <= row.existing_in_time:
				frappe.throw(
					_("Row #{0} ({1}): New Out {2} must be later than the existing check in {3}.").format(
						row.idx, label, str(new_out)[:5], row.existing_in_time
					)
				)

			# Never create a duplicate scan
			for new_time, field_label in ((new_in, _("New In")), (new_out, _("New Out"))):
				if not new_time:
					continue
				clash = _find_clashing_checkin(checkin_map.get(day, []), day, new_time)
				if clash:
					frappe.throw(
						_("Row #{0} ({1}): {2} {3} already exists as check-in {4}.").format(
							row.idx,
							label,
							field_label,
							str(new_time)[:5],
							get_link_to_form("Employee Checkin", clash),
						),
						title=_("Duplicate Check-in"),
					)

			# Both sides already recorded — allowed (it may be a genuine correction),
			# but the approver should notice.
			#
			# Judge on the real datetimes, never on "both columns are filled": a
			# double tap on the machine (seen live: 19:03:41 then 19:03:43) makes the
			# engine store in_time AND out_time, both of which format to the same
			# "19:03". That day is missing its check IN — warning that it is already
			# complete would be plainly wrong.
			if _has_real_span(attendance_map.get(day)):
				att = attendance_map[day]
				frappe.msgprint(
					_("{0} already has both a check in ({1}) and a check out ({2}).").format(
						label, _format_hhmm(att.in_time), _format_hhmm(att.out_time)
					),
					title=_("Attendance Already Complete"),
					indicator="orange",
				)

	def validate_supplement_overlap(self):
		"""Block a second submitted request that supplements the same date and side."""
		dates = [getdate(row.date) for row in self.custom_checkin_details if row.new_in_time or row.new_out_time]
		if not dates:
			return

		submitted = frappe.db.sql(
			"""
			SELECT p.name, d.date, d.new_in_time, d.new_out_time
			FROM `tabAttendance Request Checkin Detail` d
			JOIN `tabAttendance Request` p ON p.name = d.parent
			WHERE p.employee = %(employee)s
			  AND p.docstatus = 1
			  AND p.name != %(name)s
			  AND d.date IN %(dates)s
			""",
			{"employee": self.employee, "name": self.name or "", "dates": tuple(dates)},
			as_dict=True,
		)
		if not submitted:
			return

		by_date = {}
		for other in submitted:
			by_date.setdefault(getdate(other.date), []).append(other)

		for row in self.custom_checkin_details:
			for other in by_date.get(getdate(row.date), []):
				if row.new_in_time and other.new_in_time:
					self._throw_duplicate_supplement(row, other.name, _("check in"))
				if row.new_out_time and other.new_out_time:
					self._throw_duplicate_supplement(row, other.name, _("check out"))

	def _throw_duplicate_supplement(self, row, other_request: str, side: str):
		frappe.throw(
			_("The {0} of {1} was already supplemented by {2}.").format(
				side,
				frappe.bold(format_date(row.date)),
				get_link_to_form("Attendance Request", other_request),
			),
			title=_("Already Supplemented"),
		)

	# ------------------------------------------------------------------
	# submit
	# ------------------------------------------------------------------
	def on_submit(self):
		if not self.is_supplement:
			return super().on_submit()

		created = self.create_supplement_checkins()
		self.recalculate_attendance()

		frappe.msgprint(
			_("Created {0} check-in(s) and recalculated attendance.").format(len(created)),
			title=_("Attendance Supplemented"),
			indicator="green",
		)

	def create_supplement_checkins(self) -> list:
		created = []
		for row in self.custom_checkin_details:
			if row.new_in_time:
				name = self._create_checkin(row.date, row.new_in_time, "IN")
				row.db_set("created_checkin_in", name)
				created.append(name)
			if row.new_out_time:
				name = self._create_checkin(row.date, row.new_out_time, "OUT")
				row.db_set("created_checkin_out", name)
				created.append(name)
		return created

	def _create_checkin(self, day, time_value, log_type: str) -> str:
		checkin = frappe.new_doc("Employee Checkin")
		checkin.employee = self.employee
		checkin.time = get_datetime(f"{getdate(day)} {get_time(time_value)}")
		# log_type is a best guess; the after_insert hook update_employee_checkin()
		# re-derives IN/OUT from the position of the scan within the day
		checkin.log_type = log_type
		checkin.shift = self.shift
		checkin.skip_auto_attendance = 0
		checkin.custom_reason_for_manual_check_in = self.reason
		if self.reason == "Other":
			checkin.custom_other_reason_for_manual_check_in = self.explanation
		checkin.custom_attendance_request = self.name
		checkin.insert(ignore_permissions=True)
		return checkin.name

	# ------------------------------------------------------------------
	# cancel
	# ------------------------------------------------------------------
	def on_cancel(self):
		if not self.is_supplement:
			return super().on_cancel()

		deleted = self.delete_supplement_checkins()
		self.recalculate_attendance()

		frappe.msgprint(
			_("Removed {0} check-in(s) and recalculated attendance.").format(deleted),
			title=_("Supplement Reverted"),
			indicator="orange",
		)

	def delete_supplement_checkins(self) -> int:
		from customize_erpnext.overrides.employee_checkin.employee_checkin import (
			update_remaining_checkins_after_delete,
		)

		names = frappe.get_all(
			"Employee Checkin",
			filters={"custom_attendance_request": self.name},
			pluck="name",
			order_by="time asc",
		)

		# Drop our own references BEFORE deleting anything. The child fields
		# created_checkin_in / created_checkin_out are Link fields pointing at
		# Employee Checkin, so frappe.delete_doc() refuses with "Cannot delete or
		# cancel because Employee Checkin X is linked with Attendance Request Y"
		# while they still hold the name. Clearing afterwards is too late.
		for row in self.custom_checkin_details:
			if row.created_checkin_in:
				row.db_set("created_checkin_in", None)
			if row.created_checkin_out:
				row.db_set("created_checkin_out", None)

		affected = []
		deleted = 0
		for name in names:
			doc = frappe.db.get_value("Employee Checkin", name, ["employee", "time"], as_dict=True)
			if not doc:
				continue
			# Unlink from Attendance first: Employee Checkin.on_trash has no guard, but
			# a linked attendance would otherwise keep a dangling reference
			frappe.db.set_value("Employee Checkin", name, "attendance", None, update_modified=False)
			frappe.delete_doc("Employee Checkin", name, ignore_permissions=True)
			affected.append(doc)
			deleted += 1

		# Re-derive IN/OUT of the survivors. This helper exists in the checkin
		# override but is NOT registered in doc_events, so it must be called by hand.
		for doc in affected:
			update_remaining_checkins_after_delete(frappe._dict(doc), "after_delete")

		return deleted

	# ------------------------------------------------------------------
	# attendance engine
	# ------------------------------------------------------------------
	def recalculate_attendance(self):
		"""Re-run the attendance engine for this employee on the affected dates.

		Calls the core function directly rather than _recalculate_attendance() in the
		checkin override: that wrapper is gated by the peak-time window and by the
		"Recalc Attendance on Checkin Save/Delete" setting (default OFF), so it would
		silently do nothing right after the user pressed Submit.
		"""
		from customize_erpnext.overrides.shift_type.shift_type_optimized import (
			_core_process_attendance_logic_optimized,
		)

		days = sorted(
			{
				getdate(row.date)
				for row in self.custom_checkin_details
				if row.new_in_time or row.new_out_time
			}
		)
		if not days:
			return

		try:
			_core_process_attendance_logic_optimized(
				employees=[self.employee],
				days=days,
				from_date=str(days[0]),
				to_date=str(days[-1]),
				fore_get_logs=True,
			)
		except Exception:
			frappe.log_error(
				title=f"Attendance Request {self.name}: attendance recalculation failed",
				message=frappe.get_traceback(),
			)
			frappe.msgprint(
				_(
					"Check-ins were saved but the attendance recalculation failed. "
					"Run Bulk Update Attendance for {0} from {1} to {2}."
				).format(frappe.bold(self.employee), format_date(days[0]), format_date(days[-1])),
				title=_("Recalculation Failed"),
				indicator="red",
			)

	# ------------------------------------------------------------------
	# UI helpers
	# ------------------------------------------------------------------
	@frappe.whitelist()
	def get_attendance_warnings(self) -> list:
		"""HRMS renders these as a banner on refresh.

		In supplement mode every date would report "Attendance status unchanged",
		which is noise here — the child table already shows the real state.
		"""
		if self.is_supplement:
			return []
		return super().get_attendance_warnings()

	# ------------------------------------------------------------------
	# data loading
	# ------------------------------------------------------------------
	def _get_attendance_map(self) -> dict:
		return get_attendance_map(self.employee, self.from_date, self.to_date)

	def _get_checkin_map(self) -> dict:
		return get_checkin_map(self.employee, self.from_date, self.to_date)


# ----------------------------------------------------------------------
# client API
# ----------------------------------------------------------------------
@frappe.whitelist()
def get_existing_attendance_info(employee: str, from_date: str, to_date: str) -> dict:
	"""Existing attendance + every raw check-in, per date in the period.

	Module level (not a doc method) on purpose: the form needs this the moment the
	employee and the dates are picked, which is BEFORE the request has ever been
	saved — a doc method would have nothing to bind to.

	Runs permission-checked (ignore_permissions=False): this endpoint takes an
	arbitrary employee id, so with frappe.get_all — which skips permissions
	entirely — anyone holding the Employee role could read a colleague's working
	hours. get_list applies both role and User Permission filters, so a plain
	employee sees only their own record while HR still sees everyone.
	"""
	frappe.has_permission("Attendance Request", throw=True)
	frappe.has_permission("Attendance", throw=True)

	if not (employee and from_date and to_date):
		return {"days": []}

	attendance_map = get_attendance_map(employee, from_date, to_date, ignore_permissions=False)
	checkin_map = get_checkin_map(employee, from_date, to_date, ignore_permissions=False)

	days = []
	for offset in range(date_diff(to_date, from_date) + 1):
		day = getdate(add_days(from_date, offset))
		att = attendance_map.get(day)
		days.append(
			{
				"date": str(day),
				"day_of_week": day.strftime("%a"),
				"status": att.status if att else None,
				"in_time": _format_hhmm(att.in_time) if att else None,
				"out_time": _format_hhmm(att.out_time) if att else None,
				"working_hours": flt(att.working_hours, 2) if att else 0,
				"attendance": att.name if att else None,
				"checkins": [
					{"name": c.name, "time": _format_hhmm(c.time), "log_type": c.log_type}
					for c in checkin_map.get(day, [])
				],
			}
		)

	return {"days": days}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def get_attendance_map(employee, from_date, to_date, ignore_permissions: bool = True) -> dict:
	"""{date: attendance} for the period. Cancelled records ignored.

	ignore_permissions=True (the controller path) reads with frappe.get_all: the
	document itself has already been permission-checked. The whitelisted endpoint
	passes False so the query goes through frappe.get_list instead — see
	get_existing_attendance_info().
	"""
	if not (employee and from_date and to_date):
		return {}

	query = frappe.get_all if ignore_permissions else frappe.get_list
	records = query(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ("between", [from_date, to_date]),
			"docstatus": ("!=", 2),
		},
		fields=["name", "attendance_date", "status", "in_time", "out_time", "working_hours"],
		order_by="attendance_date asc, modified desc",
	)
	# order_by keeps the most recently modified record first per date
	result = {}
	for att in records:
		result.setdefault(getdate(att.attendance_date), att)
	return result


def get_checkin_map(employee, from_date, to_date, ignore_permissions: bool = True) -> dict:
	"""{date: [checkin, ...]} of every raw Employee Checkin in the period."""
	if not (employee and from_date and to_date):
		return {}

	query = frappe.get_all if ignore_permissions else frappe.get_list
	records = query(
		"Employee Checkin",
		filters={
			"employee": employee,
			"time": ("between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]),
		},
		fields=["name", "time", "log_type"],
		order_by="time asc",
	)
	result = {}
	for checkin in records:
		result.setdefault(getdate(checkin.time), []).append(checkin)
	return result



def _format_hhmm(value) -> str | None:
	if not value:
		return None
	return get_datetime(value).strftime("%H:%M")


def _has_real_span(attendance) -> bool:
	"""True when the attendance holds a genuine in -> out pair.

	Two stamps closer than DUPLICATE_TOLERANCE_MINUTES are one event (a double
	tap), not a worked day, so they must not count as a complete attendance.
	"""
	if not (attendance and attendance.in_time and attendance.out_time):
		return False
	delta = abs((get_datetime(attendance.out_time) - get_datetime(attendance.in_time)).total_seconds())
	return delta >= DUPLICATE_TOLERANCE_MINUTES * 60


def _find_clashing_checkin(checkins: list, day, new_time) -> str | None:
	"""Name of an existing check-in within DUPLICATE_TOLERANCE_MINUTES of new_time."""
	target = get_datetime(f"{getdate(day)} {new_time}")
	for checkin in checkins:
		delta = abs((get_datetime(checkin.time) - target).total_seconds())
		if delta < DUPLICATE_TOLERANCE_MINUTES * 60:
			return checkin.name
	return None
