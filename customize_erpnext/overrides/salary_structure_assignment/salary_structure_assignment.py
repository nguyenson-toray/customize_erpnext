# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

# Các khoản cấu thành căn cứ đóng BHXH/BHYT/BHTN — HR đã xác nhận.
# KHÔNG gồm: xăng xe, điện thoại, nhà ở, huấn luyện PCCC, KPI, các khoản 7.x
# Xem overrides/payroll_docs/PAYROLL_SETUP.md mục 2.1 (khớp 7/8 phiếu lương thật).
#
# ⚠ Giữ ĐỒNG BỘ với danh sách trong
#    public/js/custom_scripts/salary_structure_assignment.js
SI_BASE_FIELDS = (
	"base",                                # Lương trên HĐLĐ
	"custom_technical_allowance",          # Phụ cấp kỹ thuật
	"custom_position_allowance",           # Phụ cấp chức vụ
	"custom_pccc_allowance",               # Phụ cấp PCCC
	"custom_atvs_allowance",               # Phụ cấp ATVS viên
	"custom_supporting_stages_allowance",  # Phụ cấp hỗ trợ công đoạn
	"custom_attendance_incentive",         # Thưởng chuyên cần
	"custom_responsibility_incentive",     # Thưởng trách nhiệm
)

def compute_si_base(doc):
	"""Tổng các khoản cấu thành căn cứ đóng bảo hiểm."""
	return flt(sum(flt(doc.get(f)) for f in SI_BASE_FIELDS))


def set_si_base(doc, method=None):
	"""hooks.py doc_events["Salary Structure Assignment"]["validate"]

	`custom_si_base` mặc định TỰ TÍNH từ lương HĐLĐ + các phụ cấp thuộc diện đóng BH.
	Khi cần khai khác mức đã đăng ký với cơ quan BHXH thì tick `custom_si_base_override`
	rồi nhập tay — lúc đó hệ thống không ghi đè nữa, chỉ cảnh báo mức lệch.

	Vì sao cần cho phép ghi đè: mức đăng ký với cơ quan BHXH có thể lệch khỏi tổng
	lương thực tế (đăng ký chậm sau khi tăng lương, hoặc thoả thuận riêng). Ca thật:
	TIQN-0006 có căn cứ BH lệch +773,965 so với tổng các khoản trên phiếu.
	"""
	computed = compute_si_base(doc)

	if not doc.custom_si_base_override:
		doc.custom_si_base = computed
		return

	# Ghi đè thủ công: giữ nguyên số HR nhập, nhưng nói rõ đang lệch bao nhiêu.
	# Cảnh báo với MỌI mức lệch — 8 khoản cấu thành đều là Currency số nguyên đồng nên
	# phép cộng không sinh sai số làm tròn. Đặt ngưỡng bỏ qua là âm thầm chấp nhận
	# dữ liệu sai.
	diff = flt(doc.custom_si_base) - computed
	if diff:
		frappe.msgprint(
			_("SI Base đang nhập tay: {0}, lệch {1} so với tổng lương HĐLĐ + phụ cấp ({2}).").format(
				frappe.format_value(doc.custom_si_base, {"fieldtype": "Currency"}),
				frappe.format_value(diff, {"fieldtype": "Currency"}),
				frappe.format_value(computed, {"fieldtype": "Currency"}),
			),
			title=_("Kiểm tra mức đóng bảo hiểm"),
			indicator="orange",
			alert=True,
		)
