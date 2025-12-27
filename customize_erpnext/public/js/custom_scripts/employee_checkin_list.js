frappe.listview_settings['Employee Checkin'] = {
	onload: function (listview) {
		// Add Bulk Update action button
		listview.page.add_inner_button(__('🔄️ Bulk Update Employee Checkin Fields'), function () {
			show_bulk_update_dialog();
		});
	}
};

function show_bulk_update_dialog() {
	// Create dialog
	let d = new frappe.ui.Dialog({
		title: __('🔄️ Bulk Update Employee Checkin Fields'),
		fields: [
			{
				label: __('📅 Date Range'),
				fieldname: 'date_range_section',
				fieldtype: 'Section Break'
			},
			{
				label: __('From Date'),
				fieldname: 'from_date',
				fieldtype: 'Date',
				default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
				reqd: 1
			}, {
				fieldname: 'column_break',
				fieldtype: 'Column Break'
			},
			{
				label: __('To Date'),
				fieldname: 'to_date',
				fieldtype: 'Date',
				default: frappe.datetime.get_today(),
				reqd: 1
			},
			{
				fieldname: 'column_break',
				fieldtype: 'Section Break'
			},
			{
				label: __('Info'),
				fieldname: 'info',
				fieldtype: 'HTML',
				options: `<div class="text-muted small">
					<p><strong>ℹ️ This will update:</strong></p>
					<ul>
						<li>Shift field (using fetch_shift)</li>
						<li>Log Type (IN/OUT based on time)</li>
						<li>Offshift flag</li>
					</ul>
					<p class="text-warning"><strong>Note:</strong> Only checkins with missing shift or log_type will be updated.</p>
				</div>`
			}
		],
		size: 'small',
		primary_action_label: __('Update'),
		primary_action(values) {
			// Validate dates
			if (values.from_date > values.to_date) {
				frappe.msgprint({
					title: __('Invalid Date Range'),
					message: __('From Date cannot be greater than To Date'),
					indicator: 'red'
				});
				return;
			}

			// Call backend function
			frappe.call({
				method: 'customize_erpnext.overrides.employee_checkin.employee_checkin.bulk_update_employee_checkin',
				args: {
					from_date: values.from_date,
					to_date: values.to_date
				},
				freeze: true,
				freeze_message: __('Updating Employee Checkins...'),
				callback: function (r) {
					if (r.message !== undefined) {
						frappe.msgprint({
							title: __('Bulk Update Complete'),
							message: __('Successfully updated {0} employee checkin(s)', [r.message]),
							indicator: 'green'
						});

						// Refresh the list view
						cur_list.refresh();

						// Close dialog
						d.hide();
					}
				},
				error: function (r) {
					frappe.msgprint({
						title: __('Update Failed'),
						message: __('An error occurred while updating checkins. Please check the error log.'),
						indicator: 'red'
					});
				}
			});
		}
	});

	d.show();
}
