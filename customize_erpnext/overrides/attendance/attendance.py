
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

	# Get maternity record (cấu trúc mới: 1 record/employee, 3 cặp ngày riêng)
	em = frappe.db.sql("""
		SELECT
			pregnant_from_date, pregnant_to_date, estimated_due_date,
			maternity_from_date, maternity_to_date,
			youg_child_from_date, youg_child_to_date,
			apply_benefit
		FROM `tabEmployee Maternity`
		WHERE employee = %(employee)s
		LIMIT 1
	""", {"employee": employee}, as_dict=1)

	maternity_records = []  # dùng để kiểm tra có maternity không (cho note cuối)

	if em:
		rec = em[0]
		check_date = frappe.utils.getdate(attendance_date)

		def _fmt(d):
			return frappe.utils.formatdate(d, "dd/mm/yyyy") if d else "?"

		# Pregnant period
		if rec.pregnant_from_date:
			eff_to = rec.pregnant_to_date or rec.estimated_due_date
			if eff_to and rec.pregnant_from_date <= check_date <= frappe.utils.getdate(eff_to):
				maternity_records.append(rec)
				benefit_label = "Benefit Applied" if rec.apply_benefit == 1 else "No Benefit"
				details.append(
					f"🤰 Pregnant: {_fmt(rec.pregnant_from_date)} - {_fmt(eff_to)} ({benefit_label})"
				)

		# Maternity Leave period
		if rec.maternity_from_date and rec.maternity_to_date:
			if frappe.utils.getdate(rec.maternity_from_date) <= check_date <= frappe.utils.getdate(rec.maternity_to_date):
				maternity_records.append(rec)
				details.append(
					f"🏠 Maternity Leave: {_fmt(rec.maternity_from_date)} - {_fmt(rec.maternity_to_date)}"
				)

		# Young Child period
		if rec.youg_child_from_date and rec.youg_child_to_date:
			if frappe.utils.getdate(rec.youg_child_from_date) <= check_date <= frappe.utils.getdate(rec.youg_child_to_date):
				maternity_records.append(rec)
				details.append(
					f"👶 Young Child: {_fmt(rec.youg_child_from_date)} - {_fmt(rec.youg_child_to_date)}"
				)

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

