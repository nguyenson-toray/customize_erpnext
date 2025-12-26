
import frappe
from frappe import _
from erpnext.controllers.status_updater import validate_status
from hrms.hr.utils import validate_active_employee


def custom_attendance_validate(self):
	"""Custom validation that includes 'Maternity Leave' as a valid status"""
	# Include "Maternity Leave" in the allowed statuses
	validate_status(self.status, ["Present", "Absent", "On Leave", "Half Day", "Work From Home", "Maternity Leave"])
	validate_active_employee(self.employee)
	self.validate_attendance_date()
	self.validate_duplicate_record()
	self.validate_overlapping_shift_attendance()
	self.validate_employee_status()
	self.check_leave_record()

@frappe.whitelist()
def get_attendance_custom_additional_info(employee, attendance_date):
	"""Get detailed maternity benefit information for display

	Args:
		employee: Employee ID
		attendance_date: Date to check

	Returns:
		str: Formatted maternity benefit details or empty string
	"""
	maternity_records = frappe.db.sql("""
		SELECT type, from_date, to_date, apply_pregnant_benefit
		FROM `tabMaternity Tracking`
		WHERE parent = %(employee)s
		  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
		  AND from_date <= %(date)s
		  AND to_date >= %(date)s
	""", {"employee": employee, "date": attendance_date}, as_dict=1)

	if not maternity_records:
		return ""

	details = []
	for record in maternity_records:
		record_type = record.type
		from_date = frappe.utils.formatdate(record.from_date, "dd/mm/yyyy")
		to_date = frappe.utils.formatdate(record.to_date, "dd/mm/yyyy")

		if record.type == 'Pregnant':
			if record.apply_pregnant_benefit == 1:
				details.append(f"🤰 {record_type}: {from_date} - {to_date} (Benefit Applied)")
			else:
				details.append(f"🤰 {record_type}: {from_date} - {to_date} (No Benefit)")
		elif record.type == 'Maternity Leave':
			details.append(f"🏠 {record_type}: {from_date} - {to_date}")
		elif record.type == 'Young Child':
			details.append(f"👶 {record_type}: {from_date} - {to_date}")

	if not details:
		return ""

	return "\n".join([
		"<b>Additional Information:</b>",
		"<ul style='margin-top: 5px; margin-bottom: 0;'>",
		*[f"<li>{detail}</li>" for detail in details],
		"</ul>",
		"<small style='color: #888;'>* Allow shift end time reduced by 1 houry</small>"
	])

