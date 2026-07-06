"""
Overtime Registration Hooks
Auto-update attendance when overtime registration changes using optimized logic

This module provides hooks that are called when Overtime Registration documents change
(on_submit, on_cancel, on_update_after_submit) to recalculate attendance for affected
employees and dates using the same optimized logic as the main attendance processing.
"""

import frappe
from frappe.utils import getdate
from datetime import date, timedelta


def update_attendance_on_overtime_change(doc, method):
	"""
	Update attendance when overtime registration is submitted or cancelled.

	This hook enqueues a background job to recalculate attendance for affected employees.
	The submit/cancel action completes immediately without blocking the user.

	Args:
		doc: Overtime Registration document
		method: Hook method name (on_submit, on_cancel)
	"""
	# Gated by setting (default OFF): when off, attendance picks up OT changes
	# at the next full run (Full Update Hours) or a manual Bulk Update
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_attendance_settings,
	)
	if not frappe.utils.cint(get_attendance_settings().recalc_attendance_on_ot_change):
		return

	_collect_and_enqueue_attendance_update(doc)


def update_attendance_on_overtime_draft_change(doc, method):
	"""
	DRAFT OTR save/delete: drafts only affect attendance when the
	include_draft_ot setting is ON — in that case editing or deleting a draft
	must recalc too (same recalc_attendance_on_ot_change gate as submit/cancel).

	quiet=True on saves: no popup spam while HR is still composing the form
	(job_id + deduplicate collapse repeated saves of the same doc).

	Args:
		doc: Overtime Registration document (docstatus 0)
		method: Hook method name (on_update, on_trash)
	"""
	if doc.docstatus != 0:
		# submit/cancel path is handled by update_attendance_on_overtime_change
		return

	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		get_attendance_settings,
	)
	settings = get_attendance_settings()
	if not frappe.utils.cint(settings.recalc_attendance_on_ot_change):
		return
	if not frappe.utils.cint(settings.include_draft_ot):
		# drafts don't count toward attendance → nothing to recalc
		return

	_collect_and_enqueue_attendance_update(doc, quiet=(method == "on_update"))


def _collect_and_enqueue_attendance_update(doc, quiet=False):
	"""Collect affected (employee, date) pairs from OTR detail and enqueue the
	attendance recalculation background job (deduplicated per OTR name)."""
	if not doc.ot_employees:
		return

	# ========================================================================
	# Collect affected employees and dates from OTR detail
	# ========================================================================
	affected_employees = set()
	affected_dates = set()
	today = date.today()

	for detail in doc.ot_employees:
		if detail.employee and detail.date:
			detail_date = getdate(detail.date)
			if detail_date > today:
				continue
			affected_employees.add(detail.employee)
			affected_dates.add(detail_date)

	if not affected_employees or not affected_dates:
		return

	employee_list = sorted(list(affected_employees))
	date_list = sorted(list(affected_dates))
	from_date = min(date_list)
	to_date = max(date_list)

	# ========================================================================
	# Enqueue background job for attendance processing
	# ========================================================================
	frappe.enqueue(
		"customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks._process_attendance_background",
		queue="long",
		timeout=600,
		job_id=f"ot_attendance_{doc.name}",
		deduplicate=True,  # repeated draft saves collapse into one queued job
		doc_name=doc.name,
		employee_list=employee_list,
		date_list=[str(d) for d in date_list],  # serialize dates
		from_date=str(from_date),
		to_date=str(to_date),
		user=frappe.session.user,
		enqueue_after_commit=True
	)

	if not quiet:
		frappe.msgprint(
			msg=f"Attendance update for {len(employee_list)} employees has been queued and will be processed shortly.",
			title="Attendance Update Queued",
			indicator="blue"
		)


def _process_attendance_background(doc_name, employee_list, date_list, from_date, to_date, user):
	"""
	Background job: recalculate attendance for employees affected by an OTR.

	Args:
		doc_name: Overtime Registration name (for logging)
		employee_list: List of employee IDs
		date_list: List of date strings
		from_date: Start date string
		to_date: End date string
		user: User who triggered the action (for realtime notification)
	"""
	from customize_erpnext.overrides.shift_type.shift_type_optimized import (
		_core_process_attendance_logic_optimized
	)
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import is_peak_time

	logger = frappe.logger("overtime_registration", allow_site=True)

	# Skip during check-in/out peak windows — next full run catches up
	if is_peak_time():
		logger.info(f"OT Attendance Background Job [{doc_name}]: peak time — skipped")
		return

	# Convert date strings back to date objects
	days = [getdate(d) for d in date_list]

	try:
		logger.info(f"OT Attendance Background Job [{doc_name}]: {len(employee_list)} employees, {len(days)} dates")

		stats = _core_process_attendance_logic_optimized(
			employees=employee_list,
			days=days,
			from_date=from_date,
			to_date=to_date,
			fore_get_logs=True
		)

		logger.info(f"OT Attendance Background Job [{doc_name}]: completed, {stats.get('employees_with_attendance', 0)} employees updated")

		# Send realtime notification to the user
		if stats.get('errors', 0) > 0:
			frappe.publish_realtime(
				"msgprint",
				{
					"message": f"[{doc_name}] Attendance updated with {stats.get('errors')} errors. Check Error Log.",
					"title": "Attendance Update Warning",
					"indicator": "orange"
				},
				user=user
			)
		else:
			frappe.publish_realtime(
				"msgprint",
				{
					"message": f"[{doc_name}] Successfully updated attendance for {stats.get('employees_with_attendance', 0)} employees",
					"title": "Attendance Updated",
					"indicator": "green"
				},
				user=user
			)

	except Exception as e:
		error_msg = f"Error updating attendance for OT Registration {doc_name}: {str(e)}"
		logger.error(error_msg)
		frappe.log_error(
			title=f"OT Attendance Background Error - {doc_name}",
			message=error_msg
		)
		frappe.publish_realtime(
			"msgprint",
			{
				"message": f"[{doc_name}] Failed to update attendance: {str(e)}",
				"title": "Attendance Update Error",
				"indicator": "red"
			},
			user=user
		)


# ============================================================================
# OPTIONAL: Helper function to manually trigger attendance recalculation
# ============================================================================

@frappe.whitelist()
def recalculate_attendance_for_overtime_registration(overtime_registration_name):
	"""
	Manually recalculate attendance for an Overtime Registration

	This can be called from the UI if needed to manually trigger recalculation.

	Args:
		overtime_registration_name: Name of the Overtime Registration document

	Returns:
		dict: Processing statistics
	"""
	doc = frappe.get_doc("Overtime Registration", overtime_registration_name)

	if doc.docstatus != 1:
		frappe.throw("Only submitted Overtime Registration can trigger attendance recalculation")

	# Call the hook function
	update_attendance_on_overtime_change(doc, "manual_recalculation")

	return {"success": True, "message": "Attendance recalculated successfully"}
