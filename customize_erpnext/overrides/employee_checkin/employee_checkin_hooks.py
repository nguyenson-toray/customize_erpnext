"""
Employee Checkin Hooks
Auto-update attendance when employee checkin is created, updated, or deleted
"""

import frappe
from frappe.utils import getdate, now_datetime
from customize_erpnext.overrides.shift_type.shift_type_optimized import _core_process_attendance_logic_optimized


def _is_peak_hours():
	"""
	Check if current time is during peak hours when mass checkins occur.

	Peak hours:
	- 07:30 to 07:55
	- 16:00 to 16:15
	- 17:00 to 17:15
	- 19:00 to 19:15

	Returns:
		bool: True if during peak hours, False otherwise
	"""
	current_time = now_datetime().time()
	hour = current_time.hour
	minute = current_time.minute

	# Morning shift start: 07:30 - 07:55
	if hour == 7 and 30 <= minute <= 55:
		return True

	# Afternoon break end: 16:00 - 16:15
	if hour == 16 and minute <= 15:
		return True

	# Evening shift end: 17:00 - 17:15
	if hour == 17 and minute <= 15:
		return True

	# Night shift end: 19:00 - 19:15
	if hour == 19 and minute <= 15:
		return True

	return False


def update_attendance_on_checkin_insert(doc, method):
	"""
	Recalculate attendance when a new employee checkin is created.
	Skips recalculation during peak hours to avoid system overload.

	Args:
		doc: Employee Checkin document being inserted
		method: Hook method name (after_insert)
	"""
	if not doc.employee or not doc.time:
		return

	# Skip attendance recalculation during peak hours
	if _is_peak_hours():
		return

	employee = doc.employee
	checkin_date = getdate(doc.time)

	_recalculate_attendance(employee, checkin_date)


def update_attendance_on_checkin_update(doc, method):
	"""
	Recalculate attendance when employee checkin is updated.
	Skips recalculation during peak hours to avoid system overload.

	Args:
		doc: Employee Checkin document being updated
		method: Hook method name (on_update)
	"""
	if not doc.employee or not doc.time:
		return

	# Skip attendance recalculation during peak hours
	if _is_peak_hours():
		return

	employee = doc.employee
	checkin_date = getdate(doc.time)

	_recalculate_attendance(employee, checkin_date)


def set_log_type_for_first_and_last_checkin(doc, method):
    # Get all checkins for this employee on this date, ordered by time
    checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": doc.employee,
            "time": ["between", [f"{getdate(doc.time)} 00:00:00", f"{getdate(doc.time)} 23:59:59"]], 
        },
        fields=["name", "log_type", "time"],
        order_by="time ASC"
    )

    if not checkins:
        return

    updated = False

    # Update first check-in of the day to IN
    first_checkin = checkins[0]
    if first_checkin.log_type != "IN":
        frappe.db.set_value("Employee Checkin", first_checkin.name, "log_type", "IN")
        if first_checkin.name == doc.name:
            doc.log_type = "IN"
        updated = True

    # Update last check-in of the day to OUT (if more than one)
    if len(checkins) > 1:
        last_checkin = checkins[-1]
        if last_checkin.log_type != "OUT":
            frappe.db.set_value("Employee Checkin", last_checkin.name, "log_type", "OUT")
            if last_checkin.name == doc.name:
                doc.log_type = "OUT"
            updated = True

    frappe.db.commit()

    # Show message and trigger reload if updates were made
    if updated:
        # frappe.msgprint("Log type has been automatically set based on check-in order", indicator="green")
        # Trigger client-side reload
		
        frappe.publish_realtime("employee_checkin_updated", {
            "employee": doc.employee,
            "date": getdate(doc.time),
            "current_doc": doc.name
        }, user=frappe.session.user) 
def update_attendance_on_checkin_delete(doc, method):
	"""
	Update or delete attendance when employee checkin is deleted.

	Logic:
	- If there are remaining checkins: Recalculate attendance from remaining checkins
	- If no remaining checkins: Delete the attendance record

	Args:
		doc: Employee Checkin document being deleted
		method: Hook method name (on_trash)
	"""
	if not doc.employee or not doc.time:
		return

	employee = doc.employee
	checkin_date = getdate(doc.time)
	_recalculate_attendance(employee, checkin_date)  

def _recalculate_attendance(employee, checkin_date):
	"""
	Recalculate attendance for employee on specific date using remaining checkins.

	Args:
		employee: Employee ID
		checkin_date: Date to recalculate
	"""
	_core_process_attendance_logic_optimized(
		[employee],
		[checkin_date],
		checkin_date,
		checkin_date,
		fore_get_logs=True
	)

