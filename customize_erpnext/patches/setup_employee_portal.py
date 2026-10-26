# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: first-time setup of the Employee Portal (Zalo Mini App) module.

1. Service user `portal@tiqn.com.vn` - Mini App requests run as this user so
   owner/modified_by carry a real name. Website User, no roles, no password: it
   cannot log in anywhere.
2. Employee Portal Settings - defaults + a Vietnamese template of the privacy policy
   and terms that HR edits before the Mini App is submitted to Zalo.
3. Display config of the payslip on every Salary Component (custom_portal_*), only
   where still empty - HR's later edits are never overwritten.

Idempotent.
"""

import json

import frappe
from frappe.utils import today

PORTAL_USER = "portal@tiqn.com.vn"

# abbr -> (section, row type, parent abbr, label, unit, order)
COMPONENTS = {
	"1": ("Earnings", "Line", None, "Lương cơ bản", "VND", 10),
	"2": ("Earnings", "Line", None, "Làm thêm giờ", "VND", 20),
	"3": ("Earnings", "Subtotal", None, "Lương tháng", "VND", 30),
	"3.1": ("Earnings", "Subtotal", None, "Phụ cấp", "VND", 40),
	"3.2": ("Earnings", "Line", "3.1", "Phụ cấp kỹ thuật", "VND", 41),
	"3.3": ("Earnings", "Line", "3.1", "Phụ cấp chức vụ", "VND", 42),
	"3.4": ("Earnings", "Line", "3.1", "Phụ cấp nhà ở", "VND", 43),
	"3.5": ("Earnings", "Line", "3.1", "Phụ cấp xăng xe", "VND", 44),
	"3.6": ("Earnings", "Line", "3.1", "Phụ cấp điện thoại", "VND", 45),
	"3.7": ("Earnings", "Line", "3.1", "Phụ cấp PCCC", "VND", 46),
	"3.8": ("Earnings", "Line", "3.1", "Phụ cấp ATVS viên", "VND", 47),
	"3.9": ("Earnings", "Line", "3.1", "Phụ cấp hỗ trợ công đoạn", "VND", 48),
	"3.10": ("Earnings", "Line", "3.1", "Phụ cấp huấn luyện PCCC", "VND", 49),
	"4": ("Earnings", "Subtotal", None, "Thưởng", "VND", 50),
	"4.1": ("Earnings", "Line", "4", "Thưởng chuyên cần", "VND", 51),
	"4.2": ("Earnings", "Line", "4", "Thưởng trách nhiệm", "VND", 52),
	"4.3": ("Earnings", "Line", "4", "Thưởng KPI", "VND", 53),
	"4.4": ("Earnings", "Line", "4", "Hỗ trợ làm tại công ty gia công", "VND", 54),
	"4.5": ("Earnings", "Line", "4", "Hỗ trợ làm ca", "VND", 55),
	"4.6": ("Earnings", "Line", "4", "Hỗ trợ con nhỏ", "VND", 56),
	"4.7": ("Earnings", "Line", "4", "Hỗ trợ xăng xe", "VND", 57),
	"5": ("Earnings", "Section Total", None, "Tổng thu nhập", "VND", 60),
	"6": ("Deductions", "Section Total", None, "Tổng khấu trừ", "VND", 100),
	"6.1": ("Deductions", "Line", None, "BHXH (8%)", "VND", 101),
	"6.2": ("Deductions", "Line", None, "BHYT (1,5%)", "VND", 102),
	"6.3": ("Deductions", "Line", None, "BHTN (1%)", "VND", 103),
	"6.4": ("Deductions", "Line", None, "Phí công đoàn", "VND", 104),
	"6.5": ("Deductions", "Line", None, "Thuế TNCN", "VND", 105),
	"6.6": ("Deductions", "Line", None, "Bồi thường hợp đồng", "VND", 106),
	"7": ("Others", "Section Total", None, "Tổng khoản khác", "VND", 200),
	"7.1": ("Others", "Line", None, "Hỗ trợ tiền cơm", "VND", 201),
	"7.2": ("Others", "Line", None, "Quà kết hôn", "VND", 202),
	"7.3": ("Others", "Line", None, "Quyết toán thuế TNCN", "VND", 203),
	"7.4": ("Others", "Line", None, "Thanh toán phép năm", "VND", 204),
	"7.5": ("Others", "Line", None, "Phụ cấp kinh nguyệt", "VND", 205),
	"7.6": ("Others", "Line", None, "21,5% BHXH+BHYT+BHTN", "VND", 206),
	"7.7": ("Others", "Line", None, "Thưởng lễ", "VND", 207),
	"8": ("Adjustment", "Section Total", None, "Điều chỉnh lương tháng trước", "VND", 300),
	"9": ("Net Pay", "Section Total", None, "Thực lĩnh", "VND", 400),
	"1.1": ("Attendance", "Line", None, "Công chuẩn", "Day", 900),
	"1.2": ("Attendance", "Line", None, "Công thực tế", "Day", 910),
	"2.1": ("Attendance", "Line", None, "Giờ làm thêm ngày thường", "Hour", 920),
	"2.2": ("Attendance", "Line", None, "Giờ làm thêm cuối tuần", "Hour", 930),
	"2.3": ("Attendance", "Line", None, "Giờ làm thêm ngày lễ", "Hour", 940),
}

PRIVACY_POLICY = """<h3>Chính sách dữ liệu – Cổng nhân viên trên Zalo</h3>
<p><i>Bản mẫu – phòng Nhân sự cần rà soát và hoàn thiện trước khi phát hành.</i></p>
<p><b>1. Dữ liệu chúng tôi sử dụng.</b> Số điện thoại Zalo của bạn (do Zalo cung cấp sau khi bạn đồng ý)
và mã người dùng Zalo dành riêng cho ứng dụng này. Ứng dụng không có tài khoản hay mật khẩu riêng.</p>
<p><b>2. Mục đích.</b> Đối chiếu số điện thoại với hồ sơ nhân viên đã đăng ký tại phòng Nhân sự để xác định
bạn là ai, từ đó chỉ hiển thị cho bạn dữ liệu của chính bạn: chấm công, tăng ca, nghỉ phép, phiếu lương.</p>
<p><b>3. Không chia sẻ.</b> Dữ liệu không được chia sẻ cho bên thứ ba và không dùng cho quảng cáo.</p>
<p><b>4. Lưu trữ và bảo mật.</b> Dữ liệu nằm trên máy chủ của công ty. Mỗi lần xem phiếu lương đều được ghi
nhật ký. Khi bạn nghỉ việc, quyền xem chỉ còn trong thời hạn công ty quy định, sau đó tài khoản ngừng hoạt động.</p>
<p><b>5. Quyền của bạn.</b> Bạn có thể yêu cầu phòng Nhân sự khoá tài khoản Cổng nhân viên của mình hoặc cập
nhật số điện thoại bất kỳ lúc nào.</p>
<p><b>6. Liên hệ.</b> Phòng Nhân sự – [SĐT / EMAIL].</p>
"""

TERMS_OF_USE = """<h3>Điều khoản sử dụng – Cổng nhân viên trên Zalo</h3>
<p><i>Bản mẫu – phòng Nhân sự cần rà soát và hoàn thiện trước khi phát hành.</i></p>
<p>1. Ứng dụng dành riêng cho nhân viên của công ty, dùng để xem dữ liệu cá nhân và gửi đơn nghỉ phép, giải trình chấm công.</p>
<p>2. Thông tin lương là bảo mật. Bạn có trách nhiệm không chia sẻ màn hình phiếu lương cho người khác.</p>
<p>3. Số liệu chấm công trước ngày chốt là số tạm tính. Số liệu chính thức là phiếu lương do phòng Nhân sự phát hành.</p>
<p>4. Đơn gửi qua ứng dụng có giá trị như đơn giấy và được trưởng bộ phận duyệt trên hệ thống của công ty.</p>
<p>5. Nếu phát hiện sai sót, vui lòng liên hệ phòng Nhân sự để được điều chỉnh.</p>
"""


def execute():
	create_portal_user()
	seed_settings()
	seed_salary_components()


def create_portal_user():
	if frappe.db.exists("User", PORTAL_USER):
		return
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": PORTAL_USER,
			"first_name": "Employee Portal",
			"last_name": "Mini App",
			"user_type": "Website User",
			"language": "vi",
			"send_welcome_email": 0,
			"enabled": 1,
		}
	)
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)


def seed_settings():
	s = frappe.get_single("Employee Portal Settings")
	if s.legal_version:
		return  # already set up once - never overwrite HR's edits
	company = frappe.defaults.get_global_default("company")
	s.update(
		{
			"company_display_name": company,
			"company_short_name": "TIQN",
			"read_only_days": 30,
			"session_days": 30,
			"min_client_version": "1.0.0",
			"expected_pay_day": 5,
			"show_zero_lines": 0,
			"max_files": 5,
			"max_file_size_mb": 5,
			"oa_chat_enabled": 1,
			"oa_messages_enabled": 0,
			"feature_payslip": 1,
			"feature_notifications": 1,
			"feature_attendance": 0,
			"feature_overtime": 0,
			"feature_leave_view": 0,
			"feature_leave_create": 0,
			"feature_explanation_create": 0,
			"feature_oa_invite": 0,
			"legal_version": today(),
			"privacy_policy": PRIVACY_POLICY,
			"terms_of_use": TERMS_OF_USE,
		}
	)
	s.flags.ignore_permissions = True
	s.save()


def ensure_portal_custom_fields():
	"""🔴 Migrate imports fixtures AFTER post_model_sync patches, so on the first migrate
	the custom_portal_* columns do not exist yet when this patch runs. Create exactly
	those fields from the fixture file now; the later fixture sync finds them in place."""
	path = frappe.get_app_path("customize_erpnext", "fixtures", "custom_field.json")
	with open(path) as fh:
		entries = [d for d in json.load(fh) if d.get("dt") == "Salary Component" and d["fieldname"].startswith("custom_portal_")]
	for entry in entries:
		if not frappe.db.exists("Custom Field", entry["name"]):
			doc = frappe.get_doc({k: v for k, v in entry.items() if k not in ("modified", "creation")})
			doc.insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Salary Component")


def seed_salary_components():
	ensure_portal_custom_fields()
	if "custom_portal_section" not in frappe.db.get_table_columns("Salary Component"):
		return  # v4 (26/10/2026): the payslip no longer reads Salary Component
	rows = frappe.get_all(
		"Salary Component",
		fields=["name", "salary_component_abbr", "custom_portal_section"],
	)
	by_abbr = {str(r.salary_component_abbr).strip(): r.name for r in rows}
	for r in rows:
		if r.custom_portal_section:
			continue
		abbr = str(r.salary_component_abbr).strip()
		spec = COMPONENTS.get(abbr)
		if not spec:
			# HRMS demo components (Basic, HRA, Income Tax, Provident Fund...) - hidden,
			# never deleted or disabled (decided 12/10/2026).
			frappe.db.set_value("Salary Component", r.name, "custom_portal_section", "Hidden", update_modified=False)
			continue
		section, row_type, parent_abbr, label, unit, order = spec
		frappe.db.set_value(
			"Salary Component",
			r.name,
			{
				"custom_portal_section": section,
				"custom_portal_row": row_type,
				"custom_portal_parent": by_abbr.get(parent_abbr) if parent_abbr else None,
				"custom_portal_label": label,
				"custom_portal_unit": unit,
				"custom_portal_order": order,
			},
			update_modified=False,
		)
