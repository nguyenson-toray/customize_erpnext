// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt
/**
 * Employee Promotion / Employee Transfer — restrict the "Add Employee Property" picker
 * and let past records be recorded for employees who are no longer Active.
 *
 * Stock hrms/hr/employee_property_update.js offers an EXCLUDE list, so the picker ends
 * up listing ~80 Employee fields (bank_ac_no, blood_group, shoe_size, ...). Here it is
 * turned into a short ALLOW list of the organisational fields a promotion/transfer is
 * actually about.
 *
 * How the override takes effect — this file is loaded through the `doctype_js` hook,
 * which frappe appends AFTER the doctype's own .js (frappe/desk/form/meta.py:111).
 * Both end up in one `__js` blob run as a single `new Function(...)` body
 * (script_manager.js:191), which means:
 *   - `cur_frm.events[handler] = <last one registered>` (script_manager.js:42), so the
 *     handlers below REPLACE the HRMS ones. The stock `refresh` keeps working untouched
 *     because it calls `frm.events.setup_employee_property_button(frm, table)` — which
 *     resolves to our version.
 *   - `show_dialog()` from the HRMS file is in scope here and is reused as-is, together
 *     with its `render_dynamic_field` / `add_to_details` / `validate_duplicate` helpers.
 *
 * Keep ALLOWED_PROPERTY_FIELDS in sync with ALLOWED_FIELDS in
 * customize_erpnext/overrides/employee_property/work_history.py (the server-side guard).
 */

// Order here is the order shown in the dropdown.
const ALLOWED_PROPERTY_FIELDS = [
	"department",
	"custom_section",
	"custom_group",
	"designation",
	"reports_to",
	"employment_type",
];

// Past promotions/transfers still have to be recordable for people on maternity leave
// (Inactive) or who have already left. "Left " with a trailing space is real data on
// this site — both spellings must be listed or those employees drop out of the picker.
const PROPERTY_EMPLOYEE_STATUSES = ["Active", "Inactive", "Left "];

frappe.ui.form.on(cur_frm.doctype, {
	setup: function (frm) {
		frm.set_query("employee", function () {
			return {
				filters: {
					status: ["in", PROPERTY_EMPLOYEE_STATUSES],
				},
			};
		});
	},

	setup_employee_property_button: function (frm, table) {
		frm.fields_dict[table].grid.add_custom_button(__("Add Employee Property"), () => {
			if (!frm.doc.employee) {
				frappe.msgprint(__("Please select Employee first."));
				return;
			}

			frappe.model.with_doctype("Employee", () => {
				const meta = frappe.get_meta("Employee");
				const allowed_fields = [];

				ALLOWED_PROPERTY_FIELDS.forEach((fieldname) => {
					const df = meta.fields.find((d) => d.fieldname === fieldname);
					if (!df) {
						// Field was renamed or removed on this site — skip it rather than
						// offering a property the server cannot apply.
						console.warn(`Employee has no field "${fieldname}", skipped`);
						return;
					}
					// Nhãn trần, không kèm "(custom_group)". HRMS gốc dán fieldname vào để
					// phân biệt các field trùng nhãn khi dropdown liệt kê cả ~80 field
					// Employee; allow-list 6 field ở đây không có nhãn nào trùng nên phần
					// đuôi đó chỉ làm rối người dùng.
					allowed_fields.push({
						label: __(df.label, null, df.parent),
						value: df.fieldname,
					});
				});

				show_dialog(frm, table, allowed_fields);
			});
		});
	},
});
