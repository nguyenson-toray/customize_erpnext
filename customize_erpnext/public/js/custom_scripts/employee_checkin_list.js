frappe.listview_settings['Employee Checkin'] = {
	onload: function (listview) {
		listview.page.add_inner_button(__('Bulk Update Employee Checkin Fields'), function () {
			show_bulk_update_dialog(listview);
		});
	}
};

function show_bulk_update_dialog(listview) {
	let d = new frappe.ui.Dialog({
		title: __('Bulk Update Employee Checkin Fields'),
		fields: [
			{
				label: __('Date Range'),
				fieldname: 'date_range_section',
				fieldtype: 'Section Break'
			},
			{
				label: __('From Date'),
				fieldname: 'from_date',
				fieldtype: 'Date',
				default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
				reqd: 1
			},
			{
				fieldname: 'col_break_1',
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
				fieldname: 'info_section',
				fieldtype: 'Section Break'
			},
			{
				fieldname: 'info',
				fieldtype: 'HTML',
				options: `<div class="alert alert-info" style="margin:4px 0">
					<p class="mb-1"><strong>${__('This will update')}:</strong></p>
					<ul class="mb-1">
						<li>${__('Shift field (using fetch_shift)')}</li>
						<li>${__('Log Type (IN/OUT based on time)')}</li>
						<li>${__('Offshift flag')}</li>
					</ul>
					<p class="mb-0"><small class="text-muted">${__('Only checkins with missing shift or log_type will be updated.')}</small></p>
				</div>`
			}
		],
		size: 'small',
		primary_action_label: __('Update'),
		primary_action(values) {
			if (values.from_date > values.to_date) {
				frappe.msgprint({
					title: __('Invalid Date Range'),
					message: __('From Date cannot be greater than To Date'),
					indicator: 'red'
				});
				return;
			}

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
						d.hide();
						if (listview) listview.refresh();
					}
				},
				error: function () {
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
