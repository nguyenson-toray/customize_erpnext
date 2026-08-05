// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// Các khoản cấu thành căn cứ đóng BHXH/BHYT/BHTN — HR đã xác nhận.
// ⚠ Giữ ĐỒNG BỘ với SI_BASE_FIELDS trong
//    overrides/salary_structure_assignment/salary_structure_assignment.py
// (server mới là nguồn chuẩn — JS chỉ để người nhập thấy số ngay, không phải chờ save)
const TIQN_SI_BASE_FIELDS = [
	'base',                                 // Lương trên HĐLĐ
	'custom_technical_allowance',           // Phụ cấp kỹ thuật
	'custom_position_allowance',            // Phụ cấp chức vụ
	'custom_pccc_allowance',                // Phụ cấp PCCC
	'custom_atvs_allowance',                // Phụ cấp ATVS viên
	'custom_supporting_stages_allowance',   // Phụ cấp hỗ trợ công đoạn
	'custom_attendance_incentive',          // Thưởng chuyên cần
	'custom_responsibility_incentive',      // Thưởng trách nhiệm
];

function tiqn_recalc_si_base(frm) {
	if (frm.doc.custom_si_base_override) {
		return;    // đang nhập tay -> không đụng vào
	}
	const total = TIQN_SI_BASE_FIELDS.reduce((sum, f) => sum + flt(frm.doc[f]), 0);
	if (flt(frm.doc.custom_si_base) !== total) {
		frm.set_value('custom_si_base', total);
	}
}

frappe.ui.form.on('Salary Structure Assignment', {
	refresh(frm) {
		tiqn_recalc_si_base(frm);
	},

	custom_si_base_override(frm) {
		// Bỏ tick -> quay lại số tự tính
		tiqn_recalc_si_base(frm);
	},
});

// Mỗi khoản cấu thành đều kích hoạt tính lại
TIQN_SI_BASE_FIELDS.forEach((fieldname) => {
	frappe.ui.form.on('Salary Structure Assignment', {
		[fieldname]: (frm) => tiqn_recalc_si_base(frm),
	});
});
