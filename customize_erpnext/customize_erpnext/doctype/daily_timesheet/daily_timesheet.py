# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, get_datetime, time_diff_in_hours, flt, today, add_days
from datetime import datetime, time, timedelta
import json
from decimal import Decimal, ROUND_HALF_UP

# Constant for decimal rounding precision
DECIMAL_ROUND_NUMBER = 2

# Constants for minimum thresholds
MIN_MINUTES_OT = 30
MIN_MINUTES_WORKING_HOURS = 10
MIN_MINUTES_PRE_SHIFT_OT = 60
MIN_MINUTES_CHECKIN_FILTER = 10 # Min munutes between checkins

# Constants for Sunday overtime
MIN_SUNDAY_OT_FOR_LUNCH_BENEFIT = 4  # Minimum 4 hours OT to get lunch benefit

# Constants for payroll reporting 
OVERTIME_ALERT_RERIPIENTS = ["it@tiqn.com.vn", "loan.ptk@tiqn.com.vn","hoanh.ltk@tiqn.com.vn"]
TOP_OT_NUMBER = 50  # Top N employees for OT reports
MAX_MONTHLY_OT_HOURS = 40  # Maximum OT hours per month according to Vietnam law

class DailyTimesheet(Document):
	def before_save(self):
		"""Calculate all fields before saving"""
		self.calculate_all_fields()
	def decimal_round(self, value, places=DECIMAL_ROUND_NUMBER):
		"""Làm tròn số sử dụng decimal để đồng nhất với JavaScript"""
		if value is None:
			return 0.0
		try:
			decimal_value = Decimal(str(value))
			# Tạo pattern cho số chữ số thập phân
			if places == 1:
				pattern = Decimal('0.1')
			elif places == 2:
				pattern = Decimal('0.01')
			else:
				pattern = Decimal('0.' + '0' * (places - 1) + '1')
			
			return float(decimal_value.quantize(pattern, rounding=ROUND_HALF_UP))
		except (ValueError, TypeError):
			return 0.0
	def calculate_all_fields(self):
		"""Main calculation function - tính toán tất cả các fields"""
		if not self.employee or not self.attendance_date:
			return

		# Validate attendance_date is not before employee's joining date
		date_of_joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")
		if date_of_joining and getdate(self.attendance_date) < getdate(date_of_joining):
			frappe.throw(f"Cannot create Daily Timesheet: Attendance date ({self.attendance_date}) is before employee's joining date ({date_of_joining})")

		# Always generate additional info HTML first
		self.generate_additional_info_html()
		
		# 1. Get check-in/out data từ Employee Checkin
		check_in, check_out = self.get_employee_checkin_data()
		
		# 2. Xác định shift type
		shift_type, determined_by = self.get_shift_type()
		self.shift = shift_type
		self.shift_determined_by = determined_by
		
		# 3. Check maternity benefit
		self.maternity_benefit = self.check_maternity_benefit()
		
		# 4. Set status based on check-in availability (even if only check-in exists)
		if check_in:
			self.check_in = check_in
			self.in_time = check_in.time()
			self.status = "Present"  # Set Present if any check-in exists
		else:
			self.status = "Absent"
			self.clear_all_fields()
			return
		
		# 5. Only proceed with full calculation if both check-in and check-out exist
		if not check_in or not check_out:
			# Clear calculation-related fields but keep status as Present
			self.check_out = None
			self.out_time = None
			self.working_hours = 0
			self.overtime_hours = 0
			self.actual_overtime = 0
			self.approved_overtime = 0
			self.late_entry = False
			self.early_exit = False
			self.overtime_details_html = ""
			return
		
		# From here, both check_in and check_out exist
		self.check_out = check_out
		self.out_time = check_out.time()
		
		# 6. Get shift configuration
		shift_config = self.get_shift_config(shift_type)
		if not shift_config:
			return
		
		# 7. Calculate working hours (morning + afternoon)
		morning_hours = self.calculate_morning_hours(check_in, check_out, shift_config)
		afternoon_hours = self.calculate_afternoon_hours(check_in, check_out, shift_config, self.maternity_benefit)
		
		# Calculate total working hours (no longer storing morning/afternoon separately)
		total_working_hours = morning_hours + afternoon_hours
		
		# Apply MIN_MINUTES_WORKING_HOURS threshold: bỏ qua working_hours nếu < 15 phút
		if total_working_hours * 60 < MIN_MINUTES_WORKING_HOURS:
			total_working_hours = 0
		
		self.working_hours = self.decimal_round(total_working_hours)
		
		# 8. Calculate overtime
		actual_ot = self.calculate_actual_overtime(check_in, check_out, shift_config, self.maternity_benefit)
		approved_ot = self.get_approved_overtime(shift_type)
		final_ot = min(actual_ot, approved_ot) if shift_config.get("allows_ot") else 0
		
		self.actual_overtime = self.decimal_round(actual_ot)
		self.approved_overtime = self.decimal_round(approved_ot)
		self.overtime_hours = self.decimal_round(final_ot)
		
		# 8.5. Calculate overtime coefficient
		self.overtime_coefficient = self.calculate_overtime_coefficient()

		# 8.6. Special Sunday logic
		from datetime import datetime
		if isinstance(self.attendance_date, str):
			date_obj = datetime.strptime(str(self.attendance_date), '%Y-%m-%d')
		else:
			date_obj = self.attendance_date

		if date_obj.weekday() == 6:  # Sunday
			# Get OT registrations for Sunday calculation
			ot_registrations = frappe.db.sql("""
				SELECT ord.begin_time, ord.end_time
				FROM `tabOvertime Registration Detail` ord
				JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
				WHERE ord.employee = %(employee)s
				  AND ord.date = %(date)s
				  AND or_doc.docstatus = 1
			""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)

			# Apply Sunday logic (works with or without OT registration)
			# If no OT registration, use Day shift as default
			apply_sunday_logic(self, check_in, check_out, ot_registrations, shift_config)
		else:
			# 8.7. Calculate final OT with coefficient (normal days)
			self.final_ot_with_coefficient = self.decimal_round(self.overtime_hours * self.overtime_coefficient)

		# 9. Calculate late entry / early exit (skip for Sunday)
		if date_obj.weekday() != 6:
			late_entry_val, early_exit_val = self.calculate_late_early(check_in, check_out, shift_config, self.maternity_benefit)
			self.late_entry = late_entry_val
			self.early_exit = early_exit_val
		else:
			self.late_entry = False
			self.early_exit = False

		# 10. Update status based on date and overtime (skip for Sunday, already set by apply_sunday_logic)
		if date_obj.weekday() != 6:
			if self.overtime_hours > 0:
				self.status = "Present + OT"
			else:
				self.status = "Present"
		
		# 11. Generate overtime details HTML
		self.generate_overtime_details_html()
	
	def get_employee_checkin_data(self):
		"""Lấy check-in/out data từ Employee Checkin đã có sẵn"""
		checkins = frappe.db.sql("""
			SELECT time as check_time, log_type
			FROM `tabEmployee Checkin` 
			WHERE employee = %(employee)s 
			AND DATE(time) = %(date)s
			ORDER BY time ASC
		""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)
		
		check_in = None
		check_out = None
		
		if not checkins:
			return check_in, check_out
		
		# Filter out duplicate/invalid checkins
		# Rule: Sử dụng MIN_MINUTES_CHECKIN_FILTER để filter các lần chấm công quá gần nhau
		filtered_checkins = []
		for i, checkin in enumerate(checkins):
			if i == 0:
				filtered_checkins.append(checkin)
			else:
				time_diff = (checkin.check_time - checkins[i-1].check_time).total_seconds() / 60
				if time_diff >= MIN_MINUTES_CHECKIN_FILTER:  # Use constant
					filtered_checkins.append(checkin)
		
		# Handle explicit log_type if available and valid
		in_checkins = [c for c in filtered_checkins if c.log_type == "IN"]
		out_checkins = [c for c in filtered_checkins if c.log_type == "OUT"]
		
		if in_checkins:
			check_in = in_checkins[0].check_time
		if out_checkins:
			check_out = out_checkins[-1].check_time
		
		# Fallback logic when no explicit log_type
		if not check_in and not check_out and filtered_checkins:
			if len(filtered_checkins) == 1:
				# Single checkin - treat as check-in (most common case)
				# People usually record when they arrive, not when they leave
				single_checkin = filtered_checkins[0]
				check_in = single_checkin.check_time
			
			elif len(filtered_checkins) >= 2:
				# Multiple checkins - ĐẢM BẢO: sớm nhất là check in, muộn nhất là check out
				if not check_in:
					check_in = filtered_checkins[0].check_time  # Sớm nhất
				if not check_out:
					check_out = filtered_checkins[-1].check_time  # Muộn nhất
		
		return check_in, check_out
	
	def get_shift_type(self):
		"""Xác định shift type theo thứ tự ưu tiên"""
		# Ưu tiên 0: Check if it's Sunday (weekday 6 = Sunday)
		from datetime import datetime
		if isinstance(self.attendance_date, str):
			date_obj = datetime.strptime(str(self.attendance_date), '%Y-%m-%d')
		else:
			date_obj = self.attendance_date
		
		if date_obj.weekday() == 6:  # Sunday
			return "Day", "Default Day Shift For Sunday"
		
		# Ưu tiên 1: Shift Registration Detail
		shift_reg = frappe.db.sql("""
			SELECT srd.shift
			FROM `tabShift Registration Detail` srd
			JOIN `tabShift Registration` sr ON srd.parent = sr.name
			WHERE srd.employee = %(employee)s
			  AND srd.begin_date <= %(date)s  
			  AND srd.end_date >= %(date)s
			  AND sr.docstatus = 1
			ORDER BY sr.creation DESC
			LIMIT 1
		""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)
		
		if shift_reg:
			return shift_reg[0].shift, "Registration"
		
		# Ưu tiên 2: Employee custom_group
		emp_group = frappe.db.get_value("Employee", self.employee, "custom_group")
		if emp_group == "Canteen":
			return "Canteen", "Employee Group"
		
		# Mặc định: Day shift
		return "Day", "Default"
	
	def check_maternity_benefit(self):
		"""Check xem employee có maternity benefit không
		- Giai đoạn mang thai: cần apply_pregnant_benefit = 1 trong Maternity Tracking record
		- Giai đoạn nghỉ thai sản: mặc định được hưởng
		- Giai đoạn nuôi con nhỏ: mặc định được hưởng
		"""
		# Get maternity tracking records for current date
		maternity_records = frappe.db.sql("""
			SELECT type, from_date, to_date, apply_pregnant_benefit
			FROM `tabMaternity Tracking` 
			WHERE parent = %(employee)s
			  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
			  AND from_date <= %(date)s
			  AND to_date >= %(date)s
		""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)
		
		if not maternity_records:
			return False
		
		# Check each active maternity record
		for record in maternity_records:
			# Handle case-insensitive matching for Young Child/child variations
			record_type_lower = record.type.lower() if record.type else ""
			if (record_type_lower == 'young child' or 
				record.type in ['Young Child', 'Maternity Leave']):
				# Giai đoạn nghỉ thai sản hoặc nuôi con nhỏ: mặc định được hưởng
				return True
			elif record.type == 'Pregnant':
				# Giai đoạn mang thai: kiểm tra apply_pregnant_benefit trong record
				if record.apply_pregnant_benefit == 1:
					return True
				# Nếu apply_pregnant_benefit = 0 hoặc NULL, không được hưởng
		
		return False
	
	def calculate_overtime_coefficient(self):
		"""Calculate overtime coefficient based on day type
		- Normal days (Monday-Saturday): 1.5
		- Sunday: 2.0
		- Holidays: 3.0
		"""
		from datetime import datetime

		if isinstance(self.attendance_date, str):
			date_obj = datetime.strptime(str(self.attendance_date), '%Y-%m-%d')
		else:
			date_obj = self.attendance_date

		# Check if it's a holiday first (to be implemented - placeholder for now)
		# TODO: Implement holiday checking logic
		# if self.is_holiday(date_obj):
		#     return 3.0

		# Check if it's Sunday
		if date_obj.weekday() == 6:  # Sunday
			return 2.0

		# Normal days (Monday-Saturday)
		return 1.5

	def get_shift_config(self, shift_type):
		"""Get shift configuration"""
		SHIFT_CONFIGS = {
			"Day": {
				"start": time(8, 0),     # 8:00
				"end": time(17, 0),      # 17:00  
				"break_start": time(12, 0),  # 12:00
				"break_end": time(13, 0),    # 13:00
				"allows_ot": True
			},
			"Canteen": {
				"start": time(7, 0),     # 7:00
				"end": time(16, 0),      # 16:00
				"break_start": time(11, 0),  # 11:00
				"break_end": time(12, 0),    # 12:00  
				"allows_ot": True
			},
			"Shift 1": {
				"start": time(6, 0),     # 6:00
				"end": time(14, 0),      # 14:00
				"break_start": time(10, 0),  # No break
				"break_end": time(10, 0),    # No break
				"allows_ot": False
			},
			"Shift 2": {
				"start": time(14, 0),    # 14:00
				"end": time(22, 0),      # 22:00
				"break_start": time(18, 0),  # No break
				"break_end": time(18, 0),    # No break
				"allows_ot": False  
			}
		}
		
		return SHIFT_CONFIGS.get(shift_type)
	
	def calculate_morning_hours(self, check_in, check_out, shift_config):
		"""Tính morning hours (shift_start -> break_start)
		Special case: Nếu check in trước giờ bắt đầu ca và check out trước giờ nghỉ trưa,
		thì working_hours = check out - bắt đầu ca
		"""
		if not check_in or not check_out:
			return 0
		
		# Convert to datetime for calculation
		shift_start = datetime.combine(check_in.date(), shift_config["start"])
		break_start = datetime.combine(check_in.date(), shift_config["break_start"])
		
		# Special case: check in trước ca và check out trước nghỉ trưa
		if check_in < shift_start and check_out <= break_start:
			# working_hours = check out - bắt đầu ca
			if check_out > shift_start:
				return time_diff_in_hours(check_out, shift_start)
			else:
				return 0
		
		# Normal case: tính theo logic cũ
		morning_start = max(check_in, shift_start)
		morning_end = min(check_out, break_start)
		
		if morning_end <= morning_start:
			return 0
		
		return time_diff_in_hours(morning_end, morning_start)
	
	def calculate_afternoon_hours(self, check_in, check_out, shift_config, has_maternity):
		"""Tính afternoon hours với maternity benefit"""
		if not check_in or not check_out:
			return 0
		
		# Convert to datetime for calculation
		break_end = datetime.combine(check_in.date(), shift_config["break_end"])
		shift_end = datetime.combine(check_in.date(), shift_config["end"])
		
		afternoon_start = max(check_in, break_end)
		
		if has_maternity:
			# Maternity benefit: về sớm 1h mà vẫn tính đủ giờ
			maternity_end = shift_end - timedelta(hours=1)
			if check_out >= maternity_end:
				afternoon_end = shift_end  # Tính đủ giờ
			else:
				afternoon_end = min(check_out, shift_end)
		else:
			afternoon_end = min(check_out, shift_end)
		
		if afternoon_end <= afternoon_start:
			return 0
		
		return time_diff_in_hours(afternoon_end, afternoon_start)
	
	def calculate_actual_overtime(self, check_in, check_out, shift_config, has_maternity=False):
		"""Tính actual overtime (pre-shift + lunch-break + post-shift) với maternity benefit"""
		if not check_in or not check_out:
			return 0

		# Convert to datetime for calculation
		shift_start = datetime.combine(check_in.date(), shift_config["start"])
		shift_end = datetime.combine(check_in.date(), shift_config["end"])
		break_start = datetime.combine(check_in.date(), shift_config["break_start"])
		break_end = datetime.combine(check_in.date(), shift_config["break_end"])

		# Pre-shift overtime (đi sớm hơn giờ vào ca) - CHỈ tính nếu có đăng ký OT trước ca
		pre_shift_ot = 0
		if check_in < shift_start:
			# Kiểm tra có đăng ký OT trước ca không
			has_pre_shift_registration = self.check_pre_shift_ot_registration(check_in, shift_start)
			if has_pre_shift_registration:
				pre_shift_ot = time_diff_in_hours(shift_start, check_in)
				# Sử dụng MIN_MINUTES_PRE_SHIFT_OT (60 phút) làm ngưỡng tối thiểu
				if pre_shift_ot * 60 < MIN_MINUTES_PRE_SHIFT_OT:
					pre_shift_ot = 0

		# Lunch break overtime (NEW) - tính OT trong giờ nghỉ trưa
		lunch_break_ot = 0
		# Chỉ tính nếu shift có lunch break (break_start != break_end)
		if shift_config["break_start"] != shift_config["break_end"]:
			# Điều kiện: check-in sớm hơn nghỉ trưa + check-out trễ hơn nghỉ trưa + có đăng ký OT lunch
			if (check_in < break_start and check_out > break_end and
				self.check_lunch_break_ot_registration(break_start, break_end)):
				# Tính toàn bộ lunch break period làm OT
				lunch_break_ot = time_diff_in_hours(break_end, break_start)
				# Apply minimum threshold
				if lunch_break_ot * 60 < MIN_MINUTES_OT:
					lunch_break_ot = 0

		# Post-shift overtime (về trễ hơn giờ tan ca) - ADJUSTED for maternity benefit
		post_shift_ot = 0
		expected_end = shift_end
		if has_maternity:
			# Maternity benefit: được về sớm 1 giờ, nên chỉ tính OT khi về sau expected_end
			expected_end = shift_end - timedelta(hours=1)

		# Chỉ tính post-shift OT khi check out trễ hơn 15 phút so với expected_end
		if check_out > expected_end:
			post_shift_ot = time_diff_in_hours(check_out, expected_end)
			# Rule: Post-shift OT < 15 phút (0.25h) = 0
			if post_shift_ot < 0.25:
				post_shift_ot = 0

		total_ot = pre_shift_ot + lunch_break_ot + post_shift_ot

		# Apply MIN_MINUTES_OT threshold: bỏ qua OT nếu < 15 phút
		if total_ot * 60 < MIN_MINUTES_OT:
			total_ot = 0

		return total_ot
	
	def check_pre_shift_ot_registration(self, check_in, shift_start):
		"""Kiểm tra có đăng ký OT trước ca làm việc không"""
		# Tìm registration OT trong khoảng thời gian check_in đến shift_start
		check_in_time = check_in.time()
		shift_start_time = shift_start.time()
		
		registrations = frappe.db.sql("""
			SELECT COUNT(*) as count
			FROM `tabOvertime Registration Detail` ord
			JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
			WHERE ord.employee = %(employee)s
			  AND ord.date = %(date)s
			  AND or_doc.docstatus = 1
			  AND ord.begin_time <= %(shift_start_time)s
			  AND ord.end_time >= %(check_in_time)s
		""", {
			"employee": self.employee, 
			"date": self.attendance_date,
			"shift_start_time": shift_start_time,
			"check_in_time": check_in_time
		}, as_dict=1)
		
		return registrations[0].count > 0 if registrations else False

	def check_lunch_break_ot_registration(self, break_start, break_end):
		"""Kiểm tra có đăng ký OT trong giờ nghỉ trưa không"""
		break_start_time = break_start.time()
		break_end_time = break_end.time()

		registrations = frappe.db.sql("""
			SELECT COUNT(*) as count
			FROM `tabOvertime Registration Detail` ord
			JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
			WHERE ord.employee = %(employee)s
			  AND ord.date = %(date)s
			  AND or_doc.docstatus = 1
			  AND (
				  -- OT registration overlaps with lunch break period
				  (ord.begin_time <= %(break_end)s AND ord.end_time >= %(break_start)s)
			  )
		""", {
			"employee": self.employee,
			"date": self.attendance_date,
			"break_start": break_start_time,
			"break_end": break_end_time
		}, as_dict=1)

		return registrations[0].count > 0 if registrations else False
	
	def get_approved_overtime(self, shift_type):
		"""Lấy submitted overtime từ registration (chưa cần approval)"""
		# Shift 1, 2 không được phép OT
		if shift_type in ["Shift 1", "Shift 2"]:
			return 0
		
		# Query submitted overtime (docstatus = 1, chưa cần approval)
		approved_ot = frappe.db.sql("""
			SELECT SUM(TIMESTAMPDIFF(MINUTE, ord.begin_time, ord.end_time) / 60.0) as total_hours
			FROM `tabOvertime Registration Detail` ord
			JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
			WHERE ord.employee = %(employee)s
			  AND ord.date = %(date)s
			  AND or_doc.docstatus = 1
		""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)
		
		return flt(approved_ot[0].total_hours) if approved_ot and approved_ot[0].total_hours else 0
	
	def calculate_late_early(self, check_in, check_out, shift_config, has_maternity):
		"""Calculate late entry and early exit"""
		if not check_in or not check_out:
			return False, False
		
		# Convert to datetime for calculation
		shift_start = datetime.combine(check_in.date(), shift_config["start"])
		shift_end = datetime.combine(check_in.date(), shift_config["end"])
		
		# Late entry: đi muộn hơn shift start
		late_entry = check_in > shift_start
		
		# Early exit: về sớm (có tính maternity benefit)
		expected_end = shift_end
		if has_maternity:
			expected_end = shift_end - timedelta(hours=1)
		
		early_exit = check_out < expected_end
		
		return late_entry, early_exit
	
	def generate_overtime_details_html(self):
		"""Generate HTML hiển thị chi tiết overtime"""
		if not self.actual_overtime and not self.approved_overtime:
			self.overtime_details_html = ""
			return
		
		html = f"""
		<div class="overtime-details">
			<table class="table table-condensed">
				<tr>
					<td>Actual Overtime:</td>
					<td>{self.actual_overtime:.2f} hours</td>
				</tr>
				<tr>
					<td>Registered Overtime:</td>
					<td>{self.approved_overtime:.2f} hours <small>(từ registration đã submit)</small></td>
				</tr>
				<tr>
					<td><strong>Final Overtime:</strong></td>
					<td><strong>{self.overtime_hours:.2f} hours</strong></td>
				</tr>
			</table>
		</div>
		"""
		self.overtime_details_html = html
	
	def generate_additional_info_html(self):
		"""Generate HTML hiển thị thông tin bổ sung bao gồm check-in/out và maternity benefit"""
		if not self.employee or not self.attendance_date:
			self.additional_info_html = "<div class='alert alert-warning'>Employee and Attendance Date are required to display additional information.</div>"
			return
		
		html = ""
		
		# 1. Maternity Benefit Section (only if there are actual maternity tracking records)
		if getattr(self, 'maternity_benefit', False):
			maternity_info = self.get_maternity_benefit_info()
			if maternity_info:  # Only show if there's actual maternity info
				html += f"""
				<div class="maternity-section" style="margin-bottom: 20px;">
					<div style="padding: 12px; background: linear-gradient(135deg, #ff6b9d 0%, #c44569 100%); color: white; border-radius: 6px; margin-bottom: 10px;">
						<h5 style="margin: 0; color: white;">🤱 Maternity Benefit Active</h5>
									</div>
					<div style="padding: 10px; background-color: #fdf2f8; border-left: 4px solid #ec4899; border-radius: 4px;">
						{maternity_info}
					</div>
				</div>
				"""
		
		# 2. Employee Check-ins Section
		checkins = frappe.db.sql("""
			SELECT name, time, device_id, custom_reason_for_manual_check_in
			FROM `tabEmployee Checkin` 
			WHERE employee = %(employee)s 
			AND DATE(time) = %(date)s
			ORDER BY time ASC
		""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)
		
		if not checkins:
			html += f"""
			<div class="alert alert-info" style="margin: 10px 0;">
				<h6>🔍 No Employee Check-ins found</h6>
				<p>No check-in records found for {self.employee_name or self.employee} on {self.attendance_date}.</p>
			</div>
			"""
		else:
			# Header
			html += f"""
			<div class="checkins-header" style="margin-bottom: 15px; padding: 10px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; border-radius: 6px;">
				<h5 style="margin: 0; color: white;">🏃 Employee Check-ins ({len(checkins)} records)</h5> 
			</div>
			"""
			
			# Table
			html += """
			<div class="table-responsive">
				<table class="table table-bordered table-sm">
					<thead style="background-color: #f8f9fa;">
						<tr>
							<th style="width: 25%;">📅 Time</th>
							<th style="width: 30%;">📋 Check-in Record</th>
							<th style="width: 20%;">📱 Device</th>
							<th style="width: 25%;">💬 Manual Reason</th>
						</tr>
					</thead>
					<tbody>
			"""
			
			for checkin in checkins:
				time_formatted = frappe.utils.format_datetime(checkin.time) if checkin.time else 'N/A'
				manual_reason = checkin.custom_reason_for_manual_check_in or '-'
				
				# Show manual reason with different styling if it exists
				if checkin.custom_reason_for_manual_check_in:
					reason_display = f'<span style="color: #ff5722; font-style: italic;">{manual_reason}</span>'
				else:
					reason_display = '<span style="color: #999;">-</span>'
				
				html += f"""
					<tr>
						<td style="font-family: monospace;">{time_formatted}</td>
						<td><a href="/app/employee-checkin/{checkin.name}" target="_blank" class="text-primary" style="text-decoration: none;">{checkin.name}</a></td>
						<td><code>{checkin.device_id or '-'}</code></td>
						<td>{reason_display}</td>
					</tr>
				"""
			
			html += """
					</tbody>
				</table>
			</div>
			""" 
		
		self.additional_info_html = html

	def get_maternity_benefit_info(self):
		"""Get detailed maternity benefit information"""
		if not self.employee or not self.attendance_date:
			return "<p>No maternity information available</p>"
		
		# Get maternity tracking records for current date
		maternity_records = frappe.db.sql("""
			SELECT type, from_date, to_date, apply_pregnant_benefit
			FROM `tabMaternity Tracking` 
			WHERE parent = %(employee)s
			  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
			  AND from_date <= %(date)s
			  AND to_date >= %(date)s
			ORDER BY from_date ASC
		""", {"employee": self.employee, "date": self.attendance_date}, as_dict=1)
		
		# If no maternity tracking records, return empty
		if not maternity_records:
			return ""
		
		info_html = "<div class='maternity-details'>"
		
		# Track if any benefit is applied
		benefit_applied = False
		
		for record in maternity_records:
			# Set icon and color based on type
			if record.type == "Pregnant":
				benefit_type_icon = "🤰"
				benefit_type_color = "#e91e63"
			elif record.type == "Maternity Leave":
				benefit_type_icon = "🏥"
				benefit_type_color = "#ff9800"
			else:  # Young Child
				benefit_type_icon = "👶"
				benefit_type_color = "#9c27b0"
			
			# Determine benefit status for this record
			# Handle case-insensitive matching for Young Child/child variations
			record_type_lower = record.type.lower() if record.type else ""
			if (record_type_lower == 'young child' or 
				record.type in ['Young Child', 'Maternity Leave']):
				# Young child or maternity leave: always gets benefit
				benefit_status = "ENABLED (Automatic)"
				if record_type_lower == 'young child' or record.type == 'Young Child':
					benefit_note = "Childcare benefit - automatically enabled"
				else:
					benefit_note = "Maternity leave benefit - automatically enabled"
				benefit_applied = True
			elif record.type == 'Pregnant':
				# Pregnant: depends on apply_pregnant_benefit trong Maternity Tracking record
				if record.apply_pregnant_benefit == 1:
					benefit_status = "ENABLED"
					benefit_note = "Pregnancy benefit enabled via Maternity Tracking record"
					benefit_applied = True
				else:
					benefit_status = "DISABLED"
					benefit_note = "Pregnancy benefit not enabled in Maternity Tracking record"
			else:
				# Unknown type
				benefit_status = "UNKNOWN"
				benefit_note = f"Unknown maternity type: {record.type}"
			
			info_html += f"""
			<div style="margin-bottom: 12px; padding: 8px; border-left: 3px solid {benefit_type_color}; background: rgba(233, 30, 99, 0.05);">
				<h6 style="margin: 0 0 5px 0; color: {benefit_type_color};">
					{benefit_type_icon} {record.type} Benefit ({benefit_status})
				</h6>
				<div style="font-size: 12px; color: #666;">
					<strong>Period:</strong> {frappe.utils.formatdate(record.from_date)} - {frappe.utils.formatdate(record.to_date)}<br>
					<strong>Source:</strong> Maternity Tracking Record<br>
					<strong>Note:</strong> {benefit_note}<br>
					<strong>Benefit:</strong> Early departure allowed (1 hour reduction)
				</div>
			</div>
			"""
		
		if not maternity_records:
			info_html += "<p>No active maternity benefit periods found</p>"
		elif not benefit_applied:
			info_html += f"""
			<div style="margin-bottom: 12px; padding: 8px; border-left: 3px solid #ffc107; background: rgba(255, 193, 7, 0.05);">
				<h6 style="margin: 0 0 5px 0; color: #ffc107;">
					⚠️ No Active Benefits
				</h6>
				<div style="font-size: 12px; color: #666;">
					While maternity tracking records exist, no benefits are currently active based on current settings.
				</div>
			</div>
			"""
		
		info_html += "</div>"
		return info_html

	def clear_all_fields(self):
		"""Clear all calculated fields when no checkin data"""
		fields_to_clear = [
			'check_in', 'check_out', 'working_hours', 'overtime_hours', 'actual_overtime',
			'approved_overtime', 'late_entry', 'early_exit', 'maternity_benefit'
		]

		for field in fields_to_clear:
			setattr(self, field, 0 if field in ['working_hours', 'overtime_hours', 'actual_overtime', 'approved_overtime'] else None)

		self.status = "Absent"
		self.overtime_details_html = ""
		# Keep additional_info_html - don't clear it as it should always show check-in data and maternity info


# ===== SUNDAY OVERTIME HELPER FUNCTIONS (Shared by single & bulk operations) =====

def get_sunday_shift_config(ot_begin_time, ot_end_time):
	"""
	Get shift configuration for Sunday based on OT registration
	Shift start/end = OT registration start/end
	Lunch break: 12:00-13:00 if OT starts before 12:00 and ends after 13:00
	"""
	from datetime import time as dt_time, timedelta

	# Convert timedelta to time if necessary (MySQL returns TIME as timedelta)
	def to_time(t):
		if isinstance(t, timedelta):
			total_seconds = int(t.total_seconds())
			hours = total_seconds // 3600
			minutes = (total_seconds % 3600) // 60
			seconds = total_seconds % 60
			return dt_time(hours, minutes, seconds)
		return t

	ot_begin_time = to_time(ot_begin_time)
	ot_end_time = to_time(ot_end_time)

	shift_config = {
		"start": ot_begin_time,
		"end": ot_end_time,
		"allows_ot": True
	}

	# Check if lunch break applies: OT starts before 12:00 and ends after 13:00
	lunch_start = dt_time(12, 0)
	lunch_end = dt_time(13, 0)

	if ot_begin_time < lunch_start and ot_end_time > lunch_end:
		shift_config["break_start"] = lunch_start
		shift_config["break_end"] = lunch_end
	else:
		# No lunch break
		shift_config["break_start"] = ot_begin_time
		shift_config["break_end"] = ot_begin_time

	return shift_config

def calculate_sunday_overtime(check_in, check_out, ot_registrations, shift_config):
	"""
	Calculate Sunday overtime and working hours
	NEW LOGIC: Always calculate based on actual check-in/out

	Args:
		check_in: Check-in datetime
		check_out: Check-out datetime
		ot_registrations: List of OT registrations (can be None or empty)
		shift_config: Shift configuration (used when no OT registration)

	Returns: (working_hours, actual_ot, approved_ot, has_lunch_benefit)
		- working_hours: Actual hours worked
		- actual_ot: Same as working_hours (all Sunday hours are OT)
		- approved_ot: Hours from OT registration (0 if no registration)
		- has_lunch_benefit: True if worked >= 4 hours and checkout after 13:00
	"""
	if not check_in or not check_out:
		return 0, 0, 0, False

	from frappe.utils import time_diff_in_hours
	from datetime import datetime, time as dt_time, timedelta

	# Helper function to convert timedelta to time
	def to_time(t):
		if isinstance(t, timedelta):
			total_seconds = int(t.total_seconds())
			hours = total_seconds // 3600
			minutes = (total_seconds % 3600) // 60
			seconds = total_seconds % 60
			return dt_time(hours, minutes, seconds)
		return t

	# Determine shift_config to use
	sunday_shift_config = None
	if ot_registrations:
		# Convert all begin_time and end_time from ot_registrations
		for ot in ot_registrations:
			ot.begin_time = to_time(ot.begin_time)
			ot.end_time = to_time(ot.end_time)

		# Get earliest OT start and latest OT end from registrations
		ot_begin_time = min([ot.begin_time for ot in ot_registrations])
		ot_end_time = max([ot.end_time for ot in ot_registrations])

		# Get shift config based on OT registration
		sunday_shift_config = get_sunday_shift_config(ot_begin_time, ot_end_time)
	else:
		# No OT registration, use provided shift_config (Day shift)
		sunday_shift_config = shift_config

	# Calculate approved OT (sum of all OT registrations, minus lunch break if applicable)
	approved_ot = 0
	lunch_start = dt_time(12, 0)
	lunch_end = dt_time(13, 0)

	for ot in ot_registrations:
		begin_dt = datetime.combine(check_in.date(), ot.begin_time)
		end_dt = datetime.combine(check_in.date(), ot.end_time)
		ot_hours = time_diff_in_hours(end_dt, begin_dt)

		# If OT registration contains lunch break (starts before 12:00 and ends after 13:00), subtract 1 hour
		if ot.begin_time < lunch_start and ot.end_time > lunch_end:
			ot_hours -= 1  # Subtract 1 hour for lunch break

		approved_ot += ot_hours

	# Calculate actual working time (check_in to check_out minus lunch break if applicable)
	shift_start = datetime.combine(check_in.date(), sunday_shift_config["start"])
	shift_end = datetime.combine(check_in.date(), sunday_shift_config["end"])
	break_start = datetime.combine(check_in.date(), sunday_shift_config["break_start"])
	break_end = datetime.combine(check_in.date(), sunday_shift_config["break_end"])

	# Calculate working time before lunch
	morning_start = max(check_in, shift_start)
	morning_end = min(check_out, break_start)
	morning_hours = time_diff_in_hours(morning_end, morning_start) if morning_end > morning_start else 0

	# Calculate working time after lunch
	afternoon_start = max(check_in, break_end)
	afternoon_end = min(check_out, shift_end)
	afternoon_hours = time_diff_in_hours(afternoon_end, afternoon_start) if afternoon_end > afternoon_start else 0

	working_hours = morning_hours + afternoon_hours
	actual_ot = working_hours  # On Sunday, all working hours are OT

	# Apply minimum threshold
	if actual_ot * 60 < MIN_MINUTES_WORKING_HOURS:
		working_hours = 0
		actual_ot = 0

	# Check lunch benefit: worked >= 4 hours and check_out after 13:00
	has_lunch_benefit = False
	if working_hours >= MIN_SUNDAY_OT_FOR_LUNCH_BENEFIT and check_out.time() > dt_time(13, 0):
		has_lunch_benefit = True

	return working_hours, actual_ot, approved_ot, has_lunch_benefit

def apply_sunday_logic(doc, check_in, check_out, ot_registrations, shift_config):
	"""
	Apply Sunday logic to document (shared between single & bulk operations)
	This function modifies the document in place

	NEW LOGIC:
	- Calculate working_hours based on actual check-in/out
	- actual_ot = working_hours (all Sunday hours are OT)
	- working_hours = 0 (Sunday has no regular working hours)
	- approved_ot = sum from OT registrations (0 if no registration)
	- overtime_hours = actual_ot if no registration, else min(actual_ot, approved_ot)
	"""
	working_hours, actual_ot, approved_ot, has_lunch_benefit = calculate_sunday_overtime(
		check_in, check_out, ot_registrations, shift_config
	)

	# Sunday: working_hours = 0, all hours are overtime
	doc.working_hours = 0
	doc.actual_overtime = doc.decimal_round(actual_ot)
	doc.approved_overtime = doc.decimal_round(approved_ot)

	# NEW LOGIC: If no OT registration, final OT = actual OT
	if not ot_registrations or approved_ot == 0:
		doc.overtime_hours = doc.decimal_round(actual_ot)
	else:
		# With OT registration, use minimum
		doc.overtime_hours = doc.decimal_round(min(actual_ot, approved_ot))

	# Set status based on lunch benefit
	if has_lunch_benefit:
		doc.status = "Sunday, Lunch benefit"
	else:
		doc.status = "Sunday"

	# Calculate final OT with coefficient
	doc.overtime_coefficient = 2.0  # Sunday coefficient
	doc.final_ot_with_coefficient = doc.decimal_round(doc.overtime_hours * doc.overtime_coefficient)

	return has_lunch_benefit

@frappe.whitelist()
def send_sunday_overtime_alert(date):
	"""
	Send comprehensive weekly OT report including:
	1. Sunday overtime for the given date
	2. Top 50 weekly OT (from Monday to Sunday)
	3. Top 50 monthly OT (payroll period: 26th to 25th)
	"""
	from frappe.utils import getdate, formatdate, add_days
	from datetime import datetime

	date = getdate(date)

	# Calculate date ranges
	# Week: Monday to Sunday (6 days before the given Sunday)
	week_start = add_days(date, -6)  # Monday
	week_end = date  # Sunday

	# Month: 26th of previous month to 25th of current month
	current_month = date.month
	current_year = date.year

	if current_month == 1:
		prev_month = 12
		prev_year = current_year - 1
	else:
		prev_month = current_month - 1
		prev_year = current_year

	month_start = getdate(f"{prev_year}-{prev_month:02d}-26")
	month_end = getdate(f"{current_year}-{current_month:02d}-25")

	# ===== 1. Get Sunday overtime records =====
	sunday_records = frappe.db.sql("""
		SELECT
			employee,
			employee_name,
			custom_group,
			check_in,
			check_out,
			overtime_hours,
			status
		FROM `tabDaily Timesheet`
		WHERE attendance_date = %(date)s
		  AND DAYOFWEEK(attendance_date) = 1
		  AND overtime_hours > 0
		ORDER BY overtime_hours DESC, employee_name
	""", {"date": date}, as_dict=1)

	# ===== 2. Get top 50 weekly OT =====
	weekly_top = get_top_ot_weekly(week_start, week_end, limit=50)

	# ===== 3. Get unregistered OT (actual OT >= MIN_MINUTES_OT but approved OT = 0) =====
	# INCLUDES SUNDAY - to catch Sunday OT without registration
	min_ot_hours = MIN_MINUTES_OT / 60.0  # Convert minutes to hours
	unregistered_ot = frappe.db.sql("""
		SELECT
			employee,
			employee_name,
			custom_group,
			attendance_date,
			actual_overtime,
			check_in,
			check_out
		FROM `tabDaily Timesheet`
		WHERE attendance_date BETWEEN %(from_date)s AND %(to_date)s
		  AND actual_overtime >= %(min_ot_hours)s
		  AND approved_overtime = 0
		ORDER BY attendance_date ASC, actual_overtime DESC
	""", {"from_date": week_start, "to_date": week_end, "min_ot_hours": min_ot_hours}, as_dict=1)

	# ===== 4. Get top 50 monthly OT =====
	monthly_top = get_top_ot_monthly(month_start, month_end, limit=50)

	# Build email subject
	subject = f"Báo cáo tăng ca: {formatdate(week_start)} - {formatdate(week_end)}"

	# Current timestamp
	current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

	# ===== Build HTML content =====

	# 1. Sunday OT table
	sunday_table_rows = ""
	if sunday_records:
		for idx, record in enumerate(sunday_records, 1):
			check_in_time = record.check_in.strftime("%H:%M") if record.check_in else "-"
			check_out_time = record.check_out.strftime("%H:%M") if record.check_out else "-"
			sunday_table_rows += f"""
			<tr>
				<td style="text-align: center;">{idx}</td>
				<td>{record.employee}</td>
				<td>{record.employee_name}</td>
				<td>{record.custom_group or '-'}</td>
				<td style="text-align: center;">{check_in_time}</td>
				<td style="text-align: center;">{check_out_time}</td>
				<td style="text-align: center;">{record.overtime_hours:.2f}</td>
				<td>{record.status}</td>
			</tr>
			"""
	else:
		sunday_table_rows = '<tr><td colspan="8" style="text-align: center; color: #999;">Không có dữ liệu</td></tr>'

	# 2. Weekly top OT table
	weekly_table_rows = ""
	if weekly_top:
		for idx, record in enumerate(weekly_top, 1):
			weekly_table_rows += f"""
			<tr>
				<td style="text-align: center;">{idx}</td>
				<td>{record.employee}</td>
				<td>{record.employee_name}</td>
				<td>{record.custom_group or '-'}</td>
				<td style="text-align: center;">{record.total_ot_hours:.2f}</td>
				<td style="text-align: center;">{record.days_with_ot}</td>
			</tr>
			"""
	else:
		weekly_table_rows = '<tr><td colspan="6" style="text-align: center; color: #999;">Không có dữ liệu</td></tr>'

	# 3. Unregistered OT table (actual OT >= MIN_MINUTES_OT h but no approval)
	unregistered_table_rows = ""
	if unregistered_ot:
		for idx, record in enumerate(unregistered_ot, 1):
			check_in_time = record.check_in.strftime("%H:%M") if record.check_in else "-"
			check_out_time = record.check_out.strftime("%H:%M") if record.check_out else "-"
			unregistered_table_rows += f"""
			<tr>
				<td style="text-align: center;">{idx}</td>
				<td>{record.employee}</td>
				<td>{record.employee_name}</td>
				<td>{record.custom_group or '-'}</td>
				<td style="text-align: center;">{formatdate(record.attendance_date)}</td>
				<td style="text-align: center;">{record.actual_overtime:.2f}</td>
				<td style="text-align: center;">{check_in_time}</td>
				<td style="text-align: center;">{check_out_time}</td>
			</tr>
			"""
	else:
		unregistered_table_rows = '<tr><td colspan="8" style="text-align: center; color: #999;">Không có dữ liệu</td></tr>'

	# 4. Monthly top OT table
	monthly_table_rows = ""
	if monthly_top:
		for idx, record in enumerate(monthly_top, 1):
			# Determine row color based on total OT hours
			total_ot = record.total_ot_hours
			threshold_high = MAX_MONTHLY_OT_HOURS  # 40 hours
			threshold_warning = MAX_MONTHLY_OT_HOURS * 3 / 4  # 30 hours

			# Set text color based on thresholds
			if total_ot > threshold_high:
				row_color = "color: #dc3545;" # Red for > 40h
			elif total_ot > threshold_warning:
				row_color = "color: #ff8c00;"  # Orange for > 30h
			else:
				row_color = ""  # Normal black text

			monthly_table_rows += f"""
			<tr style="{row_color}">
				<td style="text-align: center;">{idx}</td>
				<td>{record.employee}</td>
				<td>{record.employee_name}</td>
				<td>{record.custom_group or '-'}</td>
				<td style="text-align: center;">{record.total_ot_hours:.2f}</td>
				<td style="text-align: center;">{record.days_with_ot}</td>
				<td style="text-align: center;">{record.sunday_ot_hours:.2f}</td>
			</tr>
			"""
	else:
		monthly_table_rows = '<tr><td colspan="7" style="text-align: center; color: #999;">Không có dữ liệu</td></tr>'

	# Build complete email message
	message = f"""
	<div style="font-family: Arial, sans-serif;">
		<h2 style="color: #007bff;">Báo cáo tăng ca: {formatdate(week_start)} - {formatdate(week_end)}</h2>
		<p style="color: #666; font-size: 14px;">Báo cáo này được gửi tự động từ ERPNext lúc <strong>{current_time}</strong></p>

		<hr style="border: 1px solid #ddd; margin: 20px 0;">

		<!-- Section 1: Sunday OT -->
		<h3 style="color: #28a745;">1. Tăng ca Chủ nhật - {formatdate(date)}</h3>
		<p>Tổng số nhân viên: <strong>{len(sunday_records)}</strong></p>

		<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
			<thead style="background-color: #28a745; color: white;">
				<tr>
					<th>STT</th>
					<th>Mã NV</th>
					<th>Tên nhân viên</th>
					<th>Nhóm</th>
					<th>Giờ vào</th>
					<th>Giờ ra</th>
					<th>Giờ OT</th>
					<th>Trạng thái</th>
				</tr>
			</thead>
			<tbody>
				{sunday_table_rows}
			</tbody>
		</table>

		<hr style="border: 1px solid #ddd; margin: 30px 0;">

		<!-- Section 2: Weekly Top 50 -->
		<h3 style="color: #fd7e14;">2. Top 50 tăng ca cao nhất tuần</h3> 

		<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
			<thead style="background-color: #fd7e14; color: white;">
				<tr>
					<th>STT</th>
					<th>Mã NV</th>
					<th>Tên nhân viên</th>
					<th>Nhóm</th>
					<th>Tổng giờ OT</th>
					<th>Số ngày OT</th>
				</tr>
			</thead>
			<tbody>
				{weekly_table_rows}
			</tbody>
		</table>

		<hr style="border: 1px solid #ddd; margin: 30px 0;">

		<!-- Section 3: Unregistered OT -->
		<h3 style="color: #ffc107;">3. Danh sách có tăng ca thực tế >= {MIN_MINUTES_OT} phút ({min_ot_hours:.1f}h) nhưng không có đăng ký tăng ca</h3>
		<p>Tuần {formatdate(week_start)} - {formatdate(week_end)}</p>
		<p>Tổng số bản ghi: <strong>{len(unregistered_ot)}</strong></p>

		<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
			<thead style="background-color: #ffc107; color: white;">
				<tr>
					<th>STT</th>
					<th>Mã NV</th>
					<th>Tên nhân viên</th>
					<th>Nhóm</th>
					<th>Ngày</th>
					<th>Giờ OT thực tế</th>
					<th>Check In</th>
					<th>Check Out</th>
				</tr>
			</thead>
			<tbody>
				{unregistered_table_rows}
			</tbody>
		</table>

		<hr style="border: 1px solid #ddd; margin: 30px 0;">

		<!-- Section 4: Monthly Top 50 -->
		<h3 style="color: #dc3545;">4. Top 50 tăng ca cao nhất tháng ({formatdate(month_start)} - {formatdate(month_end)})</h3>
		<p>Chu kỳ tính: ngày 26 tháng trước đến ngày 25 tháng hiện tại</p>

		<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
			<thead style="background-color: #dc3545; color: white;">
				<tr>
					<th>STT</th>
					<th>Mã NV</th>
					<th>Tên nhân viên</th>
					<th>Nhóm</th>
					<th>Tổng giờ OT</th>
					<th>Số ngày OT</th>
					<th>OT Chủ nhật</th>
				</tr>
			</thead>
			<tbody>
				{monthly_table_rows}
			</tbody>
		</table>

		<hr style="border: 1px solid #ddd; margin: 30px 0;"> 
	</div>
	"""

	# Send email
	try:
		frappe.sendmail(
			recipients=OVERTIME_ALERT_RERIPIENTS,
			subject=subject,
			message=message,
			delayed=False
		)
		frappe.msgprint(f"Email report sent to {', '.join(OVERTIME_ALERT_RERIPIENTS)}")
		frappe.logger().info(f"Weekly OT report sent successfully for week {formatdate(week_start)} - {formatdate(week_end)}")
	except Exception as e:
		frappe.log_error(f"Failed to send weekly OT report: {str(e)}", "Weekly OT Report Error")
		frappe.throw(f"Failed to send email: {str(e)}")

def get_top_ot_weekly(from_date, to_date, limit=TOP_OT_NUMBER):
	"""
	Get top N employees with highest overtime hours in a week
	Returns list of dict with employee info and total OT hours
	"""
	from frappe.utils import getdate

	records = frappe.db.sql("""
		SELECT
			employee,
			employee_name,
			custom_group,
			SUM(overtime_hours) as total_ot_hours,
			SUM(final_ot_with_coefficient) as total_ot_with_coef,
			COUNT(*) as days_with_ot
		FROM `tabDaily Timesheet`
		WHERE attendance_date BETWEEN %(from_date)s AND %(to_date)s
		  AND overtime_hours > 0
		GROUP BY employee, employee_name, custom_group
		ORDER BY total_ot_hours DESC
		LIMIT %(limit)s
	""", {"from_date": getdate(from_date), "to_date": getdate(to_date), "limit": limit}, as_dict=1)

	return records

def get_top_ot_monthly(from_date, to_date, limit=TOP_OT_NUMBER):
	"""
	Get top N employees with highest overtime hours in a month (payroll period: 26th to 25th)
	Returns list of dict with employee info and total OT hours
	"""
	from frappe.utils import getdate

	records = frappe.db.sql("""
		SELECT
			employee,
			employee_name,
			custom_group,
			SUM(overtime_hours) as total_ot_hours,
			SUM(final_ot_with_coefficient) as total_ot_with_coef,
			COUNT(*) as days_with_ot,
			SUM(CASE WHEN DAYOFWEEK(attendance_date) = 1 THEN overtime_hours ELSE 0 END) as sunday_ot_hours
		FROM `tabDaily Timesheet`
		WHERE attendance_date BETWEEN %(from_date)s AND %(to_date)s
		  AND overtime_hours > 0
		GROUP BY employee, employee_name, custom_group
		ORDER BY total_ot_hours DESC
		LIMIT %(limit)s
	""", {"from_date": getdate(from_date), "to_date": getdate(to_date), "limit": limit}, as_dict=1)

	return records

@frappe.whitelist()
def get_additional_info_html(docname):
	"""Get additional info HTML for a specific Daily Timesheet document"""
	doc = frappe.get_doc("Daily Timesheet", docname)
	doc.generate_additional_info_html()
	return doc.additional_info_html

@frappe.whitelist()
def recalculate_timesheet(docname):
	"""Recalculate complete timesheet - combines sync from checkin + recalculate overtime"""
	doc = frappe.get_doc("Daily Timesheet", docname)
	doc.calculate_all_fields()
	doc.save()
	frappe.msgprint("Timesheet recalculated successfully from Employee Checkin data and Overtime Registrations")


@frappe.whitelist()
def get_algorithm_constants():
	"""Get all algorithm constants for dialog display"""
	return {
		"MIN_MINUTES_OT": MIN_MINUTES_OT,
		"MIN_MINUTES_WORKING_HOURS": MIN_MINUTES_WORKING_HOURS,
		"MIN_MINUTES_PRE_SHIFT_OT": MIN_MINUTES_PRE_SHIFT_OT,
		"MIN_MINUTES_CHECKIN_FILTER": MIN_MINUTES_CHECKIN_FILTER,
		"MIN_SUNDAY_OT_FOR_LUNCH_BENEFIT": MIN_SUNDAY_OT_FOR_LUNCH_BENEFIT,
		"OVERTIME_ALERT_RERIPIENTS": ", ".join(OVERTIME_ALERT_RERIPIENTS),  # Join list to string for display
		"TOP_OT_NUMBER": TOP_OT_NUMBER,
		"MAX_MONTHLY_OT_HOURS": MAX_MONTHLY_OT_HOURS,
		"SUNDAY_OT_COEFFICIENT": 2.0,
		"NORMAL_OT_COEFFICIENT": 1.5,
		"HOLIDAY_OT_COEFFICIENT": 3.0
	}


@frappe.whitelist()
def debug_maternity_issue(doc_name):
	"""Debug maternity benefit issue for a specific Daily Timesheet"""
	doc = frappe.get_doc("Daily Timesheet", doc_name)
	
	result = {
		"doc_name": doc_name,
		"employee": doc.employee,
		"employee_name": doc.employee_name,
		"attendance_date": str(doc.attendance_date),
		"current_maternity_benefit": doc.maternity_benefit,
		"check_in": str(doc.check_in) if doc.check_in else None,
		"check_out": str(doc.check_out) if doc.check_out else None,
		"working_hours": doc.working_hours,
		"maternity_records": []
	}
	
	# Get maternity tracking records
	maternity_records = frappe.db.sql("""
		SELECT type, from_date, to_date, apply_pregnant_benefit
		FROM `tabMaternity Tracking` 
		WHERE parent = %(employee)s
		  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
		ORDER BY from_date DESC
	""", {"employee": doc.employee}, as_dict=1)
	
	correct_benefit = False
	active_records = []
	
	for record in maternity_records:
		record_info = {
			"type": record.type,
			"from_date": str(record.from_date),
			"to_date": str(record.to_date), 
			"apply_pregnant_benefit": record.apply_pregnant_benefit,
			"is_active": record.from_date <= doc.attendance_date <= record.to_date
		}
		
		result["maternity_records"].append(record_info)
		
		# Check if this record affects the attendance date
		if record.from_date <= doc.attendance_date <= record.to_date:
			active_records.append(record)
			# Handle case-insensitive matching for Young Child/child variations
			record_type_lower = record.type.lower() if record.type else ""
			if (record_type_lower == 'young child' or 
				record.type in ['Young Child', 'Maternity Leave']):
				correct_benefit = True
				record_info["should_get_benefit"] = True
				record_info["reason"] = f"{record.type} gets automatic benefit"
			elif record.type == 'Pregnant':
				if record.apply_pregnant_benefit == 1:
					correct_benefit = True
					record_info["should_get_benefit"] = True
					record_info["reason"] = "Pregnant with apply_pregnant_benefit = 1"
				else:
					record_info["should_get_benefit"] = False
					record_info["reason"] = f"Pregnant but apply_pregnant_benefit = {record.apply_pregnant_benefit}"
	
	result["correct_maternity_benefit"] = correct_benefit
	result["is_correct"] = doc.maternity_benefit == correct_benefit
	result["active_records_count"] = len(active_records)
	
	if not result["is_correct"]:
		result["issue"] = "Maternity benefit value is incorrect"
		if active_records:
			for record in active_records:
				if record.type == 'Maternity Leave' and doc.check_in and doc.check_out:
					result["potential_cause"] = "Employee on 'Maternity Leave' period but has check-in/out - period dates might be incorrect"
	
	return result

@frappe.whitelist()
def fix_maternity_record(doc_name):
	"""Fix maternity benefit for a specific record"""
	doc = frappe.get_doc("Daily Timesheet", doc_name)
	doc.calculate_all_fields()
	doc.save()
	return f"Fixed {doc_name}: maternity_benefit = {doc.maternity_benefit}"

# OPTIMIZED BULK OPERATIONS - HYBRID APPROACH

def load_bulk_timesheet_data(employee_ids, from_date, to_date):
	"""
	Load ALL required data in bulk with minimal queries
	Returns dictionary with all pre-loaded data indexed by (employee, date)
	"""
	from frappe.utils import getdate

	from_date = getdate(from_date)
	to_date = getdate(to_date)

	# Convert employee_ids to SQL-safe format
	emp_placeholders = ', '.join(['%s'] * len(employee_ids))

	# 1. Load all employee checkins in date range
	checkins_data = frappe.db.sql(f"""
		SELECT employee, DATE(time) as date, time as check_time, log_type
		FROM `tabEmployee Checkin`
		WHERE employee IN ({emp_placeholders})
		  AND DATE(time) BETWEEN %s AND %s
		ORDER BY employee, time ASC
	""", tuple(employee_ids) + (from_date, to_date), as_dict=1)

	# Index checkins by (employee, date)
	checkins_by_emp_date = {}
	for checkin in checkins_data:
		key = (checkin.employee, checkin.date)
		if key not in checkins_by_emp_date:
			checkins_by_emp_date[key] = []
		checkins_by_emp_date[key].append(checkin)

	# 2. Load all shift registrations
	shift_reg_data = frappe.db.sql(f"""
		SELECT srd.employee, srd.begin_date, srd.end_date, srd.shift
		FROM `tabShift Registration Detail` srd
		JOIN `tabShift Registration` sr ON srd.parent = sr.name
		WHERE srd.employee IN ({emp_placeholders})
		  AND sr.docstatus = 1
		  AND srd.begin_date <= %s
		  AND srd.end_date >= %s
		ORDER BY sr.creation DESC
	""", tuple(employee_ids) + (to_date, from_date), as_dict=1)

	# Index shift registrations by employee
	shift_reg_by_emp = {}
	for reg in shift_reg_data:
		emp = reg.employee
		if emp not in shift_reg_by_emp:
			shift_reg_by_emp[emp] = []
		shift_reg_by_emp[emp].append(reg)

	# 3. Load employee groups AND joining dates (for Canteen shift detection + validation)
	emp_data = frappe.db.sql(f"""
		SELECT name, custom_group, date_of_joining
		FROM `tabEmployee`
		WHERE name IN ({emp_placeholders})
	""", tuple(employee_ids), as_dict=1)

	emp_group_map = {ed.name: ed.custom_group for ed in emp_data}
	emp_joining_map = {ed.name: ed.date_of_joining for ed in emp_data}

	# 4. Load all maternity tracking records
	maternity_data = frappe.db.sql(f"""
		SELECT parent as employee, type, from_date, to_date, apply_pregnant_benefit
		FROM `tabMaternity Tracking`
		WHERE parent IN ({emp_placeholders})
		  AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
		  AND from_date <= %s
		  AND to_date >= %s
	""", tuple(employee_ids) + (to_date, from_date), as_dict=1)

	# Index maternity by employee
	maternity_by_emp = {}
	for mat in maternity_data:
		emp = mat.employee
		if emp not in maternity_by_emp:
			maternity_by_emp[emp] = []
		maternity_by_emp[emp].append(mat)

	# 5. Load all overtime registrations
	# NOTE: MySQL TIME columns are returned as timedelta, so we need to convert them
	overtime_data = frappe.db.sql(f"""
		SELECT ord.employee, ord.date, ord.begin_time, ord.end_time
		FROM `tabOvertime Registration Detail` ord
		JOIN `tabOvertime Registration` or_doc ON ord.parent = or_doc.name
		WHERE ord.employee IN ({emp_placeholders})
		  AND ord.date BETWEEN %s AND %s
		  AND or_doc.docstatus = 1
	""", tuple(employee_ids) + (from_date, to_date), as_dict=1)

	# Convert timedelta to time objects for proper comparison
	from datetime import time as dt_time, timedelta
	for ot in overtime_data:
		if isinstance(ot.begin_time, timedelta):
			total_seconds = int(ot.begin_time.total_seconds())
			hours = total_seconds // 3600
			minutes = (total_seconds % 3600) // 60
			seconds = total_seconds % 60
			ot.begin_time = dt_time(hours, minutes, seconds)
		if isinstance(ot.end_time, timedelta):
			total_seconds = int(ot.end_time.total_seconds())
			hours = total_seconds // 3600
			minutes = (total_seconds % 3600) // 60
			seconds = total_seconds % 60
			ot.end_time = dt_time(hours, minutes, seconds)

	# Index overtime by (employee, date)
	overtime_by_emp_date = {}
	for ot in overtime_data:
		key = (ot.employee, ot.date)
		if key not in overtime_by_emp_date:
			overtime_by_emp_date[key] = []
		overtime_by_emp_date[key].append(ot)

	return {
		"checkins": checkins_by_emp_date,
		"shift_registrations": shift_reg_by_emp,
		"employee_groups": emp_group_map,
		"employee_joining_dates": emp_joining_map,
		"maternity_tracking": maternity_by_emp,
		"overtime_registrations": overtime_by_emp_date
	}

def calculate_all_fields_optimized(doc, bulk_data, skip_html_generation=False):
	"""
	Optimized version of calculate_all_fields that uses pre-loaded bulk_data
	No individual DB queries - all data from bulk_data dictionary
	"""
	if not doc.employee or not doc.attendance_date:
		return

	from frappe.utils import getdate, time_diff_in_hours
	from datetime import datetime, time, timedelta

	# Validate attendance_date is not before employee's joining date (from bulk_data)
	date_of_joining = bulk_data["employee_joining_dates"].get(doc.employee)
	if date_of_joining and getdate(doc.attendance_date) < getdate(date_of_joining):
		frappe.throw(f"Cannot create Daily Timesheet: Attendance date ({doc.attendance_date}) is before employee's joining date ({date_of_joining})")

	# Only generate additional info HTML if not skipped (for bulk operations)
	if not skip_html_generation:
		doc.generate_additional_info_html()

	# 1. Get check-in/out data from bulk_data
	check_in, check_out = get_employee_checkin_data_from_bulk(doc.employee, doc.attendance_date, bulk_data)

	# 2. Xác định shift type from bulk_data
	shift_type, determined_by = get_shift_type_from_bulk(doc.employee, doc.attendance_date, bulk_data)
	doc.shift = shift_type
	doc.shift_determined_by = determined_by

	# 3. Check maternity benefit from bulk_data
	doc.maternity_benefit = check_maternity_benefit_from_bulk(doc.employee, doc.attendance_date, bulk_data)

	# 4. Set status based on check-in availability
	if check_in:
		doc.check_in = check_in
		doc.in_time = check_in.time()
		doc.status = "Present"
	else:
		doc.status = "Absent"
		doc.clear_all_fields()
		return

	# 5. Only proceed with full calculation if both check-in and check-out exist
	if not check_in or not check_out:
		doc.check_out = None
		doc.out_time = None
		doc.working_hours = 0
		doc.overtime_hours = 0
		doc.actual_overtime = 0
		doc.approved_overtime = 0
		doc.late_entry = False
		doc.early_exit = False
		doc.overtime_details_html = ""
		return

	doc.check_out = check_out
	doc.out_time = check_out.time()

	# 6. Get shift configuration
	shift_config = doc.get_shift_config(shift_type)
	if not shift_config:
		return

	# 7. Calculate working hours
	morning_hours = doc.calculate_morning_hours(check_in, check_out, shift_config)
	afternoon_hours = doc.calculate_afternoon_hours(check_in, check_out, shift_config, doc.maternity_benefit)

	total_working_hours = morning_hours + afternoon_hours

	if total_working_hours * 60 < MIN_MINUTES_WORKING_HOURS:
		total_working_hours = 0

	doc.working_hours = doc.decimal_round(total_working_hours)

	# 8. Calculate overtime from bulk_data
	actual_ot = calculate_actual_overtime_from_bulk(doc, check_in, check_out, shift_config, bulk_data)
	approved_ot = get_approved_overtime_from_bulk(doc.employee, doc.attendance_date, shift_type, bulk_data)
	final_ot = min(actual_ot, approved_ot) if shift_config.get("allows_ot") else 0

	doc.actual_overtime = doc.decimal_round(actual_ot)
	doc.approved_overtime = doc.decimal_round(approved_ot)
	doc.overtime_hours = doc.decimal_round(final_ot)

	# 8.5. Calculate overtime coefficient
	doc.overtime_coefficient = doc.calculate_overtime_coefficient()

	# 8.6. Special Sunday logic
	if isinstance(doc.attendance_date, str):
		date_obj = datetime.strptime(str(doc.attendance_date), '%Y-%m-%d')
	else:
		date_obj = doc.attendance_date

	if date_obj.weekday() == 6:  # Sunday
		# Get OT registrations from bulk_data
		key = (doc.employee, getdate(doc.attendance_date))
		ot_registrations = bulk_data["overtime_registrations"].get(key, [])

		# Apply Sunday logic (works with or without OT registration)
		apply_sunday_logic(doc, check_in, check_out, ot_registrations, shift_config)
	else:
		# 8.7. Calculate final OT with coefficient (normal days)
		doc.final_ot_with_coefficient = doc.decimal_round(doc.overtime_hours * doc.overtime_coefficient)

	# 9. Calculate late entry / early exit (skip for Sunday)
	if date_obj.weekday() != 6:
		try:
			late_early_result = doc.calculate_late_early(check_in, check_out, shift_config, doc.maternity_benefit)
			if isinstance(late_early_result, tuple) and len(late_early_result) == 2:
				late_entry_val, early_exit_val = late_early_result
				doc.late_entry = late_entry_val
				doc.early_exit = early_exit_val
			else:
				frappe.log_error(
					f"calculate_late_early returned unexpected type: {type(late_early_result)}, value: {late_early_result}",
					"Daily Timesheet Calculate Late/Early Error"
				)
				doc.late_entry = False
				doc.early_exit = False
		except Exception as e:
			frappe.log_error(
				f"Error unpacking late_early for {doc.employee} on {doc.attendance_date}: {str(e)}\nResult type: {type(late_early_result) if 'late_early_result' in locals() else 'not assigned'}",
				"Daily Timesheet Unpack Error"
			)
			doc.late_entry = False
			doc.early_exit = False
	else:
		doc.late_entry = False
		doc.early_exit = False

	# 10. Update status (skip for Sunday, already set by apply_sunday_logic)
	if date_obj.weekday() != 6:
		if doc.overtime_hours > 0:
			doc.status = "Present + OT"
		else:
			doc.status = "Present"

	# 11. Generate overtime details HTML
	doc.generate_overtime_details_html()

def get_employee_checkin_data_from_bulk(employee, attendance_date, bulk_data):
	"""Get check-in/out from pre-loaded bulk_data"""
	from frappe.utils import getdate
	from datetime import datetime

	key = (employee, getdate(attendance_date))
	checkins = bulk_data["checkins"].get(key, [])

	if not checkins:
		return None, None

	# Filter out duplicate/invalid checkins
	filtered_checkins = []
	for i, checkin in enumerate(checkins):
		if i == 0:
			filtered_checkins.append(checkin)
		else:
			time_diff = (checkin.check_time - checkins[i-1].check_time).total_seconds() / 60
			if time_diff >= MIN_MINUTES_CHECKIN_FILTER:
				filtered_checkins.append(checkin)

	check_in = None
	check_out = None

	# Handle explicit log_type
	in_checkins = [c for c in filtered_checkins if c.log_type == "IN"]
	out_checkins = [c for c in filtered_checkins if c.log_type == "OUT"]

	if in_checkins:
		check_in = in_checkins[0].check_time
	if out_checkins:
		check_out = out_checkins[-1].check_time

	# Fallback logic
	if not check_in and not check_out and filtered_checkins:
		if len(filtered_checkins) == 1:
			check_in = filtered_checkins[0].check_time
		elif len(filtered_checkins) >= 2:
			if not check_in:
				check_in = filtered_checkins[0].check_time
			if not check_out:
				check_out = filtered_checkins[-1].check_time

	return check_in, check_out

def get_shift_type_from_bulk(employee, attendance_date, bulk_data):
	"""Get shift type from pre-loaded bulk_data"""
	from frappe.utils import getdate
	from datetime import datetime

	# Check Sunday first
	if isinstance(attendance_date, str):
		date_obj = datetime.strptime(str(attendance_date), '%Y-%m-%d')
	else:
		date_obj = attendance_date

	if date_obj.weekday() == 6:
		return "Day", "Default Day Shift For Sunday"

	# Check shift registration
	shift_regs = bulk_data["shift_registrations"].get(employee, [])
	attendance_date = getdate(attendance_date)

	for reg in shift_regs:
		if reg.begin_date <= attendance_date <= reg.end_date:
			return reg.shift, "Registration"

	# Check employee group
	emp_group = bulk_data["employee_groups"].get(employee)
	if emp_group == "Canteen":
		return "Canteen", "Employee Group"

	return "Day", "Default"

def check_maternity_benefit_from_bulk(employee, attendance_date, bulk_data):
	"""Check maternity benefit from pre-loaded bulk_data"""
	from frappe.utils import getdate

	maternity_records = bulk_data["maternity_tracking"].get(employee, [])
	attendance_date = getdate(attendance_date)

	for record in maternity_records:
		if record.from_date <= attendance_date <= record.to_date:
			record_type_lower = record.type.lower() if record.type else ""
			if (record_type_lower == 'young child' or record.type in ['Young Child', 'Maternity Leave']):
				return True
			elif record.type == 'Pregnant':
				if record.apply_pregnant_benefit == 1:
					return True

	return False

def get_approved_overtime_from_bulk(employee, attendance_date, shift_type, bulk_data):
	"""Get approved overtime from pre-loaded bulk_data"""
	from frappe.utils import getdate, flt

	if shift_type in ["Shift 1", "Shift 2"]:
		return 0

	key = (employee, getdate(attendance_date))
	ot_records = bulk_data["overtime_registrations"].get(key, [])

	total_hours = 0
	for ot in ot_records:
		# Calculate hours from begin_time to end_time
		if ot.begin_time and ot.end_time:
			# Convert time to datetime for calculation
			from datetime import datetime, time as dt_time
			date = getdate(attendance_date)

			begin_dt = datetime.combine(date, ot.begin_time)
			end_dt = datetime.combine(date, ot.end_time)

			hours_diff = (end_dt - begin_dt).total_seconds() / 3600
			total_hours += hours_diff

	return flt(total_hours)

def calculate_actual_overtime_from_bulk(doc, check_in, check_out, shift_config, bulk_data):
	"""Calculate actual overtime using pre-loaded bulk_data"""
	from frappe.utils import time_diff_in_hours, getdate
	from datetime import datetime, timedelta

	if not check_in or not check_out:
		return 0

	shift_start = datetime.combine(check_in.date(), shift_config["start"])
	shift_end = datetime.combine(check_in.date(), shift_config["end"])
	break_start = datetime.combine(check_in.date(), shift_config["break_start"])
	break_end = datetime.combine(check_in.date(), shift_config["break_end"])

	# Pre-shift OT
	pre_shift_ot = 0
	if check_in < shift_start:
		has_pre_shift_registration = check_pre_shift_ot_registration_from_bulk(
			doc.employee, doc.attendance_date, check_in.time(), shift_start.time(), bulk_data
		)
		if has_pre_shift_registration:
			pre_shift_ot = time_diff_in_hours(shift_start, check_in)
			if pre_shift_ot * 60 < MIN_MINUTES_PRE_SHIFT_OT:
				pre_shift_ot = 0

	# Lunch break OT
	lunch_break_ot = 0
	if shift_config["break_start"] != shift_config["break_end"]:
		if (check_in < break_start and check_out > break_end and
			check_lunch_break_ot_registration_from_bulk(
				doc.employee, doc.attendance_date, break_start.time(), break_end.time(), bulk_data
			)):
			lunch_break_ot = time_diff_in_hours(break_end, break_start)
			if lunch_break_ot * 60 < MIN_MINUTES_OT:
				lunch_break_ot = 0

	# Post-shift OT
	post_shift_ot = 0
	expected_end = shift_end
	if doc.maternity_benefit:
		expected_end = shift_end - timedelta(hours=1)

	if check_out > expected_end:
		post_shift_ot = time_diff_in_hours(check_out, expected_end)
		if post_shift_ot < 0.25:
			post_shift_ot = 0

	total_ot = pre_shift_ot + lunch_break_ot + post_shift_ot

	if total_ot * 60 < MIN_MINUTES_OT:
		total_ot = 0

	return total_ot

def check_pre_shift_ot_registration_from_bulk(employee, attendance_date, check_in_time, shift_start_time, bulk_data):
	"""Check pre-shift OT registration from bulk_data"""
	from frappe.utils import getdate

	key = (employee, getdate(attendance_date))
	ot_records = bulk_data["overtime_registrations"].get(key, [])

	for ot in ot_records:
		if ot.begin_time <= shift_start_time and ot.end_time >= check_in_time:
			return True

	return False

def check_lunch_break_ot_registration_from_bulk(employee, attendance_date, break_start_time, break_end_time, bulk_data):
	"""Check lunch break OT registration from bulk_data"""
	from frappe.utils import getdate

	key = (employee, getdate(attendance_date))
	ot_records = bulk_data["overtime_registrations"].get(key, [])

	for ot in ot_records:
		# Check if OT registration overlaps with lunch break
		if ot.begin_time <= break_end_time and ot.end_time >= break_start_time:
			return True

	return False

@frappe.whitelist()
def bulk_recalculate_hybrid(employee=None, date_range=None, batch_size=100):
	"""Optimized bulk recalculation with smart batching and progress updates"""
	import time
	start_time = time.time()
	
	# Convert batch_size to int (comes as string from frontend)
	batch_size = int(batch_size) if batch_size else 100
	batch_size = min(batch_size, 200)  # Cap at 200 for safety
	
	# Build filters
	filters = []
	if employee:
		filters.append(f"employee = '{employee}'")
	
	if date_range:
		date_range = json.loads(date_range)
		if date_range.get("from_date"):
			filters.append(f"attendance_date >= '{date_range['from_date']}'")
		if date_range.get("to_date"):
			filters.append(f"attendance_date <= '{date_range['to_date']}'")
	
	where_clause = " AND ".join(filters) if filters else "1=1"
	
	# Get total count for progress tracking
	total_count = frappe.db.sql(f"""
		SELECT COUNT(*) as count FROM `tabDaily Timesheet` 
		WHERE {where_clause}
	""", as_dict=1)[0].count
	
	if total_count == 0:
		return {"success": True, "processed": 0, "message": "No records found to process"}
	
	# Process in batches
	processed = 0
	error_count = 0

	for offset in range(0, total_count, batch_size):
		# Get batch of records
		batch_records = frappe.db.sql(f"""
			SELECT name, employee, attendance_date
			FROM `tabDaily Timesheet` 
			WHERE {where_clause}
			ORDER BY attendance_date DESC, employee
			LIMIT {batch_size} OFFSET {offset}
		""", as_dict=1)
		
		# Process batch within transaction
		batch_processed = 0
		batch_errors = 0
		
		try:
			# Process each record in the batch
			for record in batch_records:
				try:
					doc = frappe.get_doc("Daily Timesheet", record.name)
					doc.calculate_all_fields()
					doc.save()
					batch_processed += 1
				except Exception as e:
					frappe.log_error(f"Error recalculating {record.name}: {str(e)}")
					batch_errors += 1
					continue
			
			# Commit batch
			frappe.db.commit()
			processed += batch_processed
			error_count += batch_errors

		except Exception as e:
			# Rollback batch on error
			frappe.db.rollback()
			frappe.log_error(f"Batch processing error (offset {offset}): {str(e)}")
			error_count += len(batch_records)
	
	# Final results
	end_time = time.time()
	processing_time = round(end_time - start_time, 2)
	
	result = {
		"success": True,
		"processed": processed,
		"errors": error_count,
		"total": total_count,
		"processing_time": processing_time,
		"records_per_second": round(processed / processing_time, 2) if processing_time > 0 else 0
	}
	
	message = f"Successfully processed {processed}/{total_count} records in {processing_time}s"
	if error_count > 0:
		message += f" ({error_count} errors logged)"
	
	frappe.msgprint(message)
	return result

# SMART BACKGROUND PROCESSING - PREVENTS TIMEOUTS FOR LARGE OPERATIONS

@frappe.whitelist()
def bulk_recalculate_smart(employee=None, date_range=None, batch_size=100):
	"""Smart bulk recalculation - auto-detects if operation should run in background"""
	import time
	
	# Convert batch_size to int
	batch_size = int(batch_size) if batch_size else 100
	batch_size = min(batch_size, 200)
	
	# Build filters to check total count
	filters = []
	if employee:
		filters.append(f"employee = '{employee}'")
	
	if date_range:
		date_range_parsed = json.loads(date_range)
		if date_range_parsed.get("from_date"):
			filters.append(f"attendance_date >= '{date_range_parsed['from_date']}'")
		if date_range_parsed.get("to_date"):
			filters.append(f"attendance_date <= '{date_range_parsed['to_date']}'")
	
	where_clause = " AND ".join(filters) if filters else "1=1"
	
	# Get total count
	total_count = frappe.db.sql(f"""
		SELECT COUNT(*) as count FROM `tabDaily Timesheet` 
		WHERE {where_clause}
	""", as_dict=1)[0].count
	
	# If operation is large (>300 records), run in background to prevent timeout
	if total_count > 300:
		job_id = f"bulk_recalc_{int(time.time())}"
		
		frappe.enqueue(
			'customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.bulk_recalculate_job',
			queue='default',
			timeout=1800,  # 30 minutes
			job_id=job_id,
			employee=employee,
			date_range=date_range,
			batch_size=batch_size,
			total_count=total_count
		)
		
		return {
			"success": True, 
			"background_job": True,
			"job_id": job_id,
			"total_count": total_count,
			"message": f"Large operation ({total_count} records) queued for background processing"
		}
	else:
		# Small operation, run synchronously with hybrid approach
		return bulk_recalculate_hybrid(employee, date_range, batch_size)

def bulk_recalculate_job(employee=None, date_range=None, batch_size=100, total_count=0):
	"""Background job for bulk recalculation"""
	try:
		frappe.publish_progress(0, title="Starting background recalculation...", 
							  description=f"Processing {total_count} records in background")
		
		result = bulk_recalculate_hybrid(employee, date_range, batch_size)
		
		frappe.publish_realtime(
			event='bulk_operation_complete',
			message={
				"operation": "recalculate",
				"success": True,
				"result": result,
				"message": f"Background recalculation completed: {result.get('processed', 0)} records processed"
			},
			user=frappe.session.user
		)
		
		return result
		
	except Exception as e:
		frappe.log_error(f"Background bulk recalculation failed: {str(e)}")
		frappe.publish_realtime(
			event='bulk_operation_complete',
			message={
				"operation": "recalculate", 
				"success": False,
				"error": str(e),
				"message": "Background recalculation failed"
			},
			user=frappe.session.user
		)
		raise e

@frappe.whitelist()
def bulk_create_recalculate_timesheet(from_date, to_date, employee=None, batch_size=100):
	"""Combined function: Create Daily Timesheet from checkins AND recalculate existing ones
	This replaces both create_from_checkins_smart and bulk_recalculate_smart
	"""
	import time
	from frappe.utils import getdate

	start_time = time.time()

	# Convert batch_size to int
	batch_size = int(batch_size) if batch_size else 100
	batch_size = min(batch_size, 200)  # MAX LIMIT for stability
	
	# Calculate total operations
	date_range_days = (getdate(to_date) - getdate(from_date)).days + 1
	
	# Get employee count estimate
	emp_conditions = ["emp.status = 'Active'"]
	filters = {}
	
	if employee:
		emp_conditions.append("emp.name = %(employee)s")
		filters["employee"] = employee
	
	active_employee_count = frappe.db.sql(f"""
		SELECT COUNT(*) as count
		FROM `tabEmployee` emp
		WHERE {' AND '.join(emp_conditions)}
	""", filters, as_dict=1)[0].count
	
	total_operations = active_employee_count * date_range_days
	
	# If operation is large (>500 operations), run in background to prevent timeout
	if total_operations > 500:
		job_id = f"bulk_create_recalc_{int(time.time())}"
		
		frappe.enqueue(
			'customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.bulk_create_recalculate_job',
			queue='default',
			timeout=1800,  # 30 minutes
			job_id=job_id,
			from_date=from_date,
			to_date=to_date,
			employee=employee,
			batch_size=batch_size,
			total_operations=total_operations
		)
		
		return {
			"success": True,
			"background_job": True, 
			"job_id": job_id,
			"total_operations": total_operations,
			"message": f"Large operation ({total_operations} operations) queued for background processing"
		}
	else:
		# Small operation, run synchronously with hybrid approach
		return bulk_create_recalculate_hybrid(from_date, to_date, employee, batch_size)

def bulk_create_recalculate_hybrid(from_date, to_date, employee=None, batch_size=100):
	"""OPTIMIZED: Bulk load all data first, then process with minimal queries"""
	import time
	from frappe.utils import getdate, add_days

	start_time = time.time()

	# Convert batch_size to int
	batch_size = int(batch_size) if batch_size else 100
	batch_size = min(batch_size, 200)  # MAX LIMIT for stability

	# Build employee conditions
	emp_conditions = ["emp.status = 'Active'"]
	filters = {
		"from_date": getdate(from_date),
		"to_date": getdate(to_date)
	}

	if employee:
		emp_conditions.append("emp.name = %(employee)s")
		filters["employee"] = employee

	# Get ALL active employees with date_of_joining
	active_employees = frappe.db.sql(f"""
		SELECT emp.name as employee, emp.employee_name, emp.department,
		       emp.custom_section, emp.custom_group, emp.company, emp.date_of_joining
		FROM `tabEmployee` emp
		WHERE {' AND '.join(emp_conditions)}
		ORDER BY emp.name
	""", filters, as_dict=1)

	if not active_employees:
		return {"success": True, "created": 0, "updated": 0, "message": "No active employees found"}

	# Calculate total operations
	date_range_days = (getdate(to_date) - getdate(from_date)).days + 1
	total_operations = len(active_employees) * date_range_days

	# ===== BULK DATA LOADING - QUERY ONCE =====
	employee_ids = [emp.employee for emp in active_employees]

	bulk_data = load_bulk_timesheet_data(employee_ids, from_date, to_date)

	# Process in batches by date
	created_count = 0
	updated_count = 0
	error_count = 0
	processed_operations = 0

	current_date = getdate(from_date)
	end_date = getdate(to_date)

	while current_date <= end_date:
		# Process employees in batches for this date
		for emp_offset in range(0, len(active_employees), batch_size):
			emp_batch = active_employees[emp_offset:emp_offset + batch_size]

			# Process batch within transaction
			batch_created = 0
			batch_updated = 0
			batch_errors = 0

			try:
				for emp_data in emp_batch:
					emp = emp_data.employee

					try:
						# Skip if attendance_date is before employee's joining date
						if emp_data.date_of_joining and getdate(current_date) < getdate(emp_data.date_of_joining):
							continue

						# Check if Daily Timesheet already exists
						existing_timesheet = frappe.db.exists("Daily Timesheet", {
							"employee": emp,
							"attendance_date": current_date
						})

						if existing_timesheet:
							# Update existing record - OPTIMIZED CALCULATION with pre-loaded data
							doc = frappe.get_doc("Daily Timesheet", existing_timesheet)
							calculate_all_fields_optimized(doc, bulk_data, skip_html_generation=True)
							doc.save()
							batch_updated += 1
						else:
							# Create new Daily Timesheet
							doc = frappe.get_doc({
								"doctype": "Daily Timesheet",
								"employee": emp,
								"employee_name": emp_data.employee_name,
								"attendance_date": current_date,
								"department": emp_data.department,
								"custom_section": emp_data.custom_section,
								"custom_group": emp_data.custom_group,
								"company": emp_data.company or frappe.defaults.get_user_default("Company")
							})

							calculate_all_fields_optimized(doc, bulk_data, skip_html_generation=True)
							doc.insert(ignore_permissions=True)
							batch_created += 1

					except Exception as e:
						frappe.log_error(f"Error processing timesheet for {emp} on {current_date}: {str(e)}")
						batch_errors += 1
						continue

				# Commit batch
				frappe.db.commit()
				created_count += batch_created
				updated_count += batch_updated
				error_count += batch_errors
				processed_operations += len(emp_batch)

			except Exception as e:
				# Rollback batch on error
				frappe.db.rollback()
				frappe.log_error(f"Batch processing error for date {current_date}: {str(e)}")
				error_count += len(emp_batch)
				processed_operations += len(emp_batch)

		current_date = add_days(current_date, 1)

	# Final results
	end_time = time.time()
	processing_time = round(end_time - start_time, 2)

	result = {
		"success": True,
		"created": created_count,
		"updated": updated_count,
		"errors": error_count,
		"total_operations": total_operations,
		"processing_time": processing_time,
		"records_per_second": round((created_count + updated_count) / processing_time, 2) if processing_time > 0 else 0
	}

	message = f"Processed {len(active_employees)} employees. Created {created_count}, Updated {updated_count} in {processing_time}s (OPTIMIZED)"
	if error_count > 0:
		message += f" ({error_count} errors logged)"

	frappe.msgprint(message)
	return result

def bulk_create_recalculate_job(from_date, to_date, employee=None, batch_size=100, total_operations=0):
	"""Background job for combined bulk create + recalculate"""
	try:
		frappe.publish_progress(0, title="Starting background create + recalculate...",
							  description=f"Processing {total_operations} operations in background")
		
		result = bulk_create_recalculate_hybrid(from_date, to_date, employee, batch_size)
		
		frappe.publish_realtime(
			event='bulk_operation_complete',
			message={
				"operation": "create_recalculate",
				"success": True,
				"result": result,
				"message": f"Background create + recalculate completed: {result.get('created', 0)} created, {result.get('updated', 0)} updated"
			},
			user=frappe.session.user
		)
		
		return result
		
	except Exception as e:
		frappe.log_error(f"Background bulk create + recalculate failed: {str(e)}")
		frappe.publish_realtime(
			event='bulk_operation_complete',
			message={
				"operation": "create_recalculate",
				"success": False,
				"error": str(e),
				"message": "Background create + recalculate failed"
			},
			user=frappe.session.user
		)
		raise e

@frappe.whitelist()
def debug_timesheet_calculation(docname):
	"""Debug function to verify timesheet calculation logic"""
	from datetime import datetime, time
	
	try:
		doc = frappe.get_doc('Daily Timesheet', docname)
		print(f'=== Daily Timesheet Debug: {docname} ===')
		print(f'Employee: {doc.employee} - {doc.employee_name}')
		print(f'Attendance Date: {doc.attendance_date}')
		print(f'Check In: {doc.check_in}')
		print(f'Check Out: {doc.check_out}')
		print(f'Working Hours: {doc.working_hours}')
		print(f'Actual Overtime: {doc.actual_overtime}')
		print(f'Approved Overtime: {doc.approved_overtime}')
		print(f'Final Overtime: {doc.overtime_hours}')
		print(f'Shift: {doc.shift}')
		
		# Get employee checkin data
		checkins = frappe.db.sql('''
			SELECT time, log_type, device_id, custom_reason_for_manual_check_in
			FROM `tabEmployee Checkin` 
			WHERE employee = %s AND DATE(time) = %s 
			ORDER BY time
		''', (doc.employee, doc.attendance_date), as_dict=1)
		
		print('\n=== Employee Checkins ===')
		for checkin in checkins:
			reason = checkin.custom_reason_for_manual_check_in or 'N/A'
			device = checkin.device_id or 'Manual'
			print(f'{checkin.time} | {checkin.log_type} | Device: {device} | Reason: {reason}')
		
		# Manual calculation verification
		if checkins and len(checkins) >= 2:
			# Filter checkins based on MIN_MINUTES_CHECKIN_FILTER
			filtered_checkins = []
			for checkin in checkins:
				if not filtered_checkins:
					filtered_checkins.append(checkin)
				else:
					time_diff_minutes = time_diff_in_hours(checkin.time, filtered_checkins[-1].time) * 60
					if time_diff_minutes >= MIN_MINUTES_CHECKIN_FILTER:
						filtered_checkins.append(checkin)
			
			if len(filtered_checkins) >= 2:
				check_in_time = min([c.time for c in filtered_checkins])
				check_out_time = max([c.time for c in filtered_checkins])
				
				print(f'\n=== Manual Verification ===')
				print(f'Filtered Checkins Count: {len(filtered_checkins)} (original: {len(checkins)})')
				print(f'Earliest Check In: {check_in_time}')
				print(f'Latest Check Out: {check_out_time}')
				
				# Calculate overtime based on shift
				shift_type = doc.shift or "Day"
				
				if shift_type == "Day":
					shift_start = datetime.combine(doc.attendance_date, time(8, 0))
					shift_end = datetime.combine(doc.attendance_date, time(17, 0))
				elif shift_type == "Canteen":
					shift_start = datetime.combine(doc.attendance_date, time(7, 0))
					shift_end = datetime.combine(doc.attendance_date, time(16, 0))
				else:
					# Shift 1/2 don't have OT
					print(f'Shift {shift_type} - No overtime allowed')
					return
				
				print(f'Shift: {shift_type} ({shift_start.time()} - {shift_end.time()})')
				
				# Calculate pre-shift OT
				pre_shift_ot = 0
				if check_in_time < shift_start:
					pre_shift_ot = time_diff_in_hours(shift_start, check_in_time)
					print(f'Pre-shift OT: {pre_shift_ot:.2f} hours ({pre_shift_ot*60:.0f} minutes)')
					
					# Apply MIN_MINUTES_PRE_SHIFT_OT threshold
					if pre_shift_ot * 60 < MIN_MINUTES_PRE_SHIFT_OT:
						pre_shift_ot = 0
						print(f'Pre-shift OT < {MIN_MINUTES_PRE_SHIFT_OT} minutes → Set to 0')
				
				# Calculate post-shift OT
				post_shift_ot = 0
				if check_out_time > shift_end:
					post_shift_ot = time_diff_in_hours(check_out_time, shift_end)
					print(f'Post-shift OT: {post_shift_ot:.2f} hours ({post_shift_ot*60:.0f} minutes)')
				
				# Total actual OT
				total_actual_ot = pre_shift_ot + post_shift_ot
				print(f'Total Actual OT: {total_actual_ot:.2f} hours ({total_actual_ot*60:.0f} minutes)')
				
				# Apply MIN_MINUTES_OT threshold
				if total_actual_ot * 60 < MIN_MINUTES_OT:
					final_actual_ot = 0
					print(f'Total OT ({total_actual_ot*60:.0f} min) < MIN_MINUTES_OT ({MIN_MINUTES_OT} min) → Set to 0')
				else:
					final_actual_ot = total_actual_ot
					print(f'Total OT ({total_actual_ot*60:.0f} min) >= MIN_MINUTES_OT ({MIN_MINUTES_OT} min) → Valid')
				
				print(f'\n=== Comparison ===')
				print(f'Expected Actual OT: {final_actual_ot:.2f}h vs Current: {doc.actual_overtime}h')
				
				# Check if they match (within 0.01 tolerance)
				if abs(final_actual_ot - doc.actual_overtime) < 0.01:
					print('✅ ALGORITHM IS CORRECT')
					return True
				else:
					print('❌ ALGORITHM MISMATCH - Needs investigation')
					return False
			else:
				print('Not enough filtered checkins for calculation')
		else:
			print('Not enough checkin records for calculation')
			
	except Exception as e:
		print(f'Error: {e}')
		import traceback
		traceback.print_exc()
		return False


@frappe.whitelist()
def get_overtime_registrations(employee, attendance_date):
	"""
	Get Overtime Registration documents for a specific employee and date
	Returns list of parent document names
	"""
	if not employee or not attendance_date:
		return []

	# Query child table to get parent documents
	parents = frappe.db.sql("""
		SELECT DISTINCT parent
		FROM `tabOvertime Registration Detail`
		WHERE employee = %s
		AND date = %s
		AND parenttype = 'Overtime Registration'
	""", (employee, attendance_date), as_dict=1)

	if not parents:
		return []

	# Return list of parent names
	return [p.parent for p in parents]
