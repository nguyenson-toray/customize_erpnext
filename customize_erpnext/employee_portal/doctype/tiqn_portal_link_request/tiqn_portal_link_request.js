// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("TIQN Portal Link Request", {
	refresh(frm) {
		add_zalo_chat_button(frm);
		if (frm.doc.status !== "Pending" || !frm.perm[0]?.write) return;

		if (frm.doc.warning) {
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.warning).replace(/\n/g, "<br>"),
				"orange"
			);
		}

		frm.add_custom_button(__("Approve"), () => {
			const message = [
				__("Approve only after you have checked that the request really comes from {0} (e.g. call {1}).", [
					frappe.utils.escape_html(`${frm.doc.employee} - ${frm.doc.employee_name || ""}`),
					frappe.utils.escape_html(frm.doc.phone || ""),
				]),
				__("The Zalo phone is written to the employee's record; the user can sign in at the next app start."),
			].join("<br><br>");
			frappe.confirm(message, () =>
				frm.call("approve").then(() => {
					frappe.show_alert({ message: __("Approved"), indicator: "green" });
					frm.reload_doc();
				})
			);
		}).addClass("btn-primary");

		frm.add_custom_button(__("Reject"), () => {
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reject Reason"),
					description: __("Shown to the user in the Mini App"),
				},
				(values) =>
					frm.call("reject", { reason: values.reason }).then(() => {
						frappe.show_alert({ message: __("Rejected"), indicator: "red" });
						frm.reload_doc();
					}),
				__("Reject Request"),
				__("Reject")
			);
		});
	},
});

// "Chat on Zalo PC" (toolbar): opens zalo://conversation?phone=<0xxx> in Zalo PC, the quick
// way to message / call the employee back.
function add_zalo_chat_button(frm) {
	const digits = (frm.doc.phone || "").replace(/\D/g, "");
	const phone = digits.startsWith("84") && digits.length === 11 ? `0${digits.slice(2)}` : digits;
	if (!phone || frm.is_new()) return;
	frm.add_custom_button(__("Chat on Zalo PC"), () => {
		window.location.href = `zalo://conversation?phone=${encodeURIComponent(phone)}`;
	}).attr("title", __("Opens Zalo PC (must be installed and signed in)."));
}
