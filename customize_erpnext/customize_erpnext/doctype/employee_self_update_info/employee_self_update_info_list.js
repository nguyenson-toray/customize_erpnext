// Copyright (c) 2026, TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Self Update Info"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		if (doc.status === "Submitted") return [__("Submitted"), "green", "status,=,Submitted"];
		return [__("Draft"), "orange", "status,=,Draft"];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Download Excel"), () => {
			const selected = listview.get_checked_items().map((d) => d.name);
			// download_excel streams a binary response; use a form POST so the
			// browser saves the file (open_url_post adds the CSRF token).
			open_url_post(
				"/api/method/customize_erpnext.api.self_update_info.self_update_info_api.download_excel",
				{ names: selected.length ? JSON.stringify(selected) : "" }
			);
		});
	},
};
