"""
Leave Application Overrides for TIQN

Override so với HRMS gốc:
1. validate_attendance(): Chỉ block Full Day leave khi working_hours >= 8
2. create_or_update_attendance(): Status logic + dual leave support
3. on_leave_application_cancel(): Xử lý cancel đúng khi có dual leave

HRMS gốc:
- validate_attendance(): Block TẤT CẢ attendance "Present"/"Work From Home"
- create_or_update_attendance(): status = "Half Day" or "On Leave" only

=== validate_attendance() ===
- Half Day leave: LUÔN cho phép
- Full Day leave + working_hours >= 8: BLOCK
- Full Day leave + working_hours < 8: Cho phép

=== create_or_update_attendance() - Status Logic ===
| Leave Type | Has Check-in | Status     |
|------------|--------------|------------|
| Half Day   | Any          | Half Day   |
| Full Day   | Yes (wh > 0) | Present    |
| Full Day   | No (wh = 0)  | On Leave   |

=== Dual Leave ===
- 2 Half Day LAs cùng ngày với 2 loại nghỉ phép khác nhau
- LA2 lưu vào custom_leave_type_2, custom_leave_application_2
"""

import frappe
from frappe import _
from frappe.utils import getdate, formatdate, get_link_to_form


# =============================================================================
# CONFIGURATION
# =============================================================================

# Số giờ làm việc tối thiểu để block Full Day leave
# Chỉ block khi: Full Day leave AND working_hours >= này
FULL_DAY_WORKING_HOURS_THRESHOLD = 8


# =============================================================================
# OVERRIDE: validate_attendance
# =============================================================================

def custom_validate_attendance(self):
	"""
	Override validate_attendance để cho phép leave trong hầu hết trường hợp.

	HRMS gốc (leave_application.py:602-629):
	- Block TẤT CẢ attendance có status "Present" hoặc "Work From Home"

	Override:
	- CHỈ block khi: Full Day leave AND working_hours >= 8
	- Các trường hợp khác đều cho phép:
	  - Half Day leave: luôn cho phép
	  - Full Day leave với working_hours < 8: cho phép
	"""
	from hrms.hr.doctype.leave_application.leave_application import AttendanceAlreadyMarkedError

	# Query attendance
	attendance_records = frappe.get_all(
		"Attendance",
		filters=[
			["employee", "=", self.employee],
			["attendance_date", "between", [self.from_date, self.to_date]],
			["status", "in", ["Present", "Work From Home"]],
			["docstatus", "=", 1],
			["half_day_status", "!=", "Absent"],
		],
		fields=["name", "attendance_date", "working_hours"],
		order_by="attendance_date",
	)

	if not attendance_records:
		return  # Không có attendance, tiếp tục

	blocking_attendance = []
	allowed_attendance = []

	for att in attendance_records:
		attendance_date = att.attendance_date
		working_hours = att.working_hours or 0

		# Half Day leave: LUÔN cho phép
		if self.half_day:
			allowed_attendance.append({
				"date": attendance_date,
				"action": _("will be updated to Half Day")
			})
			continue

		# Full Day leave: chỉ block nếu working_hours >= threshold
		if working_hours >= FULL_DAY_WORKING_HOURS_THRESHOLD:
			blocking_attendance.append(att)
		else:
			allowed_attendance.append({
				"date": attendance_date,
				"action": _("will be updated to On Leave (working_hours={0})").format(working_hours)
			})

	# Hiển thị warning cho attendance sẽ được update
	if allowed_attendance:
		dates_info = [f"{formatdate(a['date'])} → {a['action']}" for a in allowed_attendance]
		frappe.msgprint(
			_("Attendance will be updated:") + "<br><ul><li>" +
			"</li><li>".join(dates_info) + "</li></ul>",
			indicator="orange",
			alert=True
		)

	# Throw error nếu còn blocking attendance
	if blocking_attendance:
		frappe.throw(
			_("Cannot apply Full Day leave. Employee {0} has full working hours ({1}h) on: {2}").format(
				self.employee,
				FULL_DAY_WORKING_HOURS_THRESHOLD,
				"<br><ul><li>" + "</li><li>".join(
					get_link_to_form("Attendance", a.name, label=f"{formatdate(a.attendance_date)} ({a.working_hours}h)")
					for a in blocking_attendance
				) + "</li></ul>",
			),
			AttendanceAlreadyMarkedError,
		)


# =============================================================================
# OVERRIDE: create_or_update_attendance
# =============================================================================

def custom_create_or_update_attendance(self, attendance_name, date):
	"""
	Override create_or_update_attendance để hỗ trợ 2 Half Day LAs cùng ngày.

	HRMS gốc (leave_application.py:316-349):
	- status = "Half Day" nếu half_day_date match, ngược lại "On Leave"

	Override - Status logic:
	- Half Day leave → status = "Half Day"
	- Full Day + working_hours = 0 + no check in → status = "On Leave"
	- Full Day + có check in (working_hours > 0) → status = "Present"

	Dual leave:
	- Hỗ trợ 2 Half Day LAs riêng biệt cùng ngày
	- LA2 được lưu vào custom_leave_type_2, custom_leave_application_2
	"""
	from customize_erpnext.overrides.leave_utils import (
		get_leave_type_abbreviation,
		get_combined_abbreviation,
		update_attendance_with_dual_leave,
	)

	# Xác định Half Day
	is_half_day_for_this_date = (
		self.half_day and
		self.half_day_date and
		getdate(date) == getdate(self.half_day_date)
	)

	if attendance_name:
		# Update existing attendance
		doc = frappe.get_doc("Attendance", attendance_name)
		has_checkin = doc.working_hours and doc.working_hours > 0

		# CHECK DUAL LEAVE: Attendance đã có LA khác?
		if doc.leave_application and doc.leave_application != self.name:
			# Cho phép dual leave nếu:
			# - LA hiện tại là Half Day
			# - HOẶC attendance hiện tại đã là Half Day
			allow_dual_leave = self.half_day or doc.status == "Half Day"

			if allow_dual_leave:
				# Đây là LA2 cho ngày này
				combined_abbr = update_attendance_with_dual_leave(
					attendance_name,
					doc.leave_type,       # LA1 leave_type
					doc.leave_application, # LA1 name
					self.leave_type,       # LA2 leave_type
					self.name              # LA2 name
				)
				frappe.msgprint(
					_("Attendance {0} updated with 2nd leave: {1}").format(
						get_link_to_form("Attendance", attendance_name),
						combined_abbr
					),
					indicator="green",
					alert=True
				)
				return
			else:
				frappe.throw(
					_("Attendance {0} already has leave application {1}").format(
						attendance_name, doc.leave_application
					)
				)

		# Xác định status dựa trên điều kiện
		# - Half Day → "Half Day"
		# - Full Day + có check in → "Present"
		# - Full Day + không check in → "On Leave"
		if is_half_day_for_this_date:
			status = "Half Day"
			half_day_status = "Present"
			modify_half_day_status = 0 if has_checkin else 1
		elif has_checkin:
			status = "Present"
			half_day_status = None
			modify_half_day_status = 0
		else:
			status = "On Leave"
			half_day_status = None
			modify_half_day_status = 0

		# Abbreviation
		abbr = get_leave_type_abbreviation(self.leave_type)
		combined_abbr = f"{abbr}/2" if is_half_day_for_this_date else abbr

		# Update
		doc.db_set({
			"status": status,
			"leave_type": self.leave_type,
			"leave_application": self.name,
			"custom_leave_application_abbreviation": combined_abbr,
			"half_day_status": half_day_status,
			"modify_half_day_status": modify_half_day_status,
		})

	else:
		# Make new attendance - không có check in
		# Half Day → "Half Day", Full Day → "On Leave"
		status = "Half Day" if is_half_day_for_this_date else "On Leave"

		abbr = get_leave_type_abbreviation(self.leave_type)
		combined_abbr = f"{abbr}/2" if is_half_day_for_this_date else abbr

		doc = frappe.new_doc("Attendance")
		doc.employee = self.employee
		doc.employee_name = self.employee_name
		doc.attendance_date = date
		doc.company = self.company
		doc.leave_type = self.leave_type
		doc.leave_application = self.name
		doc.status = status
		doc.custom_leave_application_abbreviation = combined_abbr
		doc.half_day_status = "Present" if status == "Half Day" else None
		doc.modify_half_day_status = 1 if status == "Half Day" else 0
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		doc.submit()


# =============================================================================
# HOOK: on_cancel
# =============================================================================

def on_leave_application_cancel(doc, method):
	"""
	Hook on_cancel để xử lý dual leave khi LA bị cancel.

	Scenarios:
	- LA là LA1 và có LA2 → Swap LA2 thành LA1
	- LA là LA2 → Remove LA2, giữ LA1
	- LA là LA duy nhất → Let HRMS handle (cancel attendance)
	"""
	from customize_erpnext.overrides.leave_utils import (
		get_combined_abbreviation,
		find_attendance_for_leave,
	)

	# Chỉ xử lý Half Day leaves
	if not doc.half_day or not doc.half_day_date:
		return

	existing_att = find_attendance_for_leave(doc.employee, doc.half_day_date)
	if not existing_att:
		return

	att_name = existing_att.name
	is_la1 = existing_att.leave_application == doc.name
	is_la2 = existing_att.custom_leave_application_2 == doc.name

	if is_la1 and existing_att.custom_leave_application_2:
		# LA1 bị cancel, LA2 tồn tại → Swap LA2 → LA1
		new_lt1 = existing_att.custom_leave_type_2
		new_la1 = existing_att.custom_leave_application_2
		new_abbr = get_combined_abbreviation(new_lt1, None)

		frappe.db.set_value("Attendance", att_name, {
			"leave_type": new_lt1,
			"leave_application": new_la1,
			"custom_leave_type_2": None,
			"custom_leave_application_2": None,
			"custom_leave_application_abbreviation": new_abbr,
			"status": "Half Day",
			"half_day_status": "Present",
		})
		frappe.msgprint(
			_("Attendance {0}: swapped LA2 → LA1 ({1})").format(att_name, new_abbr),
			indicator="blue", alert=True
		)

	elif is_la2:
		# LA2 bị cancel → Remove LA2, giữ LA1
		new_abbr = get_combined_abbreviation(existing_att.leave_type, None)

		frappe.db.set_value("Attendance", att_name, {
			"custom_leave_type_2": None,
			"custom_leave_application_2": None,
			"custom_leave_application_abbreviation": new_abbr,
			"status": "Half Day",
			"half_day_status": "Present",
		})
		frappe.msgprint(
			_("Attendance {0}: removed LA2 ({1})").format(att_name, new_abbr),
			indicator="blue", alert=True
		)

	# Nếu is_la1 và không có LA2 → HRMS sẽ cancel attendance


print("✅ Leave Application overrides loaded")
