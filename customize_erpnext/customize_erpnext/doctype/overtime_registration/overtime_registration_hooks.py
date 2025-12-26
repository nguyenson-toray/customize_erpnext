"""
Overtime Registration Hooks
Auto-update attendance when overtime registration changes using optimized logic

This module provides hooks that are called when Overtime Registration documents change
(on_submit, on_cancel, on_update_after_submit) to recalculate attendance for affected
employees and dates using the same optimized logic as the main attendance processing.
"""

import frappe
from frappe.utils import getdate
from datetime import timedelta


def update_attendance_on_overtime_change(doc, method):
	"""
	Update attendance when overtime registration is submitted, cancelled, or updated

	This hook is called when:
	- on_submit: OT registration is approved
	- on_cancel: OT registration is cancelled
	- on_update_after_submit: OT registration is amended

	Key improvements over the old version:
	1. Uses _core_process_attendance_logic_optimized for consistency
	2. Collects all affected employees and dates first
	3. Processes in a single batch call for efficiency
	4. Ensures the same logic as main attendance processing

	Args:
		doc: Overtime Registration document
		method: Hook method name (on_submit, on_cancel, on_update_after_submit)
	"""
	if not doc.details:
		return

	print(f"\n{'='*80}")
	print(f"🔄 OVERTIME REGISTRATION HOOK TRIGGERED")
	print(f"{'='*80}")
	print(f"   Document: {doc.name}")
	print(f"   Status: {doc.docstatus}")
	print(f"   Method: {method}")
	print(f"   Details: {len(doc.details)} records")

	# ========================================================================
	# STEP 1: Collect affected employees and dates
	# ========================================================================
	affected_employees = set()
	affected_dates = set()

	for detail in doc.details:
		if detail.employee and detail.date:
			affected_employees.add(detail.employee)
			affected_dates.add(getdate(detail.date))

	if not affected_employees or not affected_dates:
		print(f"   ⚠️  No valid employees or dates found in details")
		return

	# Convert to sorted lists for better logging
	employee_list = sorted(list(affected_employees))
	date_list = sorted(list(affected_dates))

	print(f"   📋 Affected employees: {len(employee_list)}")
	print(f"      {', '.join(employee_list[:5])}{' ...' if len(employee_list) > 5 else ''}")
	print(f"   📅 Affected dates: {len(date_list)}")
	print(f"      {', '.join(str(d) for d in date_list[:5])}{' ...' if len(date_list) > 5 else ''}")

	# ========================================================================
	# STEP 2: Calculate date range for processing
	# ========================================================================
	from_date = min(date_list)
	to_date = max(date_list)

	print(f"   📆 Processing range: {from_date} to {to_date}")

	# ========================================================================
	# STEP 3: Call optimized attendance processing
	# ========================================================================
	# Import the optimized core logic from shift_type_optimized
	from customize_erpnext.overrides.shift_type.shift_type_optimized import (
		_core_process_attendance_logic_optimized
	)

	try:
		print(f"\n   🚀 Calling optimized attendance processing...")

		# CRITICAL: Use fore_get_logs=True (full day mode)
		# This ensures attendance is RECALCULATED from ALL checkins, not just new ones
		# This is necessary because:
		# 1. Approved overtime amount changed (need to recalculate custom_approved_overtime_duration)
		# 2. Final overtime depends on min(actual_overtime, approved_overtime)
		# 3. We need to update existing attendance records, not create new ones
		stats = _core_process_attendance_logic_optimized(
			employees=employee_list,
			days=date_list,
			from_date=str(from_date),
			to_date=str(to_date),
			fore_get_logs=True  # Force full day recalculation
		)

		print(f"\n   ✅ Attendance processing completed")
		print(f"      Records processed: {stats.get('actual_records', 0)}")
		print(f"      Employees with attendance: {stats.get('employees_with_attendance', 0)}")
		print(f"      Processing time: {stats.get('processing_time', 0):.2f}s")
		print(f"      Errors: {stats.get('errors', 0)}")

		if stats.get('errors', 0) > 0:
			frappe.msgprint(
				msg=f"Attendance updated with {stats.get('errors')} errors. Check Error Log for details.",
				title="Attendance Update Warning",
				indicator="orange"
			)
		else:
			frappe.msgprint(
				msg=f"Successfully updated attendance for {stats.get('employees_with_attendance', 0)} employees",
				title="Attendance Updated",
				indicator="green"
			)

	except Exception as e:
		error_msg = f"Error updating attendance for OT Registration {doc.name}: {str(e)}"
		print(f"\n   ❌ {error_msg}")
		frappe.log_error(
			title=f"Overtime Registration Hook Error - {doc.name}",
			message=error_msg
		)
		frappe.throw(
			msg=f"Failed to update attendance: {str(e)}",
			title="Attendance Update Error"
		)

	finally:
		print(f"{'='*80}")
		print(f"✅ OVERTIME REGISTRATION HOOK COMPLETED")
		print(f"{'='*80}\n")


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
