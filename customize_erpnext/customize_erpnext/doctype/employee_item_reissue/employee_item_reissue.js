// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Item Reissue", {
    employee: function(frm) {
        // Chỉ thực hiện nếu có employee
        if (frm.doc.employee) {
            console.log("Đang tính toán số lần cấp phát thẻ nhân viên cho:", frm.doc.employee);
            
            // Kiểm tra đơn đã submit trước đó VÀ có đánh dấu employee_card
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Employee Item Reissue",
                    filters: {
                        employee: frm.doc.employee,
                        employee_card: 1, // Chỉ đếm đơn có đánh dấu employee_card
                        docstatus: 1 // Chỉ đếm đơn đã submit
                    },
                    fields: ["name"],
                    limit_page_length: 1000
                },
                callback: function(r) {
                    // Tính số lần cấp phát thẻ
                    var previous_count = r.message ? r.message.length : 0;
                    
                    // Đếm đơn hiện tại nếu có đánh dấu employee_card
                    var current_count = frm.doc.employee_card ? 1 : 0;
                    
                    // Tổng số lần cấp phát = số đơn đã tồn tại + đơn hiện tại (nếu có đánh dấu)
                    var total_count = previous_count + current_count;
                    
                    console.log("Số đơn thẻ đã submit trước đó:", previous_count);
                    console.log("Đơn hiện tại có thẻ:", current_count);
                    console.log("Tổng số lần cấp phát thẻ:", total_count);
                    
                    frm.set_value("reissue_count", total_count);
                    
                    // Hiển thị thông báo nếu đã có cấp phát trước đó
                    if (previous_count > 0) {
                        frappe.show_alert({
                            message: __("Nhân viên này đã được cấp thẻ " + previous_count + " lần trước đó"),
                            indicator: 'orange'
                        }, 5);
                    }
                }
            });
        } else {
            // Reset nếu không có employee
            frm.set_value("reissue_count", 0);
        }
    },
    
    // Cập nhật lại khi thay đổi trạng thái employee_card
    employee_card: function(frm) {
        if (frm.doc.employee) {
            // Gọi lại hàm employee để tính toán lại
            frm.trigger("employee");
        }
    }
});