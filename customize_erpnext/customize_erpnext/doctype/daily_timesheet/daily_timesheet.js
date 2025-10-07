// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Daily Timesheet", {
	refresh(frm) {
		// Add custom buttons
		if (!frm.is_new()) {
			frm.add_custom_button(__('Recalculate Timesheet'), function() {
				frappe.call({
					method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.recalculate_timesheet",
					args: {
						docname: frm.doc.name
					},
					callback: function(r) {
						if (!r.exc) {
							frm.reload_doc();
						}
					}
				});
			});
			
			frm.add_custom_button(__('Timesheet Algorithm'), function() {
				frm.trigger('show_algorithm_dialog');
			});
		}
		
		// Refresh additional info HTML and overtime details
		frm.trigger('refresh_additional_info_display');
		
		// Auto refresh overtime details when check-in/out changes
		if (frm.doc.check_in && frm.doc.check_out) {
			frm.trigger('update_overtime_details');
		}
	},
	
	refresh_additional_info_display(frm) {
		// Force refresh additional_info_html field display
		if (frm.doc.employee && frm.doc.attendance_date && !frm.is_new()) {
			frappe.call({
				method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.get_additional_info_html",
				args: {
					docname: frm.doc.name
				},
				callback: function(r) {
					if (r.message) {
						frm.set_df_property('additional_info_html', 'options', r.message);
						frm.refresh_field('additional_info_html');
					}
				}
			});
		} else if (frm.doc.employee && frm.doc.attendance_date) {
			// For new documents, try to generate additional info HTML directly
			setTimeout(() => {
				frm.refresh_field('additional_info_html');
			}, 500);
		}
	},
	
	
	employee(frm) {
		// Auto-populate employee related fields
		if (frm.doc.employee) {
			frappe.db.get_value("Employee", frm.doc.employee, 
				["employee_name", "department", "custom_section", "custom_group"], 
				function(r) {
					if (r) {
						frm.set_value("employee_name", r.employee_name);
						frm.set_value("department", r.department);
						frm.set_value("custom_section", r.custom_section);
						frm.set_value("custom_group", r.custom_group);
						
						// Refresh additional info display when employee changes
						if (frm.doc.attendance_date) {
							frm.trigger('refresh_additional_info_display');
						}
					}
				}
			);
		}
	},
	
	attendance_date(frm) {
		// Auto-calculate when date changes and refresh additional info
		if (frm.doc.employee && frm.doc.attendance_date && !frm.is_new()) {
			frm.call('calculate_all_fields').then(() => {
				frm.trigger('refresh_additional_info_display');
			});
		} else if (frm.doc.employee && frm.doc.attendance_date) {
			// For new documents, just refresh additional info display
			frm.trigger('refresh_additional_info_display');
		}
	},
	
	update_overtime_details(frm) {
		// Update overtime details display
		if (frm.doc.actual_overtime || frm.doc.approved_overtime) {
			let html = `
				<div class="overtime-summary">
					<div class="row">
						<div class="col-sm-4">
							<label>Actual Overtime:</label>
							<div>${frm.doc.actual_overtime || 0} hours</div>
						</div>
						<div class="col-sm-4">
							<label>Registered Overtime:</label>
							<div>${frm.doc.approved_overtime || 0} hours</div>
							<small style="color: #666;">(từ registration đã submit)</small>
						</div>
						<div class="col-sm-4">
							<label><strong>Final Overtime:</strong></label>
							<div><strong>${frm.doc.overtime_hours || 0} hours</strong></div>
						</div>
					</div>
				</div>
			`;
			frm.set_df_property('overtime_details_html', 'options', html);
		}
	},
	
	show_algorithm_dialog() {
		// Get constants from server first
		frappe.call({
			method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.get_algorithm_constants",
			callback: function(r) {
				if (r.message) {
					const constants = r.message;
					
					// Create and show algorithm explanation dialog
					let dialog = new frappe.ui.Dialog({
						title: 'Timesheet Algorithm - Thuật Toán Tính Giờ Làm Việc & Tăng Ca',
						size: 'large',
						fields: [
							{
								fieldtype: 'HTML',
								options: `
									<div style="padding: 15px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
										<div style="margin-bottom: 20px;">
											<h4 style="color: #2e7d32; margin-bottom: 10px;">🏢 Ca Làm Việc</h4>
											<ul style="margin-left: 20px;">
												<li><strong>Day Shift:</strong> 8:00-17:00, nghỉ trưa 12:00-13:00</li>
												<li><strong>Canteen:</strong> 7:00-16:00, nghỉ trưa 11:00-12:00</li>
												<li><strong>Shift 1:</strong> 6:00-14:00 (không có OT)</li>
												<li><strong>Shift 2:</strong> 14:00-22:00 (không có OT)</li>
											</ul>
										</div>
										
										<div style="margin-bottom: 20px;">
											<h4 style="color: #1565c0; margin-bottom: 10px;">⏰ Tính Giờ Làm Việc (Working Hours)</h4>
											<ul style="margin-left: 20px;">
												<li><strong>Buổi sáng:</strong> từ bắt đầu ca đến giờ nghỉ trưa</li>
												<li><strong>Buổi chiều:</strong> từ hết nghỉ trưa đến tan ca</li>
												<li><strong>Trường hợp đặc biệt:</strong> Check in trước ca & check out trước nghỉ trưa → Working hours = Check out - Bắt đầu ca</li>
												<li><strong>Ngưỡng tối thiểu:</strong> Working hours < ${constants.MIN_MINUTES_WORKING_HOURS} phút → Set = 0</li>
												<li><strong>Filter checkin:</strong> Các lần chấm công < ${constants.MIN_MINUTES_CHECKIN_FILTER} phút sẽ được filter</li>
												<li><strong>Quyền lợi thai sản:</strong> Được về sớm 1 giờ mà vẫn tính đủ giờ</li>
											</ul>
										</div>
										
										<div style="margin-bottom: 20px;">
											<h4 style="color: #e65100; margin-bottom: 10px;">🚀 Tính Tăng Ca (Overtime)</h4>
											<ul style="margin-left: 20px;">
												<li><strong>OT trước ca:</strong> Check in sớm hơn ca + có đăng ký OT (tối thiểu ${constants.MIN_MINUTES_PRE_SHIFT_OT} phút)</li>
												<li><strong>OT sau ca:</strong> Check out trễ hơn tan ca (tối thiểu ${constants.MIN_MINUTES_OT} phút)</li>
												<li><strong>Final OT = min(Actual OT, Registered OT)</strong></li>
												<li><strong>Chủ nhật:</strong> Working hours chuyển thành Actual OT</li>
											</ul>
										</div>
										
										<div style="margin-bottom: 20px;">
											<h4 style="color: #7b1fa2; margin-bottom: 10px;">💰 Hệ Số Tăng Ca</h4>
											<ul style="margin-left: 20px;">
												<li><strong>Ngày thường (T2-T7):</strong> 1.5x</li>
												<li><strong>Chủ nhật:</strong> 2.0x</li>
												<li><strong>Ngày lễ:</strong> 3.0x (chưa implement)</li>
											</ul>
										</div>
										
										<div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin-top: 20px;">
											<h4 style="color: #d84315; margin-bottom: 10px;">📋 Các Trạng Thái</h4>
											<ul style="margin-left: 20px;">
												<li><strong>Absent:</strong> Không có check-in</li>
												<li><strong>Present:</strong> Có check-in, không OT</li>
												<li><strong>Present + OT:</strong> Có check-in và có OT</li>
												<li><strong>Sunday:</strong> Làm việc vào Chủ nhật</li>
											</ul>
										</div>
										
										<div style="background: #e8f5e8; padding: 15px; border-radius: 8px; margin-top: 20px; border: 1px solid #4caf50;">
											<h4 style="color: #2e7d32; margin-bottom: 10px;">⚙️ Constants Hiện Tại</h4>
											<div style="font-family: monospace; font-size: 12px;">
												<div><strong>MIN_MINUTES_OT:</strong> ${constants.MIN_MINUTES_OT} phút</div>
												<div><strong>MIN_MINUTES_WORKING_HOURS:</strong> ${constants.MIN_MINUTES_WORKING_HOURS} phút</div>
												<div><strong>MIN_MINUTES_PRE_SHIFT_OT:</strong> ${constants.MIN_MINUTES_PRE_SHIFT_OT} phút</div>
												<div><strong>MIN_MINUTES_CHECKIN_FILTER:</strong> ${constants.MIN_MINUTES_CHECKIN_FILTER} phút</div>
											</div>
										</div>
									</div>
								`
							}
						],
						primary_action_label: 'Đóng',
						primary_action() {
							dialog.hide();
						}
					});
					
					dialog.show();
				}
			}
		});
	}
});


// Report button for Monthly Timesheet
frappe.ui.form.on("Daily Timesheet", {
	onload: function(frm) {
		frm.add_custom_button(__('Monthly Report'), function() {
			frappe.set_route('query-report', 'Monthly Timesheet Report');
		}, __('Reports'));
	}
});
