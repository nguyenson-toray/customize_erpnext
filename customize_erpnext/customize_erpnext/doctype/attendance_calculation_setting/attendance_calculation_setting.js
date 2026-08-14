// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// The report normally goes out on a schedule to the Manager / HR lists below.
// This button is for sending it by hand, so it deliberately does not prefill
// those lists — addresses are typed in, which keeps a manual test from reaching
// the real audience by accident.
frappe.ui.form.on("Attendance Calculation Setting", {
	refresh(frm) {
		frm.add_custom_button(__("Send Daily Attendance Report"), () =>
			send_daily_attendance_report_dialog()
		);
	},
});

function send_daily_attendance_report_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Send Daily Attendance Report"),
		fields: [
			{
				fieldname: "date",
				label: __("Date"),
				fieldtype: "Date",
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{
				fieldname: "attach_detail",
				label: __("Attach file detail"),
				fieldtype: "Check",
				default: 0,
				description: __("Adds the detailed Excel workbook for this date."),
			},
			{
				fieldname: "force_update_attendance",
				label: __("Recalculate attendance before sending"),
				fieldtype: "Check",
				default: 0,
				// Not tied to the attachment: recalculating rebuilds the
				// Attendance records the summary figures are read from too.
				description: __("Rebuilds attendance from check-ins. Affects every figure, not just the attachment."),
			},
			{
				fieldname: "bypass_holiday_check",
				label: __("Send even on Sunday or a holiday"),
				fieldtype: "Check",
				default: 0,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "recipients",
				label: __("Email Recipients"),
				fieldtype: "Small Text",
				reqd: 1,
				description: __("Enter one email address per line"),
			},
		],
		primary_action_label: __("Send"),
		primary_action(values) {
			const emails = values.recipients
				.split(/[\n,]/)
				.map((e) => e.trim())
				.filter((e) => e.length > 0);
			const invalid = emails.filter((e) => !frappe.utils.validate_type(e, "email"));
			if (invalid.length) {
				frappe.msgprint({
					title: __("Invalid Email"),
					message: __("Please enter valid email addresses: ") + invalid.join(", "),
					indicator: "red",
				});
				return;
			}

			const btn = dialog.get_primary_btn();
			btn.prop("disabled", true);

			frappe.call({
				method: "customize_erpnext.api.daily_attendance_email.send_daily_attendance_email",
				args: {
					date: values.date,
					recipients: values.recipients,
					attach_detail: values.attach_detail ? 1 : 0,
					force_update_attendance: values.force_update_attendance ? 1 : 0,
					bypass_holiday_check: values.bypass_holiday_check ? 1 : 0,
				},
				// No freeze: the work runs in a background job, so the dialog closes
				// immediately instead of holding the user through a rebuild.
				callback(r) {
					const res = r.message || {};
					if (res.status === "queued") {
						dialog.hide();
						frappe.show_alert(
							{
								message: __("Report queued for {0}. The email will arrive shortly.", [
									(res.recipients || []).join(", "),
								]),
								indicator: "green",
							},
							10
						);
					} else {
						// "skipped" is a normal outcome (holiday), so it reads as a
						// notice rather than a failure.
						frappe.msgprint({
							title: __("Not Sent"),
							message: res.message || __("Unknown response"),
							indicator: "orange",
						});
						btn.prop("disabled", false).text(__("Send"));
					}
				},
				error() {
					btn.prop("disabled", false).text(__("Send"));
				},
			});
		},
	});

	dialog.show();
}
