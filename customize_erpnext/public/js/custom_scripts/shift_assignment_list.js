/**
 * Shift Assignment List - add "Bulk Create" action.
 *
 * Lets a user create many Shift Assignment records at once, filtering targets
 * either by an explicit list of employees or by Employee Group (custom_group).
 */

const _original_shift_assignment_listview = frappe.listview_settings["Shift Assignment"] || {};

frappe.listview_settings["Shift Assignment"] = Object.assign({}, _original_shift_assignment_listview, {
	onload: function (list_view) {
		if (_original_shift_assignment_listview.onload) {
			_original_shift_assignment_listview.onload.call(this, list_view);
		}
		if (frappe.perm.has_perm("Shift Assignment", 0, "create")) {
			list_view.page.add_inner_button(__("Bulk Create"), function () {
				show_bulk_create_shift_assignment(list_view);
			});
		}
	},
});

function show_bulk_create_shift_assignment(list_view) {
	const dialog = new frappe.ui.Dialog({
		title: __("Bulk Create Shift Assignment"),
		size: "large",
		fields: [
			{
				fieldtype: "Link",
				fieldname: "shift_type",
				label: __("Shift Type"),
				options: "Shift Type",
				reqd: 1,
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Link",
				fieldname: "company",
				label: __("Company"),
				options: "Company",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{
				fieldtype: "Section Break",
				label: __("Period"),
			},
			{
				fieldtype: "Date",
				fieldname: "start_date",
				label: __("Start Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Date",
				fieldname: "end_date",
				label: __("End Date (optional)"),
				description: __("Leave empty for an open-ended assignment"),
			},
			{
				fieldtype: "Section Break",
				label: __("Target Employees"),
			},
			{
				fieldtype: "Select",
				fieldname: "filter_by",
				label: __("Filter By"),
				options: ["Employee", "Employee Group"].join("\n"),
				default: "Employee",
				onchange: function () {
					const by = dialog.get_value("filter_by");
					dialog.set_df_property("employees", "hidden", by !== "Employee");
					dialog.set_df_property("employees", "reqd", by === "Employee");
					dialog.set_df_property("custom_group", "hidden", by !== "Employee Group");
					dialog.set_df_property("custom_group", "reqd", by === "Employee Group");
				},
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "MultiSelectList",
				fieldname: "employees",
				label: __("Employees"),
				reqd: 1,
				get_data: function (txt) {
					return frappe.db.get_link_options("Employee", txt, { status: "Active" });
				},
			},
			{
				fieldtype: "Link",
				fieldname: "custom_group",
				label: __("Employee Group"),
				options: "Group",
				hidden: 1,
			},
			{
				fieldtype: "Section Break",
			},
			{
				fieldtype: "Check",
				fieldname: "skip_existing",
				label: __("Skip employees with an overlapping active assignment"),
				default: 1,
			},
		],
		primary_action_label: __("Create"),
		primary_action: function (values) {
			if (values.end_date && values.end_date < values.start_date) {
				frappe.msgprint(__("End Date cannot be before Start Date"));
				return;
			}

			const by_group = values.filter_by === "Employee Group";
			if (by_group && !values.custom_group) {
				frappe.msgprint(__("Please select an Employee Group"));
				return;
			}
			if (!by_group && (!values.employees || !values.employees.length)) {
				frappe.msgprint(__("Please select at least one Employee"));
				return;
			}

			const target_desc = by_group
				? __('group "{0}"', [values.custom_group])
				: __("{0} selected employee(s)", [values.employees.length]);

			frappe.confirm(
				__("Create Shift Assignment ({0}) for {1} starting {2}?", [
					values.shift_type,
					target_desc,
					frappe.datetime.str_to_user(values.start_date),
				]),
				function () {
					frappe.call({
						method: "customize_erpnext.api.shift_assignment.bulk_assign.bulk_create_shift_assignment",
						args: {
							shift_type: values.shift_type,
							start_date: values.start_date,
							end_date: values.end_date || null,
							company: values.company,
							employees: by_group ? null : JSON.stringify(values.employees),
							custom_group: by_group ? values.custom_group : null,
							skip_existing: values.skip_existing ? 1 : 0,
						},
						freeze: true,
						freeze_message: __("Creating Shift Assignments..."),
						callback: function (r) {
							if (r.exc || !r.message) {
								frappe.msgprint({
									title: __("Error"),
									message: __("Failed to create Shift Assignments. Check Error Log."),
									indicator: "red",
								});
								return;
							}
							dialog.hide();
							show_bulk_create_result(r.message);
							list_view.refresh();
						},
					});
				}
			);
		},
	});

	// Apply initial visibility based on default filter_by = "Employee"
	dialog.set_df_property("custom_group", "hidden", true);

	dialog.show();
}

function show_bulk_create_result(result) {
	const errors = result.errors || [];
	let errors_html = "";
	if (errors.length) {
		const rows = errors
			.slice(0, 20)
			.map(
				(e) =>
					`<tr><td>${frappe.utils.escape_html(e.employee)}</td>` +
					`<td>${frappe.utils.escape_html(e.error)}</td></tr>`
			)
			.join("");
		errors_html = `
			<div class="mt-3">
				<strong>${__("Skipped / Errors")}:</strong>
				<table class="table table-bordered table-sm mt-2">
					<thead><tr><th>${__("Employee")}</th><th>${__("Reason")}</th></tr></thead>
					<tbody>${rows}</tbody>
				</table>
				${errors.length > 20 ? `<small class="text-muted">${__("...and {0} more", [errors.length - 20])}</small>` : ""}
			</div>`;
	}

	frappe.msgprint({
		title: __("Bulk Create Completed"),
		indicator: result.created > 0 ? "green" : "orange",
		message: `
			<div>
				<div>${__("Created")}: <strong>${result.created}</strong></div>
				<div>${__("Skipped")}: <strong>${result.skipped}</strong></div>
			</div>
			${errors_html}
		`,
		wide: true,
	});
}
