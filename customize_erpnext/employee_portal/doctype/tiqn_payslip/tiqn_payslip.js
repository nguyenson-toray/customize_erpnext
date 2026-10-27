// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// "Download PDF": the paper payslip as an A4 PDF (employee_portal.payslip_print), named
// {Period}_{section}_{group}_{employee}_{employee_name}.pdf. Draft / Withdrawn print with
// a "BẢN NHÁP / DRAFT" watermark. The list's Download PDF builds many in the background
// (payslip_print.start_pdf_job).

frappe.ui.form.on('TIQN Payslip', {
	refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role(['CnB', 'System Manager'])) return;
		frm.add_custom_button(__('Download PDF'), () => {
			// POST + CSRF; the browser downloads the file.
			open_url_post(frappe.request.url, {
				cmd: 'customize_erpnext.employee_portal.payslip_print.download_pdf',
				names: JSON.stringify([frm.doc.name]),
			});
		});
	},
});
