// Tô màu cột Status: NVR trên form + Status của từng camera trong bảng details.
// Dùng df.formatter (frappe/public/js/frappe/form/formatters.js) thay cho
// get_indicator — get_indicator khiến Frappe gỡ hẳn cột status khỏi list view.
function status_html(value) {
	if (!value) return "";
	const color = value === "Online" ? "var(--green-600, #1a7a1a)" : "var(--red-600, #c00)";
	return `<span style="color:${color};font-weight:600">\u25cf ${__(value)}</span>`;
}

frappe.ui.form.on("CCTV Tracking", {
	onload_post_render(frm) {
		// Status của từng camera trong grid "details"
		const df = frappe.meta.docfield_map["Video Recorded Detail"];
		if (df && df.status) {
			df.status.formatter = (value) => status_html(value);
		}
	},
	refresh(frm) {
		if (frm.doc.status) {
			frm.page.set_indicator(
				__(frm.doc.status),
				frm.doc.status === "Online" ? "green" : "red"
			);
		}
		if (frm.doc.camera_offline) {
			frm.dashboard.set_headline_alert(
				__("{0} of {1} cameras offline", [frm.doc.camera_offline, frm.doc.camera_total]),
				"red"
			);
		}
		frm.refresh_field("details");
	},
});
