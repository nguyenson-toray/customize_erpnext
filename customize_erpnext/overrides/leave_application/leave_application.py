"""Leave Application overrides cho TIQN.

Căn cứ nghiệp vụ: `QUY_DINH_NGHI_PHEP_2025.md`. Mọi **quyết định** (mã viết tắt,
`half_day_status`, loại nghỉ nào vào `Attendance.leave_type`) đặt ở `overrides/leave_rules.py`
vì engine tính công (`overrides/shift_type/shift_type_optimized.py`) ghi vào **cùng các field
đó và luôn ghi sau cùng** — hai luồng lệch nhau thì mỗi FULL run lại ghi đè lẫn nhau.

Override so với HRMS gốc:

1. `validate_attendance()` — HRMS block MỌI attendance `Present`/`Work From Home`.
   Ở đây chỉ block Full Day leave khi ngày đó đã làm đủ giờ
   (`Attendance Calculation Setting.full_day_leave_block_hours`).

2. `create_or_update_attendance()` — thêm trạng thái `Present` khi Full Day leave rơi vào ngày
   đã có checkin, và hỗ trợ hai đơn nửa ngày cùng ngày (`custom_leave_type_2`).

   | Đơn nghỉ  | Có checkin   | status     |
   |-----------|--------------|------------|
   | Half Day  | bất kỳ       | `Half Day` |
   | Full Day  | có (wh > 0)  | `Present`  |
   | Full Day  | không        | `On Leave` |

3. `on_leave_application_cancel()` — cancel đúng khi ngày đó có hai đơn.

4. `CustomLeaveApplication.cancel_attendance()` — batch SQL thay cho vòng lặp per-record của
   HRMS, tránh timeout với đơn dài ngày (thai sản ~180 ngày).

   ⚠ Giá trị còn lại của override này **chỉ là** tránh timeout và tránh `LinkExistsError` của
   `check_no_back_links_exist()`. Việc tính lại Attendance sau khi cancel **không** do đây lo:
   engine bước 2b tự xoá attendance trong giai đoạn Maternity Leave (Employee Maternity là
   source of truth), và setting `recalc_attendance_on_maternity_change` **mặc định TẮT** — nên
   thực tế không có gì recalc cho tới FULL run kế tiếp.
"""

import frappe
from frappe import _
from frappe.utils import getdate, formatdate, get_link_to_form
from hrms.hr.doctype.leave_application.leave_application import LeaveApplication


# =============================================================================
# CONFIGURATION
# =============================================================================

# Số giờ làm việc tối thiểu để block Full Day leave lấy từ
# Attendance Calculation Setting (full_day_leave_block_hours, mặc định 8)
from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
	get_attendance_settings
)


# =============================================================================
# OVERRIDE: validate_attendance
# =============================================================================

def custom_validate_attendance(self):
	"""
	Override validate_attendance để cho phép leave trong hầu hết trường hợp.
	Chỉ chạy khi status = Approved và docstatus = 1 (submitted).

	HRMS gốc (leave_application.py:602-629):
	- Block TẤT CẢ attendance có status "Present" hoặc "Work From Home"

	Override:
	- CHỈ block khi: Full Day leave AND working_hours >= 8
	- Các trường hợp khác đều cho phép:
	  - Half Day leave: luôn cho phép
	  - Full Day leave với working_hours < 8: cho phép
	"""
	# Chỉ validate khi Approved & submitted
	if self.status != "Approved" or self.docstatus != 1:
		return

	from hrms.hr.doctype.leave_application.leave_application import AttendanceAlreadyMarkedError

	# Query attendance
	# NOTE: không filter half_day_status trong SQL — điều kiện `!=` của SQL loại
	# luôn record NULL (Present luôn có half_day_status NULL) khiến toàn bộ
	# validate thành no-op. Lọc "Absent" trong Python bên dưới.
	attendance_records = frappe.get_all(
		"Attendance",
		filters=[
			["employee", "=", self.employee],
			["attendance_date", "between", [self.from_date, self.to_date]],
			["status", "in", ["Present", "Work From Home"]],
			["docstatus", "=", 1],
		],
		fields=[
			"name", "attendance_date", "working_hours", "half_day_status",
			"actual_overtime_duration",
		],
		order_by="attendance_date",
	)

	if not attendance_records:
		return  # Không có attendance, tiếp tục

	blocking_attendance = []
	allowed_attendance = []
	full_day_block_hours = frappe.utils.flt(get_attendance_settings().full_day_leave_block_hours)

	for att in attendance_records:
		# Nửa ngày còn lại vắng mặt → không tính là ngày làm việc đầy đủ
		if att.half_day_status == "Absent":
			continue

		attendance_date = att.attendance_date
		# Ngày Chủ Nhật / ngày lễ: engine §8 reset working_hours = 0 và dồn toàn bộ giờ sang
		# actual_overtime_duration. Chỉ đọc working_hours thì đơn nghỉ nguyên ngày LỌT QUA
		# validate và đè lên một ngày đã đi làm 8-10 tiếng.
		working_hours = max(
			frappe.utils.flt(att.working_hours), frappe.utils.flt(att.actual_overtime_duration)
		)

		# Half Day leave: LUÔN cho phép
		if self.half_day:
			allowed_attendance.append({
				"date": attendance_date,
				"action": _("will be updated to Half Day")
			})
			continue

		# Full Day leave: chỉ block nếu working_hours >= threshold (setting)
		if working_hours >= full_day_block_hours:
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
				full_day_block_hours,
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
	Chỉ chạy khi status = Approved và docstatus = 1 (submitted).

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
	# Chỉ update attendance khi Approved & submitted
	if self.status != "Approved" or self.docstatus != 1:
		return

	from customize_erpnext.overrides.leave_rules import (
		combined_abbreviation,
		full_day_abbreviation,
		resolve_half_day_status,
	)
	from customize_erpnext.overrides.leave_utils import (
		find_other_half_day_leave_type,
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
		has_checkin = bool(doc.working_hours and doc.working_hours > 0)

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
					doc.leave_type,        # LA1 leave_type
					doc.leave_application, # LA1 name
					self.leave_type,       # LA2 leave_type
					self.name,             # LA2 name
					has_checkin=has_checkin,
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
			other = find_other_half_day_leave_type(self.employee, date, self.name)
			half_day_status = resolve_half_day_status(has_checkin, other)
			combined_abbr = combined_abbreviation(self.leave_type, other)
		else:
			status = "Present" if has_checkin else "On Leave"
			half_day_status = None
			combined_abbr = full_day_abbreviation(self.leave_type)

		# Update. Không ghi `modify_half_day_status`: HRMS chỉ ĐỌC field này ở
		# get_duplicate_attendance_record() (attendance.py:99), engine luôn ghi 0, và nó nằm
		# trong danh sách compare của engine → ghi khác 0 làm mỗi FULL run update lại vô ích.
		doc.db_set({
			"status": status,
			"leave_type": self.leave_type,
			"leave_application": self.name,
			"custom_leave_application_abbreviation": combined_abbr,
			"half_day_status": half_day_status,
		})

	else:
		# Make new attendance - không có check in
		# Half Day → "Half Day", Full Day → "On Leave"
		if is_half_day_for_this_date:
			status = "Half Day"
			other = find_other_half_day_leave_type(self.employee, date, self.name)
			# has_checkin=False: không có Attendance nào cho ngày này nên chắc chắn chưa quẹt thẻ
			half_day_status = resolve_half_day_status(False, other)
			combined_abbr = combined_abbreviation(self.leave_type, other)
		else:
			status = "On Leave"
			half_day_status = None
			combined_abbr = full_day_abbreviation(self.leave_type)

		doc = frappe.new_doc("Attendance")
		doc.employee = self.employee
		doc.employee_name = self.employee_name
		doc.attendance_date = date
		doc.company = self.company
		doc.leave_type = self.leave_type
		doc.leave_application = self.name
		doc.status = status
		doc.custom_leave_application_abbreviation = combined_abbr
		doc.half_day_status = half_day_status
		# ignore_validate là BẮT BUỘC: attendance.py:197-200 tự ép half_day_status = 'Absent'
		# khi HRMS không tự tìm thấy leave record, ghi đè giá trị vừa tính ở trên.
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
	from customize_erpnext.overrides.leave_rules import (
		combined_abbreviation,
		resolve_half_day_status,
	)
	from customize_erpnext.overrides.leave_utils import find_attendance_for_leave

	# Chỉ xử lý Half Day leaves
	if not doc.half_day or not doc.half_day_date:
		return

	existing_att = find_attendance_for_leave(doc.employee, doc.half_day_date)
	if not existing_att:
		return

	att_name = existing_att.name
	is_la1 = existing_att.leave_application == doc.name
	is_la2 = existing_att.custom_leave_application_2 == doc.name
	# Sau khi bỏ một đơn thì chỉ còn MỘT nửa là nghỉ phép; nửa còn lại được trả lương hay không
	# giờ phụ thuộc duy nhất vào việc hôm đó có đi làm — nên phải tính lại, không hardcode.
	has_checkin = bool(existing_att.working_hours and existing_att.working_hours > 0)

	if is_la1 and existing_att.custom_leave_application_2:
		# LA1 bị cancel, LA2 tồn tại → Swap LA2 → LA1
		new_lt1 = existing_att.custom_leave_type_2
		new_la1 = existing_att.custom_leave_application_2
		new_abbr = combined_abbreviation(new_lt1, None)

		frappe.db.set_value("Attendance", att_name, {
			"leave_type": new_lt1,
			"leave_application": new_la1,
			"custom_leave_type_2": None,
			"custom_leave_application_2": None,
			"custom_leave_application_abbreviation": new_abbr,
			"status": "Half Day",
			"half_day_status": resolve_half_day_status(has_checkin, None),
		})
		frappe.msgprint(
			_("Attendance {0}: swapped LA2 → LA1 ({1})").format(att_name, new_abbr),
			indicator="blue", alert=True
		)

	elif is_la2:
		# LA2 bị cancel → Remove LA2, giữ LA1
		new_abbr = combined_abbreviation(existing_att.leave_type, None)

		frappe.db.set_value("Attendance", att_name, {
			"custom_leave_type_2": None,
			"custom_leave_application_2": None,
			"custom_leave_application_abbreviation": new_abbr,
			"status": "Half Day",
			"half_day_status": resolve_half_day_status(has_checkin, None),
		})
		frappe.msgprint(
			_("Attendance {0}: removed LA2 ({1})").format(att_name, new_abbr),
			indicator="blue", alert=True
		)

	# Nếu is_la1 và không có LA2 → HRMS sẽ cancel attendance


# =============================================================================
# CLASS OVERRIDE: CustomLeaveApplication
# =============================================================================

class CustomLeaveApplication(LeaveApplication):
	"""
	Override LeaveApplication để fix timeout khi cancel leave dài ngày (thai sản ~6 tháng, v.v.)

	Vấn đề HRMS gốc: cancel_attendance() lặp từng record, gọi db.set_value() riêng lẻ
	(~180 lần cho 6 tháng) → timeout web request.

	Ngoài ra: skip cancel_attendance() không đủ vì Frappe's check_no_back_links_exist()
	(chạy sau on_cancel) throw LinkExistsError khi còn 180 submitted Attendance link tới LA.

	Fix: 1 SQL batch UPDATE thay cho loop — áp dụng cho mọi leave type.
	Maternity attendance recalc vẫn được xử lý qua Employee Maternity hooks khi EM được update/delete.
	"""

	def autoname(self):
		"""`LA-YYYY-MM-#####`, trong đó **YYYY-MM lấy từ `from_date`** của đơn.

		Vì sao phải viết tay thay vì đổi naming series: `.YYYY.` / `.MM.` của Frappe lấy theo
		**ngày hôm nay**, không lấy theo field. Đơn nghỉ tháng 8 nhập vào tháng 9 sẽ mang số
		tháng 9 — sai với cách HR tra cứu.

		Thứ tự trong `frappe/model/naming.py:set_new_name`: nhánh `amended_from` chạy TRƯỚC,
		rồi mới `doc.run_method("autoname")`, cuối cùng mới tới meta `naming_series:`. Nên hàm
		này thắng naming series, và bản sửa đổi (amend) vẫn được Frappe đặt tên `-1`, `-2`…
		như cũ — không cần xử lý riêng.

		Mỗi tháng một bộ đếm riêng (`LA-2026-08-`), bắt đầu từ 00001.

		⚠ **Chỉ áp cho đơn MỚI.** 7.097 đơn cũ giữ nguyên tên `HR-LAP-…`; đổi tên chúng sẽ phải
		cập nhật 16.009 tham chiếu (9.261 `Attendance.leave_application` + 6.748
		`Leave Ledger Entry.transaction_name`).
		"""
		from frappe.model.naming import make_autoname

		d = getdate(self.from_date or self.posting_date or frappe.utils.nowdate())
		self.name = make_autoname(f"LA-{d.year:04d}-{d.month:02d}-.#####")

	def cancel_attendance(self):
		"""Gỡ đơn nghỉ khỏi Attendance khi cancel — 2 câu SQL, không loop.

		HRMS gốc lặp từng bản ghi gọi `db.set_value()` (~180 lần với đơn thai sản 6 tháng)
		→ timeout web request. Chỉ skip cũng không được: `check_no_back_links_exist()` chạy
		sau `on_cancel` sẽ throw `LinkExistsError` khi còn Attendance submitted trỏ tới đơn.

		Hai nhóm bản ghi, hai cách xử lý khác nhau — chia theo **có giờ công hay không**,
		không chia theo `status`:

		  • `working_hours > 0` — người ta CÓ đi làm hôm đó (nghỉ nửa ngày làm nửa còn lại,
		    hoặc nghỉ nguyên ngày nhưng vẫn vào ca). Huỷ đơn nghỉ **không được xoá ngày công**
		    ⇒ GIỮ bản ghi, chỉ gỡ 5 field đơn nghỉ. Giữ luôn document name và link
		    `Employee Checkin.attendance` — cancel rồi tạo lại sẽ phải nối lại toàn bộ checkin.
		  • `working_hours = 0` — không có gì để giữ ⇒ cancel bản ghi như HRMS.

		Khác HRMS gốc điểm nữa: CHỈ đụng attendance thuộc chính đơn này (hoặc không link đơn
		nào — dữ liệu cũ). Bắt buộc với dual leave: hook `before_cancel` đã swap LA2→LA1 trước
		đó, bản ghi sau swap có `leave_application` = LA2 ≠ đơn đang cancel nên phải sống sót.

		`status` của nhóm giữ lại chưa đúng ngay: nó vẫn là 'Half Day'/'Present' tính theo đơn
		vừa gỡ. Engine tính lại mới ra đúng — xem `_queue_recalc_after_cancel()`.
		"""
		from frappe.utils import now

		if self.docstatus != 2:
			return

		args = (now(), frappe.session.user, self.employee, self.from_date, self.to_date, self.name)

		# 1. Có giờ công → giữ bản ghi, gỡ dấu vết đơn nghỉ.
		#    half_day_status = NULL vì không còn nửa ngày nghỉ nào để mô tả.
		frappe.db.sql("""
			UPDATE `tabAttendance`
			SET leave_type = NULL,
			    leave_application = NULL,
			    custom_leave_application_abbreviation = NULL,
			    custom_leave_type_2 = NULL,
			    custom_leave_application_2 = NULL,
			    half_day_status = NULL,
			    modified = %s, modified_by = %s
			WHERE employee = %s
			  AND attendance_date BETWEEN %s AND %s
			  AND docstatus < 2
			  AND IFNULL(working_hours, 0) > 0
			  AND leave_application = %s
		""", args)

		# 2. Không có giờ công → cancel như HRMS.
		frappe.db.sql("""
			UPDATE `tabAttendance`
			SET docstatus = 2, modified = %s, modified_by = %s
			WHERE employee = %s
			  AND attendance_date BETWEEN %s AND %s
			  AND docstatus < 2
			  AND IFNULL(working_hours, 0) = 0
			  AND status IN ('On Leave', 'Half Day')
			  AND (leave_application IS NULL OR leave_application = %s)
		""", args)

		self._queue_recalc_after_cancel()

	def _queue_recalc_after_cancel(self):
		"""Đẩy job tính lại attendance cho đúng khoảng ngày của đơn vừa cancel.

		Gated bởi `Attendance Calculation Setting` → **Recalc Attendance on Leave Application
		Cancel** (mặc định TẮT). Tắt thì attendance đúng lại ở FULL run kế tiếp (giờ 8 và 23)
		hoặc Bulk Update thủ công — cùng quy ước với 3 cờ recalc còn lại.

		Cần thiết vì bản ghi được GIỮ ở nhóm 1 vẫn mang `status` tính theo đơn vừa gỡ; chỉ
		engine mới tính lại được 'Present'/'Half Day'/'Absent' từ giờ công thật.
		"""
		try:
			from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
				get_attendance_settings,
			)

			if not frappe.utils.cint(
				get_attendance_settings().recalc_attendance_on_leave_application_cancel
			):
				return

			frappe.enqueue(
				"customize_erpnext.overrides.leave_application.leave_application."
				"background_recalculate_attendance_for_leave_cancel",
				queue="long",
				timeout=1800,
				job_id=f"leave_cancel_attendance_{self.name}_"
				       f"{int(frappe.utils.now_datetime().timestamp())}",
				# Job chỉ vào queue sau khi transaction commit — tránh worker đọc phải
				# trạng thái cũ khi đơn chưa thực sự được ghi docstatus = 2
				enqueue_after_commit=True,
				employee=self.employee,
				from_date=str(self.from_date),
				to_date=str(self.to_date),
				leave_application=self.name,
			)
		except Exception:
			# Không được để lỗi enqueue chặn việc cancel đơn
			frappe.log_error(
				frappe.get_traceback(), "Leave cancel: queue attendance recalc failed"
			)


def background_recalculate_attendance_for_leave_cancel(
	employee, from_date, to_date, leave_application=None
):
	"""Background job: tính lại attendance cho khoảng ngày của đơn nghỉ vừa cancel.

	Chỉ chạy những ngày <= hôm nay (ngày tương lai chưa có gì để tính) và bỏ qua khung giờ
	cao điểm quét vân tay — cùng quy ước với job recalc của Employee Maternity.
	"""
	from datetime import date as _date

	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		is_peak_time,
	)
	from customize_erpnext.overrides.shift_type.shift_type_optimized import (
		_core_process_attendance_logic_optimized,
	)

	if is_peak_time():
		frappe.logger().info(
			f"[LeaveCancel] Peak time — bỏ qua recalc cho {employee} ({leave_application})"
		)
		return

	today = _date.today()
	start, end = getdate(from_date), getdate(to_date)
	days = []
	while start <= end:
		if start <= today:
			days.append(start)
		start = frappe.utils.add_days(start, 1)

	if not days:
		frappe.logger().info(f"[LeaveCancel] {employee}: không có ngày quá khứ — bỏ qua.")
		return

	frappe.logger().info(
		f"[LeaveCancel] Bắt đầu — {employee}: {len(days)} ngày ({from_date} → {to_date}), "
		f"đơn {leave_application}"
	)
	_core_process_attendance_logic_optimized(
		employees=[employee],
		days=days,
		from_date=str(days[0]),
		to_date=str(days[-1]),
		fore_get_logs=True,
	)
	frappe.db.commit()
	frappe.logger().info(f"[LeaveCancel] Xong — {employee}: {len(days)} ngày.")



print("✅ Leave Application overrides loaded")
