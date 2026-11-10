// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("TIQN Portal Link Request", {
	refresh(frm) {
		show_zalo_chat(frm);
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

// Opens a Zalo chat with the Zalo phone in Zalo PC (zalo:// link): the quick way to call /
// message the employee back before approving.
function show_zalo_chat(frm) {
	const digits = (frm.doc.phone || "").replace(/\D/g, "");
	const phone = digits.startsWith("84") && digits.length === 11 ? `0${digits.slice(2)}` : digits;
	const wrapper = frm.fields_dict.zalo_chat?.$wrapper;
	if (!wrapper) return;
	if (!phone) {
		wrapper.empty();
		return;
	}
	wrapper.html(
		`<a class="btn btn-default btn-sm" href="zalo://conversation?phone=${encodeURIComponent(phone)}">
			${__("Chat on Zalo PC")} (${frappe.utils.escape_html(phone)})
		</a>
		 `
	);
}
