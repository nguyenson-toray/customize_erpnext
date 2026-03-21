// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// ─── Form View ───────────────────────────────────────────────────────────────

frappe.ui.form.on("Employee Onboarding Form", {
	refresh(frm) {
		frm.set_intro("");

		const status = frm.doc.status;

		if (!frm.is_new()) {
			// ── Approve ──────────────────────────────────────────────────────
			if (status === "Pending Review") {
				frm.add_custom_button(__("Approve"), () => {
					frappe.confirm(
						__("Approve this onboarding form for <b>{0}</b>?", [frm.doc.employee_name]),
						() => {
							frappe.call({
								method: "customize_erpnext.api.onboarding.onboarding_api.approve_onboarding",
								args: { name: frm.doc.name },
								freeze: true,
								freeze_message: __("Approving..."),
								callback(r) {
									if (!r.exc) {
										frappe.show_alert({ message: __("Form approved."), indicator: "green" });
										frm.reload_doc();
									}
								},
							});
						}
					);
				}, __("Actions")).addClass("btn-success");
			}

			// ── Reject ───────────────────────────────────────────────────────
			if (status === "Pending Review") {
				frm.add_custom_button(__("Reject"), () => {
					const d = new frappe.ui.Dialog({
						title: __("Reject Onboarding Form"),
						fields: [
							{
								fieldname: "reason",
								fieldtype: "Small Text",
								label: __("Reject Reason"),
								reqd: 1,
							},
						],
						primary_action_label: __("Reject"),
						primary_action(values) {
							frappe.call({
								method: "customize_erpnext.api.onboarding.onboarding_api.reject_onboarding",
								args: { name: frm.doc.name, reason: values.reason },
								freeze: true,
								freeze_message: __("Rejecting..."),
								callback(r) {
									if (!r.exc) {
										d.hide();
										frappe.show_alert({ message: __("Form rejected."), indicator: "orange" });
										frm.reload_doc();
									}
								},
							});
						},
					});
					d.show();
				}, __("Actions")).addClass("btn-danger");
			}

			// ── Sync to Employee ──────────────────────────────────────────────
			if (status === "Approved") {
				frm.add_custom_button(__("Sync to Employee"), () => {
					frappe.confirm(
						__("Sync onboarding data to Employee <b>{0}</b>? This will overwrite existing Employee fields.", [frm.doc.employee]),
						() => {
							frappe.call({
								method: "customize_erpnext.api.onboarding.onboarding_api.sync_to_employee",
								args: { name: frm.doc.name },
								freeze: true,
								freeze_message: __("Syncing to Employee..."),
								callback(r) {
									if (!r.exc && r.message) {
										frappe.show_alert({
											message: __("Synced {0} fields to Employee.", [r.message.synced_fields?.length || 0]),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				}, __("Actions")).addClass("btn-primary");
			}

			// ── Status indicators ─────────────────────────────────────────────
			if (status === "Approved" || status === "Synced") {
				frm.set_intro(__("This form is locked. Data fields cannot be edited."), "green");
			} else if (status === "Rejected") {
				frm.set_intro(__("This form has been rejected. Employee can re-submit via the onboarding page."), "orange");
			}
		}
	},
});
