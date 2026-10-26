# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: Employee Portal Settings > Payslip Lines (26/10/2026), idempotent.

The TIQN Payslip labels became short English ("3.2 Technical Allowance") for the Excel
columns; the Vietnamese label on the Mini App moved to this table, which CnB edits.
Filled with exactly what the app showed before (the Vietnamese part of the old
bilingual labels) - only rows still empty, so CnB's later edits are never overwritten.
"""

import frappe

SETTINGS = "Employee Portal Settings"
APP_LABELS = {
	"sc_1": "Lương cơ bản",
	"sc_1_1": "Số ngày làm việc chuẩn trong tháng",
	"sc_1_2": "Số ngày công thực tế làm việc",
	"sc_2": "Làm việc ngoài giờ",
	"sc_2_1": "Số giờ làm thêm ngày thường",
	"sc_2_2": "Số giờ làm thêm ngày cuối tuần",
	"sc_2_3": "Số giờ làm thêm ngày Lễ",
	"sc_3": "Lương tháng",
	"sc_3_1": "Phụ cấp",
	"sc_3_2": "Phụ cấp kỹ thuật",
	"sc_3_3": "Phụ cấp chức vụ",
	"sc_3_4": "Phụ cấp nhà ở",
	"sc_3_5": "Phụ cấp xăng xe",
	"sc_3_6": "Phụ cấp điện thoại",
	"sc_3_7": "Phụ cấp PCCC",
	"sc_3_8": "Phụ cấp ATVS viên",
	"sc_3_9": "Phụ cấp hỗ trợ công đoạn",
	"sc_3_10": "Phụ cấp tham gia huấn luyện PCCC",
	"sc_4": "Thưởng",
	"sc_4_1": "Thưởng Chuyên cần",
	"sc_4_2": "Thưởng trách nhiệm",
	"sc_4_3": "Thưởng đánh giá kết quả làm việc",
	"sc_4_4": "Tiền hỗ trợ làm tại công ty gia công",
	"sc_4_5": "Tiền hỗ trợ làm ca",
	"sc_4_6": "Hỗ trợ con nhỏ",
	"sc_4_7": "Hỗ trợ xăng xe",
	"sc_5": "Tổng",
	"sc_6": "Các khoản khấu trừ",
	"sc_6_1": "BHXH (8%)",
	"sc_6_2": "BHYT (1,5%)",
	"sc_6_3": "BHTN (1%)",
	"sc_6_4": "Phí Công Đoàn",
	"sc_6_5": "Thuế TNCN",
	"sc_6_6": "Tiền bồi thường HĐ của NLĐ",
	"sc_7": "Các khoản khác",
	"sc_7_1": "Hỗ trợ tiền cơm",
	"sc_7_2": "Quà kết hôn",
	"sc_7_3": "Quyết toán thuế",
	"sc_7_4": "Thanh toán phép năm",
	"sc_7_5": "Phụ cấp kinh nguyệt",
	"sc_7_6": "21.5% (BHXH+BHYT+BHTN)",
	"sc_7_7": "Thưởng lễ",
	"sc_8": "Điều chỉnh lương tháng trước",
	"sc_9": "Thực lĩnh",
}


def execute():
	frappe.clear_cache(doctype="TIQN Payslip")
	settings = frappe.get_single(SETTINGS)
	settings.sync_payslip_lines()
	for row in settings.payslip_lines:
		if not (row.portal_label or "").strip() and row.payslip_field in APP_LABELS:
			row.portal_label = APP_LABELS[row.payslip_field]
	settings.flags.ignore_permissions = True
	settings.save()
