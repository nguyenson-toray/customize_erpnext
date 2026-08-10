// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["OT Compliance"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			// Kỳ lương TIQN: 26 tháng trước -> 25 tháng này
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -1).replace(/-01$/, "-26"),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start().replace(/-01$/, "-25"),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "only_violations",
			label: __("Only Show Violations"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "violations" && data.violations) {
			return `<span style="color: var(--red-600); font-weight: 500;">${value}</span>`;
		}
		// Còn dưới 20 giờ là sắp chạm trần năm — cảnh báo sớm để còn điều tiết sản xuất
		if (column.fieldname === "remaining_year" && data.remaining_year <= 20) {
			const color = data.remaining_year < 0 ? "var(--red-600)" : "var(--orange-600)";
			return `<span style="color: ${color}; font-weight: 500;">${value}</span>`;
		}
		return value;
	},
};
