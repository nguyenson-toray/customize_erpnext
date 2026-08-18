"""Override report `Shift Attendance` của HRMS bằng 100% logic của `Shift Attendance Customize`.

Bản Customize được viết lại cho đúng thực tế TIQN và đang chạy đúng, nên nó là **nguồn duy
nhất**: module này không chép logic, chỉ trỏ report của HRMS sang đúng hàm đó.

Hai mặt phải đồng bộ:

  * **Python** — gán đè `hrms...shift_attendance.execute`. Frappe phân giải script report bằng
    `frappe.get_attr("<module>.execute")` **lúc chạy** nên gán đè thuộc tính module là đủ.
    Cả hai `execute` đều trả 5 phần tử (HRMS trả chart, Customize trả `None` ở vị trí đó) nên
    tương thích, client không cần biết.

  * **JS** — bộ filter và 3 nút bấm nằm trong file `.js` của report. Thay vì chép tay 446 dòng
    (rồi lệch nhau về sau), `report_js.py` đọc nguyên file `.js` của bản Customize và đổi đúng
    một chuỗi tên report. Đã kiểm: tên report chỉ xuất hiện **một lần** (dòng 4); dòng 224 là
    đường dẫn python `...report.shift_attendance_customize.shift_attendance_customize...` —
    **không được** đổi, vì nút Export Excel phải gọi đúng module đó.

⚠ `Shift Attendance Customize` KHÔNG bị đụng tới. Cả hai report cùng tồn tại và chạy cùng logic;
giữ bản Customize để đối chiếu khi nghi ngờ.
"""

import frappe


def _patch():
	import hrms.hr.report.shift_attendance.shift_attendance as hrms_mod

	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.shift_attendance_customize import (
		execute as customize_execute,
	)

	if not hasattr(hrms_mod, "_tiqn_original_execute"):
		hrms_mod._tiqn_original_execute = hrms_mod.execute

	hrms_mod.execute = customize_execute


try:
	_patch()
	print("✅ Shift Attendance override loaded")
except Exception as e:
	frappe.log_error(
		f"Failed to apply Shift Attendance patch: {str(e)}", "Shift Attendance Monkey Patch Error"
	)
