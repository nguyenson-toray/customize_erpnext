// Thêm code này vào file sales_order.js trong Custom Script hoặc server_scripts
frappe.ui.form.on('Sales Order', {
    refresh: function (frm) {
        if (frm.doc.sum_by_delivery_date = []) {
            calculate_sum_by_delivery_date(frm);
        }
    },

    validate: function (frm) {
        // Tự động tính tổng khi validate form
        calculate_sum_by_delivery_date(frm);
    },

    items_remove: function (frm) {
        // Cập nhật khi xóa dòng sản phẩm
        calculate_sum_by_delivery_date(frm);
    },

    items_add: function (frm, cdt, cdn) {
        // Theo dõi sự thay đổi khi thêm dòng sản phẩm mới
        var item = locals[cdt][cdn];
        frappe.ui.form.on("Sales Order Item", "delivery_date", function (frm, cdt, cdn) {
            calculate_sum_by_delivery_date(frm);
        });

        frappe.ui.form.on("Sales Order Item", "qty", function (frm, cdt, cdn) {
            calculate_sum_by_delivery_date(frm);
        });
    },

    after_save: function (frm) {
        // Đảm bảo dữ liệu được cập nhật sau khi lưu
        calculate_sum_by_delivery_date(frm);
    }
});

// Hàm để tính tổng số lượng theo ngày giao hàng
function calculate_sum_by_delivery_date(frm) {
    frm.doc.sum_by_delivery_date = [];
    let delivery_date_totals = {};
    // Lặp qua từng dòng trong Sales Order Items
    $.each(frm.doc.items || [], function (i, item) {
        if (item.delivery_date) {
            let date = item.delivery_date;
            if (delivery_date_totals[date]) {
                delivery_date_totals[date] += item.qty;
            } else {
                delivery_date_totals[date] = item.qty;

            }
        }
    });

    // Thêm dữ liệu vào child table
    $.each(delivery_date_totals, function (delivery_date, total_qty) {
        let row = frappe.model.add_child(frm.doc, "Sales Order Sum By Delivery Date", "sum_by_delivery_date");
        row.delivery_date = delivery_date;
        row.quantity = Math.round(total_qty);
    });
    frm.refresh_field("sum_by_delivery_date");
}