
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
	"""Get detailed maternity benefit and overtime registration information for display

	Args:
		employee: Employee ID
		attendance_date: Date to check

	Returns:
		str: Formatted additional details or empty string
	"""
	details = []

	# Check if employee has left before this attendance date
	emp_data = frappe.db.get_value("Employee", employee,
		["status", "relieving_date"], as_dict=True)
	if emp_data and emp_data.status == "Left" and emp_data.relieving_date:
		if frappe.utils.getdate(attendance_date) > emp_data.relieving_date:
			relieving_str = frappe.utils.formatdate(emp_data.relieving_date, "dd/mm/yyyy")
			details.append(
				f"⚠️ Employee has left on {relieving_str} - attendance after relieving date"
			)

	# Get maternity records
	maternity_records = frappe.db.sql("""
		SELECT type, from_date, to_date, apply_benefit
		FROM `tabEmployee Maternity`
		WHERE employee = %(employee)s
		  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
		  AND from_date <= %(date)s
		  AND to_date >= %(date)s
	""", {"employee": employee, "date": attendance_date}, as_dict=1)

	for record in maternity_records:
		record_type = record.type
		from_date = frappe.utils.formatdate(record.from_date, "dd/mm/yyyy")
		to_date = frappe.utils.formatdate(record.to_date, "dd/mm/yyyy")

		if record.type == 'Pregnant':
			if record.apply_benefit == 1:
				details.append(f"🤰 {record_type}: {from_date} - {to_date} (Benefit Applied)")
			else:
				details.append(f"🤰 {record_type}: {from_date} - {to_date} (No Benefit)")
		elif record.type == 'Maternity Leave':
			details.append(f"🏠 {record_type}: {from_date} - {to_date}")
		elif record.type == 'Young Child':
			details.append(f"👶 {record_type}: {from_date} - {to_date}")

	# Get overtime registration records
	ot_records = frappe.db.sql("""
		SELECT
			otd.parent as ot_registration,
			otd.begin_time,
			otd.end_time,
			ot.docstatus
		FROM `tabOvertime Registration Detail` otd
		INNER JOIN `tabOvertime Registration` ot ON ot.name = otd.parent
		WHERE otd.employee = %(employee)s
		  AND otd.date = %(date)s
		  AND ot.docstatus IN (0, 1)
		ORDER BY otd.begin_time
	""", {"employee": employee, "date": attendance_date}, as_dict=1)

	for ot in ot_records:
		begin_time = str(ot.begin_time)[:5] if ot.begin_time else ""
		end_time = str(ot.end_time)[:5] if ot.end_time else ""
		status = "Submitted" if ot.docstatus == 1 else "Draft"
		link = f'<a href="/app/overtime-registration/{ot.ot_registration}">{ot.ot_registration}</a>'
		details.append(f"⏰ Overtime: {begin_time} - {end_time} ({status}) - {link}")

	if not details:
		return ""

	result = [
		"<b>Additional Information:</b>",
		"<ul style='margin-top: 5px; margin-bottom: 0;'>",
		*[f"<li>{detail}</li>" for detail in details],
		"</ul>"
	]

	# Add maternity note if there are maternity records
	if maternity_records:
		result.append("<small style='color: #888;'>* Allow shift end time reduced by 1 hour</small>")

	return "\n".join(result)

