// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings["TIQN Quiz Response"] = {
	get_indicator(doc) {
		const colors = { "In Progress": "orange", Submitted: "green", Expired: "blue" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
