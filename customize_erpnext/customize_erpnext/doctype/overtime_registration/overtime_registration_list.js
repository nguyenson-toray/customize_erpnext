// overtime_registration_list.js - List View customizations for Overtime Registration

frappe.listview_settings["Overtime Registration"] = {
	onload: function (listview) {
		listview.page.add_inner_button(__("Help"), function () {
			show_ot_help_dialog();
		});
	}
};

function show_ot_help_dialog() {
	if (!document.getElementById("ot-help-dialog-css")) {
		const style = document.createElement("style");
		style.id = "ot-help-dialog-css";
		style.textContent = `
.ot-help { font-size: 15px; }
.ot-help ol { margin: 0; padding-left: 26px; }
.ot-help li { margin-bottom: 22px; line-height: 1.6; }
.ot-help li b { color: var(--text-color); }
.ot-help li > b:first-child { font-size: 16px; }
.ot-help .ot-help-sub {
    margin: 8px 0 0; padding-left: 20px; font-size: 13.5px; color: var(--text-muted);
}
.ot-help .ot-help-sub li { margin-bottom: 6px; }
.ot-help .ot-help-tip {
    margin-top: 20px; padding: 12px 16px; border-radius: 8px;
    background: var(--bg-light-gray, rgba(140, 140, 140, 0.1));
    font-size: 13.5px; color: var(--text-muted);
}
.ot-help .ot-help-tip a { color: var(--text-color); text-decoration: underline; }
`;
		document.head.appendChild(style);
	}

	const steps = [
		{
			title: __("Create the request"),
			html: __("Click <b>+ Overtime Registration (+ Thêm đăng ký tăng ca)</b> (top right of this list) to open a new form.")
		},
		{
			title: __("Get the employees"),
			html: __("Click <b>{0}</b>, then in the window that opens: pick a <b>Group</b>, a <b>Week</b>, one or more <b>days</b>, the <b>begin/end time</b> and the <b>reason</b>.", ["Get Employees By Group"]),
			sub: [__("On the right side, tick the employees to add (type a name or ID to search).")]
		},
		{
			title: __("Add and repeat"),
			html: __("Click <b>Add Selected</b> — the rows are written immediately and the window stays open."),
			sub: [
				__("Need another day, time or group? Just choose again and click Add Selected — no need to start over."),
				__("If an entry matches one already in the list (same employee, same date, same/overlapping time), the system asks whether to replace it or keep the existing one.")
			]
		},
		{
			title: __("Check and save"),
			html: __("Click <b>Close</b> when done. Review the list — use <b>Pivot View</b> to see everyone at a glance — then click <b>Save</b>.")
		},
		{
			title: __("Send for approval"),
			html: __("Click <b>Submit</b>. Found a mistake after submitting? Use <b>Cancel</b>, then <b>Amend</b> to correct it and submit again.")
		}
	];

	const items = steps.map(s => {
		const sub = s.sub
			? "<ul class=\"ot-help-sub\">" + s.sub.map(x => "<li>" + x + "</li>").join("") + "</ul>"
			: "";
		return "<li><b>" + frappe.utils.escape_html(s.title) + "</b><br>" + s.html + sub + "</li>";
	}).join("");

	const dialog = new frappe.ui.Dialog({
		title: __("How to register overtime"),
		size: "large",
		fields: [{
			fieldtype: "HTML",
			options: "<div class=\"ot-help\"><ol>" + items + "</ol>"
				+ "<div class=\"ot-help-tip\">"
				+ __("Want screenshots? See the {0} course.", [
					"<a href=\"https://erp.tiqn.local:8888/lms/courses/erpnext-registration\" target=\"_blank\">"
					+ __("Overtime Registration") + "</a>"
				])
				+ "</div></div>"
		}],
		primary_action_label: __("Got it"),
		primary_action: function () {
			dialog.hide();
		}
	});
	dialog.show();
}
