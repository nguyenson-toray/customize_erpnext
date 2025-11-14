// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Trip", {
	refresh(frm) {
		// Set status indicator color
		if (frm.doc.status) {
			frm.page.set_indicator(frm.doc.status, {
				"Đang Đỗ": "gray",
				"Đang Chạy": "blue",
				"Hoàn Thành": "green"
			}[frm.doc.status]);
		}

		// Add Start button
		if (!frm.doc.start_time) {
			frm.add_custom_button(__('Start Trip'), function () {
				show_start_trip_dialog(frm);
			}).addClass('btn-primary');
		}

		// Add Finish button
		if (frm.doc.start_time && !frm.doc.finish_time) {
			frm.add_custom_button(__('Finish Trip'), function () {
				show_finish_trip_dialog(frm);
			}).addClass('btn-success');
		}
	},

	vehicle_name(frm) {
		// Auto-populate vehicle info when vehicle is selected
		if (frm.doc.vehicle_name) {
			frappe.call({
				method: 'frappe.client.get',
				args: {
					doctype: 'Vehicle List',
					name: frm.doc.vehicle_name
				},
				callback: function (r) {
					if (r.message) {
						let vehicle = r.message;
						let vehicle_info = '';
						if (vehicle.model) vehicle_info += vehicle.model;
						if (vehicle.driver) vehicle_info += (vehicle_info ? ' - ' : '') + vehicle.driver;
						if (vehicle.number_of_seats) vehicle_info += (vehicle_info ? ' - ' : '') + vehicle.number_of_seats + ' ' + __('seats');
						frm.set_value('vehicle_info', vehicle_info);
					}
				}
			});
		}
	},

	finish_km(frm) {
		// Calculate total_km when finish_km is entered
		if (frm.doc.start_km && frm.doc.finish_km) {
			frm.set_value('total_km', frm.doc.finish_km - frm.doc.start_km);
		}
	},

	start_km(frm) {
		// Calculate total_km when start_km is entered
		if (frm.doc.start_km && frm.doc.finish_km) {
			frm.set_value('total_km', frm.doc.finish_km - frm.doc.start_km);
		}
	},

	daily_pickup(frm) {
		// Auto-fill locations and purpose when daily_pickup is checked
		if (frm.doc.daily_pickup) {
			// Uncheck daily_dropoff to ensure only one is selected
			if (frm.doc.daily_dropoff) {
				frm.set_value('daily_dropoff', 0);
			}

			// Get vehicle info
			if (frm.doc.vehicle_name) {
				frappe.call({
					method: 'frappe.client.get',
					args: {
						doctype: 'Vehicle List',
						name: frm.doc.vehicle_name
					},
					callback: function (r) {
						if (r.message) {
							let vehicle = r.message;
							// Daily pickup: from fixed_location_1 to fixed_location_2
							frm.set_value('start_location', vehicle.fixed_location_1 || '');
							frm.set_value('destination_location', vehicle.fixed_location_2 || '');
							frm.set_value('purpose', __('Daily employee pickup and dropoff'));
						}
					}
				});
			} else {
				frappe.msgprint(__('Vui lòng chọn xe trước'));
				frm.set_value('daily_pickup', 0);
			}
		}
	},

	daily_dropoff(frm) {
		// Auto-fill locations and purpose when daily_dropoff is checked
		if (frm.doc.daily_dropoff) {
			// Uncheck daily_pickup to ensure only one is selected
			if (frm.doc.daily_pickup) {
				frm.set_value('daily_pickup', 0);
			}

			// Get vehicle info
			if (frm.doc.vehicle_name) {
				frappe.call({
					method: 'frappe.client.get',
					args: {
						doctype: 'Vehicle List',
						name: frm.doc.vehicle_name
					},
					callback: function (r) {
						if (r.message) {
							let vehicle = r.message;
							// Daily dropoff: from fixed_location_2 to fixed_location_1
							frm.set_value('start_location', vehicle.fixed_location_2 || '');
							frm.set_value('destination_location', vehicle.fixed_location_1 || '');
							frm.set_value('purpose', __('Daily employee pickup and dropoff'));
						}
					}
				});
			} else {
				frappe.msgprint(__('Vui lòng chọn xe trước'));
				frm.set_value('daily_dropoff', 0);
			}
		}
	}
});

// Helper function to show Start Trip dialog with manual input
function show_start_trip_dialog(frm) {
	// Check if vehicle is selected
	if (!frm.doc.vehicle_name) {
		frappe.msgprint(__('Vui lòng chọn xe trước'));
		return;
	}

	// Get max km for this vehicle
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.vehicle_trip.vehicle_trip.get_max_km_for_vehicle',
		args: {
			vehicle_name: frm.doc.vehicle_name
		},
		callback: function (r) {
			let max_km = r.message?.max_km || 0;

			// Create dialog
			let d = new frappe.ui.Dialog({
				title: __('Bắt đầu chuyến đi'),
				fields: [
					{
						fieldname: 'km_info',
						fieldtype: 'HTML',
						options: max_km > 0
							? `<div class="alert alert-info" style="margin-bottom: 10px;">
								<i class="fa fa-info-circle"></i> ${__('Maximum km recorded')}: <strong>${max_km} km</strong>
							</div>`
							: `<div class="alert alert-warning" style="margin-bottom: 10px;">
								<i class="fa fa-info-circle"></i> ${__('This is the first trip for this vehicle - please enter the current odometer reading')}
							</div>`
					},
					{
						fieldname: 'start_km',
						fieldtype: 'Int',
						label: __('Số Km bắt đầu'),
						reqd: 1,
						default: max_km > 0 ? max_km : undefined,
						description: max_km > 0 ? __('Suggested: >= {0} km (can enter less if adding old trip)', [max_km]) : __('Enter current odometer reading')
					},
					{
						fieldname: 'start_time',
						fieldtype: 'Datetime',
						label: __('Thời gian bắt đầu'),
						reqd: 1,
						default: frappe.datetime.now_datetime()
					}
				],
				primary_action_label: __('Bắt đầu'),
				primary_action(values) {
					// Validate
					if (!values.start_km && values.start_km !== 0) {
						frappe.msgprint(__('Vui lòng nhập số km'));
						return;
					}

					// Set values
					frm.set_value('start_km', values.start_km);
					frm.set_value('start_time', values.start_time);

					// Save
					frm.save().then(() => {
						frm.reload_doc();
						frappe.show_alert({
							message: __('Chuyến đi đã bắt đầu'),
							indicator: 'green'
						});
					});

					d.hide();
				}
			});

			d.show();
		}
	});
}

// Helper function to show Finish Trip dialog with manual input
function show_finish_trip_dialog(frm) {
	// Check if vehicle is selected
	if (!frm.doc.vehicle_name) {
		frappe.msgprint(__('Vui lòng chọn xe trước'));
		return;
	}

	// Get max km for this vehicle
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.vehicle_trip.vehicle_trip.get_max_km_for_vehicle',
		args: {
			vehicle_name: frm.doc.vehicle_name
		},
		callback: function (r) {
			let max_km_db = r.message?.max_km || 0;
			let start_km = frm.doc.start_km || 0;
			let min_finish_km = Math.max(start_km, max_km_db);

			// Create dialog
			let d = new frappe.ui.Dialog({
				title: __('Hoàn thành chuyến đi'),
				fields: [
					{
						fieldname: 'km_info',
						fieldtype: 'HTML',
						options: `<div class="alert alert-info" style="margin-bottom: 10px;">
							<i class="fa fa-info-circle"></i>
							${__('Start km for this trip')}: <strong>${start_km} km</strong><br>
							${max_km_db > start_km ? `${__('Maximum km in system')}: <strong>${max_km_db} km</strong>` : ''}
						</div>`
					},
					{
						fieldname: 'finish_km',
						fieldtype: 'Int',
						label: __('Số Km kết thúc'),
						reqd: 1,
						default: min_finish_km > 0 ? min_finish_km : undefined,
						description: __('Must be > {0} km', [frm.doc.start_km]) + (min_finish_km > start_km ? ` (${__('suggested')}: >= ${min_finish_km} km)` : '')
					},
					{
						fieldname: 'finish_time',
						fieldtype: 'Datetime',
						label: __('Thời gian kết thúc'),
						reqd: 1,
						default: frappe.datetime.now_datetime()
					}
				],
				primary_action_label: __('Hoàn thành'),
				primary_action(values) {
					// Validate
					if (!values.finish_km && values.finish_km !== 0) {
						frappe.msgprint(__('Vui lòng nhập số km'));
						return;
					}
					if (values.finish_km < frm.doc.start_km) {
						frappe.msgprint(__('Số km kết thúc phải lớn hơn số km bắt đầu'));
						return;
					}

					// Set values
					frm.set_value('finish_km', values.finish_km);
					frm.set_value('finish_time', values.finish_time);

					// Save
					frm.save().then(() => {
						frm.reload_doc();
						frappe.show_alert({
							message: __('Chuyến đi đã hoàn thành'),
							indicator: 'green'
						});
					});

					d.hide();
				}
			});

			d.show();
		}
	});
}
