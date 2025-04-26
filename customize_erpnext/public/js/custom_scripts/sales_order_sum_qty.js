// Đăng ký sự kiện cho Sales Order
frappe.ui.form.on('Sales Order', {
    validate: function (frm) {
        // Tính tổng khi validate form
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
        calculate_sum_by_sku(frm);
    },

    refresh: function (frm) {
        // Tính tổng khi refresh form
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
        calculate_sum_by_sku(frm);
    },

    items_remove: function (frm) {
        // Tính tổng khi xóa item
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
        calculate_sum_by_sku(frm);
    }
});

// Đăng ký sự kiện cho Sales Order Item
frappe.ui.form.on('Sales Order Item', {
    // Xử lý khi thay đổi item_code
    item_code: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];

        if (!row.item_code) {
            // Nếu xóa item_code, reset các trường liên quan
            frappe.model.set_value(cdt, cdn, "delivery_date", null);
            frappe.model.set_value(cdt, cdn, "custom_export_to_country", "");
            frappe.model.set_value(cdt, cdn, "custom_sku", "");
            frappe.model.set_value(cdt, cdn, "qty", 0);
        }

        // Cập nhật các bảng tổng hợp
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
        calculate_sum_by_sku(frm);
    },

    // Xử lý khi thay đổi ngày giao hàng
    delivery_date: function (frm, cdt, cdn) {
        calculate_sum_by_delivery_date(frm);
    },

    // Xử lý khi thay đổi số lượng
    qty: function (frm, cdt, cdn) {
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
        calculate_sum_by_sku(frm);
    },

    // Xử lý khi thay đổi country
    custom_export_to_country: function (frm, cdt, cdn) {
        calculate_sum_by_country(frm);
    },

    // Xử lý khi thay đổi SKU
    custom_sku: function (frm, cdt, cdn) {
        calculate_sum_by_sku(frm);
    }
});

// Hàm tính tổng theo ngày giao hàng
function calculate_sum_by_delivery_date(frm) {
    frm.doc.sum_by_delivery_date = [];
    let delivery_date_totals = {};

    // Lặp qua từng dòng trong Sales Order Items
    $.each(frm.doc.items || [], function (i, item) {
        // Chỉ tính các item có item_code và delivery_date
        if (item.item_code && item.delivery_date) {
            let date = item.delivery_date;

            if (!delivery_date_totals[date]) {
                delivery_date_totals[date] = 0;
            }

            delivery_date_totals[date] += flt(item.qty) || 0;
        }
    });

    // Thêm dữ liệu vào child table
    $.each(delivery_date_totals, function (delivery_date, total_qty) {
        let row = frappe.model.add_child(frm.doc, "Sales Order Sum By Delivery Date", "sum_by_delivery_date");
        row.delivery_date = delivery_date;
        row.quantity = flt(total_qty, precision("quantity", row));
    });

    frm.refresh_field("sum_by_delivery_date");
}

// Hàm tính tổng theo country
function calculate_sum_by_country(frm) {
    frm.doc.sum_by_country = [];
    let country_totals = {};

    // Lặp qua từng dòng trong Sales Order Items
    $.each(frm.doc.items || [], function (i, item) {
        // Chỉ tính các item có item_code và country
        if (item.item_code && item.custom_export_to_country) {
            let country = item.custom_export_to_country;

            if (!country_totals[country]) {
                country_totals[country] = 0;
            }

            country_totals[country] += flt(item.qty) || 0;
        }
    });

    // Thêm dữ liệu vào child table
    $.each(country_totals, function (country, total_qty) {
        let row = frappe.model.add_child(frm.doc, "Sales Order Sum By Country", "sum_by_country");
        row.country = country;
        row.quantity = flt(total_qty, precision("quantity", row));
    });

    frm.refresh_field("sum_by_country");
}

// Hàm tính tổng theo SKU
function calculate_sum_by_sku(frm) {
    frm.doc.sum_by_sku = [];
    let sku_totals = {};

    // Lặp qua từng dòng trong Sales Order Items
    $.each(frm.doc.items || [], function (i, item) {
        // Chỉ tính các item có item_code và SKU
        if (item.item_code && item.custom_sku) {
            let sku = item.custom_sku;

            if (!sku_totals[sku]) {
                sku_totals[sku] = 0;
            }

            sku_totals[sku] += flt(item.qty) || 0;
        }
    });

    // Thêm dữ liệu vào child table
    $.each(sku_totals, function (sku, total_qty) {
        let row = frappe.model.add_child(frm.doc, "Sales Order Sum By SKU", "sum_by_sku");
        row.sku = sku;
        row.quantity = flt(total_qty, precision("quantity", row));
    });

    frm.refresh_field("sum_by_sku");
}