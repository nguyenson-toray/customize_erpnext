// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings['Vehicle Trip'] = {
	onload: function(listview) {
		// Check if current user has Driver role
		frappe.call({
			method: 'frappe.client.get_value',
			args: {
				doctype: 'User',
				filters: { name: frappe.session.user },
				fieldname: 'name'
			},
			callback: function(r) {
				// Get user roles
				let user_roles = frappe.user_roles || [];

				// Check if user is Driver (and not privileged)
				let is_driver = user_roles.includes('Driver');
				let is_privileged = user_roles.includes('System Manager') ||
								   user_roles.includes('HR Manager') ||
								   user_roles.includes('HR User') ||
								   frappe.session.user === 'Administrator';

				// If Driver and not privileged, filter by assignment
				if (is_driver && !is_privileged) {
					// Get trips assigned to current user
					frappe.call({
						method: 'frappe.client.get_list',
						args: {
							doctype: 'ToDo',
							filters: {
								reference_type: 'Vehicle Trip',
								allocated_to: frappe.session.user,
								status: 'Open'
							},
							fields: ['reference_name'],
							limit_page_length: 999999
						},
						callback: function(response) {
							if (response.message && response.message.length > 0) {
								// Extract trip names
								let assigned_trips = response.message.map(todo => todo.reference_name);

								// Apply filter to listview
								listview.filter_area.clear();
								listview.filter_area.add([
									['Vehicle Trip', 'name', 'in', assigned_trips]
								]);
								listview.refresh();

								// Show info message
								frappe.show_alert({
									message: __('Showing only trips assigned to you ({0} trips)', [assigned_trips.length]),
									indicator: 'blue'
								}, 5);
							} else {
								// No trips assigned
								listview.filter_area.clear();
								listview.filter_area.add([
									['Vehicle Trip', 'name', '=', 'NO_TRIPS_ASSIGNED_DUMMY_VALUE']
								]);
								listview.refresh();

								frappe.show_alert({
									message: __('No trips assigned to you'),
									indicator: 'orange'
								}, 5);
							}
						}
					});
				}
			}
		});
	},

	// Add custom filter indicator
	get_indicator: function(doc) {
		if (doc.status === 'Hoàn Thành') {
			return [__('Hoàn Thành'), 'green', 'status,=,Hoàn Thành'];
		} else if (doc.status === 'Đang Chạy') {
			return [__('Đang Chạy'), 'blue', 'status,=,Đang Chạy'];
		} else if (doc.status === 'Đang Đỗ') {
			return [__('Đang Đỗ'), 'gray', 'status,=,Đang Đỗ'];
		}
	},

	// Format list row
	formatters: {
		vehicle_name: function(value) {
			return value ? `<strong>${value}</strong>` : '';
		}
	}
};
