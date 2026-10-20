// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings["TIQN Quiz"] = {
	get_indicator(doc) {
		const colors = { Draft: "gray", Open: "green", Closed: "red" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
