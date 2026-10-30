// File này nạp SAU employee_checkin_list.js của HRMS (hook doctype_list_js), nên phải
// dựng tiếp từ cấu hình của HRMS chứ không gán đè — bản cũ gán đè làm mất cả nhãn
// Off-Shift lẫn "Fetch Shifts".
//
// Cố ý KHÔNG gọi onload/primary_action/before_render của HRMS (từ v16.51, PR #5089):
// chúng thêm nút "Add Checkin for Another Employee" và nút tự Check In/Out. Bổ sung giờ
// phải đi qua Attendance Request (có duyệt, có lý do, tự tính lại công); HRMS cũng đã
// đặt in_create = 1 nên nút Add gốc không hiện.
//
// Nút "Bulk Update Employee Checkin Fields" đã bỏ (30/10/2026): engine tính công gọi
// bulk_update_employee_checkin ở STEP 2 mỗi lần chạy, nút chỉ làm lại việc đó mà không
// tính lại công.
(() => {
	const hrms_settings = frappe.listview_settings['Employee Checkin'] || {};

	frappe.listview_settings['Employee Checkin'] = {
		add_fields: hrms_settings.add_fields,
		get_indicator: hrms_settings.get_indicator,
		onload: function (listview) {
			listview.page.add_action_item(__('Fetch Shifts'), () => {
				const checkins = listview.get_checked_items().map((checkin) => checkin.name);
				frappe.call({
					method: 'hrms.hr.doctype.employee_checkin.employee_checkin.bulk_fetch_shift',
					freeze: true,
					args: { checkins },
				});
			});
		}
	};
})();
