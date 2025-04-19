// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Entry Multi Work Orders Table Material", {
    refresh(frm) {
        // Chạy khi refresh child form
    },

    required_qty: function (frm, cdt, cdn) {
        // Xử lý validation khi người dùng thay đổi số lượng trực tiếp trong bảng
        let row = locals[cdt][cdn];

        // Lấy giá trị gốc
        let initial_qty = row.__original_required_qty;

        // Nếu không có giá trị gốc, sử dụng giá trị hiện tại
        if (!initial_qty) {
            row.__original_required_qty = row.required_qty;
            return;
        }

        // Chỉ cho phép tăng số lượng, không cho phép giảm
        if (flt(row.required_qty) < flt(initial_qty)) {
            frappe.msgprint(__(`Cannot decrease quantity for ${row.item_code}. 
                Original: ${initial_qty}, New: ${row.required_qty}`));

            // Reset về giá trị ban đầu
            frappe.model.set_value(cdt, cdn, 'required_qty', initial_qty);
        }
    }
});

// Helper function to safely convert to float
function flt(val) {
    return parseFloat(val || 0);
}