# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Chèn / thay JS của report HRMS — cơ chế dùng chung cho mọi report.

Hai kiểu can thiệp:
  * **nối thêm** — sửa mảng `filters` sau khi HRMS đã gán (thêm `Leave Type`, gỡ filter thừa)
  * **clone nguyên file** — phục vụ file `.js` của report khác (`Shift Attendance` dùng JS của
    `Shift Attendance Customize`)

## Vì sao phải làm kiểu này

Frappe **không có hook** nào cho JS của report (không có `report_js` như `doctype_js`).
Và `frappe.desk.query_report.get_script()` chỉ đọc `Report.javascript` **khi file `.js` không
tồn tại trên đĩa** (`query_report.py:199`) — file của HRMS thì luôn có. Nên không sửa được qua
giao diện, cũng không sửa được qua DB.

Cách còn lại: gán đè `get_script`, gọi bản gốc rồi **nối thêm** JS vào cuối. Đoạn nối chạy sau
khi HRMS đã gán `frappe.query_reports["<tên>"] = {...}` nên sửa được mảng `filters`.

⚠ `get_script` là `@frappe.whitelist()`. Phải bọc lại bằng `frappe.whitelist()` khi gán đè, nếu
không hàm mới không nằm trong `frappe.whitelisted` và client sẽ nhận "Not permitted".

⚠ Hàm này chạy cho **mọi** report. Lỗi ở đây là hỏng toàn bộ phần Report của site, nên phần nối
thêm được bọc try/except riêng — hỏng thì report vẫn mở được như bản gốc.

⚠ Giá trị mặc định của filter phụ thuộc dữ liệu (`is_earned_leave = 1`) nên phải dựng JS **ở
server**, không hardcode "Phép năm/ Annual leave" trong chuỗi JS.
"""

import json

import frappe

from customize_erpnext.overrides.leave_reports.leave_report_core import get_annual_leave_types

# Vị trí chèn ô `Leave Type` — ngay sau `company` của từng report:
#   Balance : from_date, to_date, company, | department, employee, employee_status
#   Summary : date, company, | employee, department, employee_status
LEAVE_TYPE_FILTER_INDEX = {
	"Employee Leave Balance": 3,
	"Employee Leave Balance Summary": 2,
}

# `consolidate_leave_types` gom dòng theo leave type và chèn một dòng tiêu đề mỗi nhóm. Report
# nay chạy đúng MỘT leave type nên nó luôn sinh 1 dòng tiêu đề thừa rồi thụt lề phần còn lại —
# mà bản gốc còn để `default: 1`. Python cũng đã bỏ qua giá trị filter này.
DROP_FILTERS = {
	"Employee Leave Balance": ["consolidate_leave_types"],
}

# Report dùng NGUYÊN file .js của một report khác (filter + nút bấm y hệt).
#   {report cần phục vụ: (app, module path của report nguồn, tên report nguồn)}
#
# `Shift Attendance` của HRMS được trỏ sang bản Customize — xem
# `overrides/shift_attendance/__init__.py`. Chỉ đổi đúng chuỗi TÊN REPORT; đường dẫn python
# `...report.shift_attendance_customize.shift_attendance_customize.export_attendance_excel`
# trong file phải GIỮ NGUYÊN, vì nút Export Excel gọi đúng module đó.
CLONE_JS_FROM = {
	"Shift Attendance": (
		"customize_erpnext",
		"customize_erpnext/report/shift_attendance_customize/shift_attendance_customize.js",
		"Shift Attendance Customize",
	),
}


def _cloned_script(report_name: str) -> str:
	spec = CLONE_JS_FROM.get(report_name)
	if not spec:
		return ""

	import os

	app, rel_path, source_report = spec
	path = os.path.join(frappe.get_app_path(app), rel_path)
	with open(path, encoding="utf-8") as f:
		js = f.read()

	# Chỉ thay chuỗi tên report trong `frappe.query_reports["..."]`, không thay đường dẫn module.
	needle = f'frappe.query_reports["{source_report}"]'
	if needle not in js:
		frappe.log_error(
			f"Không tìm thấy {needle} trong {rel_path} — bỏ qua clone JS cho {report_name}",
			"Report JS Clone Error",
		)
		return ""

	return js.replace(needle, f'frappe.query_reports["{report_name}"]')


def _extra_script(report_name: str) -> str:
	cloned = _cloned_script(report_name)
	if cloned:
		return cloned

	index = LEAVE_TYPE_FILTER_INDEX.get(report_name)
	drop = DROP_FILTERS.get(report_name)
	if index is None and not drop:
		return ""

	name_js = json.dumps(report_name, ensure_ascii=False)
	parts = [f'const __r = frappe.query_reports[{name_js}];', "if (__r && Array.isArray(__r.filters)) {"]

	if drop:
		parts.append(
			f"  __r.filters = __r.filters.filter((f) => !{json.dumps(drop, ensure_ascii=False)}.includes(f.fieldname));"
		)

	if index is not None:
		default = (get_annual_leave_types() or [None])[0]
		parts.append(
			"  if (!__r.filters.some((f) => f.fieldname === 'leave_type')) {\n"
			f"    __r.filters.splice({index}, 0, {{\n"
			'      fieldname: "leave_type",\n'
			'      label: __("Leave Type"),\n'
			'      fieldtype: "Link",\n'
			'      options: "Leave Type",\n'
			f"      default: {json.dumps(default, ensure_ascii=False)},\n"
			"      reqd: 1,\n"
			"    });\n"
			"  }"
		)

	parts.append("}")
	return "(() => {\n" + "\n".join(parts) + "\n})();"


def custom_get_script(report_name: str):
	from frappe.desk.query_report import _tiqn_original_get_script

	out = _tiqn_original_get_script(report_name)

	try:
		extra = _extra_script(report_name)
		if extra:
			out["script"] = (out.get("script") or "") + "\n\n" + extra
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leave Report Extra Script Error")

	return out


def patch():
	import frappe.desk.query_report as qr

	if not hasattr(qr, "_tiqn_original_get_script"):
		qr._tiqn_original_get_script = qr.get_script

	# Bọc whitelist: hàm mới phải nằm trong frappe.whitelisted thì client mới gọi được.
	qr.get_script = frappe.whitelist()(custom_get_script)
