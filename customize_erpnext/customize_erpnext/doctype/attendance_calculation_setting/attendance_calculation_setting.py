# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""
Attendance Calculation Setting — single source for the business-rule values
used by attendance / shift / overtime calculation (previously hardcoded).

Consumers read values via get_attendance_settings(); every value has a
code-side fallback in DEFAULTS so behavior is unchanged when the doc has
never been saved (e.g. right after migrate) or a field is left blank.
"""

import frappe
from frappe.model.document import Document

# Fallbacks = the original hardcoded values. Used when the Single doc has no
# value for a field (never saved / cleared). Keep in sync with the doctype
# field defaults.
DEFAULTS = {
	"min_ot_minutes": 30,
	"min_pre_shift_ot_minutes": 60,
	"ot_block_minutes": 1,
	"working_block_minutes": 1,
	"allow_ot_in_rest_time": 0,
	"include_draft_ot": 0,
	"recalc_attendance_on_ot_change": 0,
	"recalc_attendance_on_maternity_change": 0,
	"recalc_attendance_on_checkin_change": 0,
	"exclude_employee_ids": "",
	"maternity_benefit_hours": 1.0,
	"full_day_leave_block_hours": 8.0,
	"default_shift": "Day",
	"employee_id_prefix": "TIQN",
	"force_update_hours": "8,23",
	"peak_times": "07:40,16:00,17:00,19:00,20:00",
	"peak_window_minutes": 20,
	"note_early_late_threshold_minutes": 60,
	"female_checkout_check_from": "16:00:00",
	"female_checkout_check_to": "17:00:00",
}

# Fields where 0/blank IS a meaningful value (Check fields, optional lists) —
# excluded from the "0 → fallback" rule in get_attendance_settings()
ZERO_ALLOWED_FIELDS = {
	"allow_ot_in_rest_time",
	"include_draft_ot",
	"recalc_attendance_on_ot_change",
	"recalc_attendance_on_maternity_change",
	"recalc_attendance_on_checkin_change",
	"exclude_employee_ids",
	"peak_times",  # cleared field = peak-skip disabled (never-set = defaults)
}


def get_ot_docstatus_condition(alias: str = "or_doc") -> str:
	"""
	SQL condition selecting which Overtime Registrations count for attendance
	calculation: Submitted only (default), or Draft + Submitted when the
	include_draft_ot setting is ON. Overlapping entries in the same zone are
	merged downstream via span (min begin - max end) in
	calculate_overtime_segments / the Sunday override.
	"""
	if frappe.utils.cint(get_attendance_settings().include_draft_ot):
		return f"{alias}.docstatus IN (0, 1)"
	return f"{alias}.docstatus = 1"


class AttendanceCalculationSetting(Document):
	def validate(self):
		# Fail early on unparseable values instead of silently falling back at runtime
		parse_force_update_hours(self.force_update_hours)
		parse_peak_times(self.peak_times)


def get_attendance_settings() -> "frappe._dict":
	"""
	Return all settings as frappe._dict, with None/blank values replaced by
	DEFAULTS. Backed by frappe.get_cached_doc (local per-request cache,
	auto-invalidated on save) — cheap to call inside per-record loops.
	"""
	try:
		doc = frappe.get_cached_doc("Attendance Calculation Setting")
	except Exception:
		# DocType not migrated yet — run entirely on defaults
		return frappe._dict(DEFAULTS)

	settings = frappe._dict()
	for key, fallback in DEFAULTS.items():
		value = doc.get(key)
		if key in ZERO_ALLOWED_FIELDS:
			settings[key] = fallback if value is None else value
		else:
			# 0 is never a meaningful value for these settings — treat as unset
			settings[key] = value if value not in (None, "", 0) else fallback
	return settings


def parse_force_update_hours(raw) -> list:
	"""Parse "8,23" → [8, 23]. Raises on invalid input (used by validate)."""
	hours = [int(part.strip()) for part in str(raw or DEFAULTS["force_update_hours"]).split(",") if part.strip()]
	if not hours or any(h < 0 or h > 23 for h in hours):
		frappe.throw(frappe._("Full Update Hours must be comma-separated hours between 0 and 23, e.g. 8,23"))
	return hours


def get_force_update_hours() -> list:
	"""Hours of day when the hourly job runs a FULL day reprocess. Never raises."""
	try:
		return parse_force_update_hours(get_attendance_settings().force_update_hours)
	except Exception:
		return [int(h) for h in DEFAULTS["force_update_hours"].split(",")]


def parse_peak_times(raw) -> list:
	"""Parse "07:40,16:00" → [time(7,40), time(16,0)]. Blank → []. Raises on bad format."""
	import datetime as _dt

	if raw is None or not str(raw).strip():
		return []
	times = []
	for part in str(raw).split(","):
		part = part.strip()
		if not part:
			continue
		try:
			hh, mm = part.split(":")
			times.append(_dt.time(int(hh), int(mm)))
		except Exception:
			frappe.throw(frappe._("Peak Times must be comma-separated HH:MM values, e.g. 07:40,16:00"))
	return times


def is_peak_time(check_dt=None) -> bool:
	"""
	True when check_dt (default: now) falls inside one of the configured daily
	peak windows [peak_time, peak_time + peak_window_minutes).

	Automatic attendance calculation (hourly hook + auto-recalc background
	jobs) is skipped during peaks — changes are caught up by the next full run.
	Manual Bulk Update from the UI is intentionally NOT gated by this.
	Never raises (bad config → not peak).
	"""
	import datetime as _dt

	settings = get_attendance_settings()
	try:
		peaks = parse_peak_times(settings.peak_times)
	except Exception:
		return False
	if not peaks:
		return False

	window = int(settings.peak_window_minutes or DEFAULTS["peak_window_minutes"])
	now_dt = check_dt or frappe.utils.now_datetime()
	for peak in peaks:
		start = _dt.datetime.combine(now_dt.date(), peak)
		if start <= now_dt < start + _dt.timedelta(minutes=window):
			return True
	return False


def get_excluded_employee_ids() -> set:
	"""Employee IDs excluded from attendance processing (CSV setting → set)."""
	raw = get_attendance_settings().exclude_employee_ids or ""
	return {part.strip() for part in str(raw).split(",") if part.strip()}


def floor_ot_to_block(hours: float, min_minutes: int = None) -> float:
	"""
	Floor OT hours to ot_block_minutes (reference algorithm _floorToBlock):
	below min_minutes → 0; otherwise floor(total_min / block) * block.
	With block = 1 (default) this floors to whole minutes.

	min_minutes defaults to the min_ot_minutes setting; pass
	min_pre_shift_ot_minutes for the pre-shift segment.
	"""
	settings = get_attendance_settings()
	if min_minutes is None:
		min_minutes = settings.min_ot_minutes
	total_min = int(hours * 60)  # floor
	if total_min < int(min_minutes):
		return 0
	block = max(int(settings.ot_block_minutes or 1), 1)
	return (total_min // block) * block / 60.0


def floor_working_to_block(hours: float) -> float:
	"""
	Floor working hours to working_block_minutes (reference _floorWorkingToBlock).
	Block <= 1 → return hours unchanged (no rounding).
	"""
	block = int(get_attendance_settings().working_block_minutes or 1)
	if block <= 1:
		return hours
	total_min = int(hours * 60)
	return (total_min // block) * block / 60.0
