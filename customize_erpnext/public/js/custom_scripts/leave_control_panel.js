// Leave Control Panel — refresh danh sách khi bật/tắt checkbox "include employees who left".
//
// HRMS khai handler riêng cho TỪNG field lọc (company, branch, department, ...) để gọi
// `frm.trigger("get_employees")`. Custom field không nằm trong danh sách đó, nên nếu không
// thêm handler này thì tick vào checkbox danh sách vẫn y nguyên — HR sẽ tưởng nó không có
// tác dụng.
//
// Xem `overrides/leave_control_panel/leave_control_panel.md`.

frappe.ui.form.on("Leave Control Panel", {
	custom_include_employees_who_left(frm) {
		frm.trigger("get_employees");
	},
});
