// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("TIQN Portal Account", {
	refresh(frm) {
		add_zalo_chat_button(frm);
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
