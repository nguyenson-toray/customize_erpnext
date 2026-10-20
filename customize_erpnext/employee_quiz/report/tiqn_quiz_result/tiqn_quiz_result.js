// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["TIQN Quiz Result"] = {
	filters: [
		{ fieldname: "quiz", label: __("Quiz"), fieldtype: "Link", options: "TIQN Quiz" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["Completed", "In Progress", "All"],
			default: "Completed",
		},
		{
			fieldname: "result",
			label: __("Result"),
			fieldtype: "Select",
			options: ["", "Passed", "Not Passed"],
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "section", label: __("Section"), fieldtype: "Link", options: "Section" },
		{ fieldname: "group", label: __("Group"), fieldtype: "Link", options: "Group" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{
			fieldname: "detail",
			label: __("Detail"),
			fieldtype: "Check",
			default: 0,
			on_change(report) {
				if (report.get_filter_value("detail") && !report.get_filter_value("quiz")) {
					frappe.show_alert(
						{ message: __("Pick a Quiz to see the answer of every question."), indicator: "orange" },
						6
					);
				}
				report.refresh(true);
			},
			description: __("One answer + points column per question (needs a Quiz)."),
		},
		{
			fieldname: "counted_only",
			label: __("Counted Attempt Only"),
			fieldtype: "Check",
			default: 0,
			description: __("Only each employee's latest submitted attempt (the one that counts)."),
		},
		{
			fieldname: "include_not_started",
			label: __("Include Not Started"),
			fieldtype: "Check",
			default: 0,
			depends_on: "eval:doc.quiz",
			description: __("Also list employees of this quiz who have not started yet."),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data || !column.fieldname) return value;
		if (column.fieldname === "result" && data.result) {
			return `<span style="color:${data.passed ? "var(--green-600)" : "var(--red-600)"};font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "status" && data.status === "Not Started") {
			return `<span style="color:var(--orange-600);font-weight:600">${value}</span>`;
		}
		if (column.fieldname.startsWith("a_")) {
			const ok = data["ok_" + column.fieldname.slice(2)];
			if (ok === 1) return `<span style="color:var(--green-600)">${value}</span>`;
			if (ok === 0) return `<span style="color:var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
