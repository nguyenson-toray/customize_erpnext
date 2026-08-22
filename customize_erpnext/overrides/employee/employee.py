# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

# NOTE: Maternity tracking functions have been moved to Employee Maternity doctype.
# See: customize_erpnext/customize_erpnext/doctype/employee_maternity/employee_maternity.py
# Old functions removed:
#   - check_maternity_tracking_changes_for_attendance()
#   - auto_update_attendance_on_maternity_change()
#   - background_update_attendance_for_maternity()

import frappe
from frappe.utils import getdate

from customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract import business_today


@frappe.whitelist()
def auto_mark_employees_as_left():
	"""Job 00:00 — đổi `Employee.status` sang `Left` khi đã tới ngày nghỉ.

	Đây là **bước thứ hai** của luồng nghỉ việc. `Resignation Application` khi được duyệt chỉ ghi
	`relieving_date` + lý do; job này mới đổi status, đúng vào ngày người ta thật sự nghỉ. Xem
	`doctype/resignation_application/resignation_application.py` để biết vì sao phải tách hai bước.

	Vẫn chạy độc lập với đơn: HR nhập tay `relieving_date` trên Employee thì job này vẫn xử lý.

	## Ba lỗi của bản trước (sửa 21/08/2026)

	1. **Thiếu điều kiện `status = 'Active'`.** Docstring viết "from Active to Left" nhưng bộ lọc
	   chỉ có `relieving_date <= today`. Đo trên site: 1.388 nhân viên khớp và **cả 1.388 đã là
	   `Left`** -> mỗi đêm chạy 1.388 câu UPDATE vô ích, kèm `update_modified=True` nên **bump
	   `modified` của 1.388 Employee mỗi đêm**: hỏng mọi thứ đọc theo `modified` (đồng bộ MongoDB,
	   "sửa gần đây") và xoá cache vô cớ. Nặng hơn: HR mở lại một người thành `Active` mà
	   `relieving_date` còn đó thì đêm sau bị ép `Left` trở lại, **im lặng**.
	2. **`frappe.utils.today()`.** Job chạy đúng 00:00, mà `System Settings.time_zone` trên site
	   này nhiều lần tự nhảy về `Asia/Kolkata` (UTC+5:30) trong khi DB chạy giờ địa phương
	   (UTC+7) -> `today()` lệch một ngày so với `CURDATE()` **đúng trong khung 00:00-01:30**.
	   `business_today()` đọc CURDATE() từ chính DB.
	3. **Bỏ qua hai việc mà `validate_status` của core làm.** Core chặn khi còn nhân viên `Active`
	   đang `reports_to` người này (`erpnext/setup/doctype/employee/employee.py:274`), và
	   `update_user_status` khoá tài khoản User. Nghỉ việc thì đúng là phải làm cả hai.

	## Vì sao KHÔNG dùng `doc.save()`

	Đường hiển nhiên là `doc.save()` để core tự chạy hết validate. **Đã thử và phải bỏ**: save
	một Employee là validate lại toàn bộ ~200 field, kể cả dữ liệu cũ nhập từ nhiều năm trước.
	Đo trên site: **796 nhân viên Active** mang `custom_driving_license = '0'` trong khi options
	của field là `"", "Có", "Không"` -> mọi `save()` đều throw

	    Driving License cannot be "0". It should be one of "", "Có", "Không"

	Tức là job sẽ **im lặng bỏ sót phần lớn người nghỉ việc**, chỉ để lại Error Log mà không ai
	đọc. Một lá đơn nghỉ việc không phải là lúc bắt người ta dọn dữ liệu 5 năm trước.

	Nên: ghi đúng thứ cần ghi (`status`), cộng với **hai việc của core được gọi tường minh** —
	kiểm cấp dưới và khoá User. Được lợi ích của `save()` mà không kéo theo phần còn lại.
	"""
	as_on = getdate(business_today())

	employees = frappe.get_all(
		"Employee",
		filters=[
			["status", "=", "Active"],
			["relieving_date", "is", "set"],
			["relieving_date", "<=", as_on],
		],
		fields=["name", "employee_name", "relieving_date"],
	)

	if not employees:
		frappe.logger().info(f"[auto_mark_employees_as_left] {as_on}: không có ai tới hạn.")
		return {"as_on": str(as_on), "updated": [], "errors": []}

	updated, skipped, errors = [], [], []

	for i, emp in enumerate(employees):
		# ⚠ `savepoint` chứ không `commit()`/`rollback()` trần.
		#   · `commit()` trong thân một hàm `@frappe.whitelist()` là đường đã từng đẩy dữ liệu
		#     test ra production — commit để cho scheduler tự làm khi job kết thúc.
		#   · `rollback()` trần huỷ **cả lô** đang dở, tức một người lỗi sẽ xoá luôn kết quả của
		#     những người đã xử lý xong trước đó.
		sp = f"amel_{i}"
		frappe.db.savepoint(sp)
		try:
			result = mark_employee_left(emp.name)
			if not result["ok"]:
				skipped.append({"employee": emp.name, "reports_to_self": result["reports_to_self"]})
				continue
			updated.append(emp.name)
		except Exception as e:
			frappe.db.rollback(save_point=sp)
			errors.append({"employee": emp.name, "error": str(e)})
			frappe.log_error(
				title=f"[auto_mark_employees_as_left] {emp.name}",
				message=frappe.get_traceback(),
			)

	frappe.logger().info(
		f"[auto_mark_employees_as_left] {as_on}: {len(updated)} chuyển sang Left, "
		f"{len(skipped)} bỏ qua, {len(errors)} lỗi. {updated}"
	)
	if skipped:
		# Không phải lỗi kỹ thuật mà là việc HR phải xử lý: chuyển cấp dưới sang người khác.
		frappe.logger().warning(f"[auto_mark_employees_as_left] còn cấp dưới: {skipped}")
	if errors:
		frappe.logger().error(f"[auto_mark_employees_as_left] lỗi: {errors}")

	return {"as_on": str(as_on), "updated": updated, "skipped": skipped, "errors": errors}


def mark_employee_left(employee: str) -> dict:
	"""Chuyển một nhân viên sang `Left`: đổi status + khoá tài khoản User.

	Dùng chung cho **hai đường vào**, để hai bên không bao giờ làm khác nhau:
	  · job 00:00 ở trên — người tới ngày nghỉ
	  · `ResignationApplication.on_submit` — đơn nhập **lùi ngày**, ngày nghỉ đã qua hoặc là
	    hôm nay thì chuyển luôn, không bắt HR đợi tới nửa đêm

	Trả `{"ok": False, "reports_to_self": [...]}` khi còn cấp dưới `Active` — người gọi tự quyết
	định báo cho ai. Đây **không phải lỗi kỹ thuật** mà là việc HR phải xử lý (chuyển cấp dưới
	sang người quản lý khác), nên không throw và không ghi Error Log.
	"""
	if frappe.db.get_value("Employee", employee, "status") == "Left":
		# Đã đúng rồi thì đừng ghi lại: mỗi `set_value` là một lần bump `modified` + xoá cache.
		return {"ok": True, "reports_to_self": []}

	blocker = _active_subordinates(employee)
	if blocker:
		return {"ok": False, "reports_to_self": blocker}

	frappe.db.set_value("Employee", employee, "status", "Left")
	_disable_linked_user(employee)
	return {"ok": True, "reports_to_self": []}


def restore_employee_active(employee: str):
	"""Mở lại một nhân viên đã bị đánh `Left` — dùng khi **rút đơn** nghỉ việc.

	Mở khoá User luôn, đối xứng với `_disable_linked_user`. Sao lại hành vi hai chiều của
	`Employee.update_user_status` (core): `status` về `Active` mà tài khoản còn khoá thì người ta
	đi làm lại nhưng không đăng nhập được, và không có gì báo cho ai biết vì sao.
	"""
	if frappe.db.get_value("Employee", employee, "status") == "Active":
		return

	frappe.db.set_value("Employee", employee, "status", "Active")

	user_id = frappe.db.get_value("Employee", employee, "user_id")
	if user_id and not frappe.db.get_value("User", user_id, "enabled"):
		frappe.db.set_value("User", user_id, "enabled", 1)


def _active_subordinates(employee: str) -> list[str]:
	"""Nhân viên `Active` còn `reports_to` người này.

	Sao lại đúng quy tắc của `Employee.validate_status`
	(`erpnext/setup/doctype/employee/employee.py:274`): để người quản lý ở trạng thái `Left` mà
	cấp dưới vẫn trỏ tới thì cây tổ chức gãy, và các luồng duyệt đơn theo `reports_to` sẽ trỏ vào
	một tài khoản đã khoá.
	"""
	return frappe.get_all(
		"Employee", filters={"reports_to": employee, "status": "Active"}, pluck="name"
	)


def _disable_linked_user(employee: str):
	"""Khoá tài khoản User của người đã nghỉ.

	Đây là phần `Employee.update_user_status` của core mà `db.set_value` bỏ qua. Chỉ **khoá**,
	không bao giờ mở lại — job này chỉ đi một chiều Active -> Left.

	⚠ Khác với nghỉ thai sản: `CustomEmployee.update_user_status` cố tình KHÔNG khoá khi Inactive
	là do thai sản (họ vẫn cần xem phiếu lương, nộp đơn nghỉ). Nghỉ việc thì phải khoá.
	"""
	user_id = frappe.db.get_value("Employee", employee, "user_id")
	if not user_id:
		return
	if frappe.db.get_value("User", user_id, "enabled"):
		frappe.db.set_value("User", user_id, "enabled", 0)
