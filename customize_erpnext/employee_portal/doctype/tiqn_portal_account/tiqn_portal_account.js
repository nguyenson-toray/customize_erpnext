// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("TIQN Portal Account", {
	refresh(frm) {
		show_zalo_chat(frm);
	},
	phone(frm) {
		show_zalo_chat(frm);
	},
});

// Opens a Zalo chat with the account's phone in Zalo PC (zalo:// link) - same button as on
// TIQN Portal Link Request.
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
