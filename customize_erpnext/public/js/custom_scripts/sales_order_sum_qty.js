// Thêm code này vào file sales_order.js trong Custom Script hoặc server_scripts
frappe.ui.form.on('Sales Order', {
    validate: function (frm) {
        // Tự động tính tổng khi validate form
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
        calculate_sum_by_sku(frm);
    },

    items_remove: function (frm) {
        calculate_sum_by_delivery_date(frm);
        calculate_sum_by_country(frm);
    },

    items_add: function (frm, cdt, cdn) {
        // Theo dõi sự thay đổi khi thêm dòng sản phẩm mới
        var item = locals[cdt][cdn];
        frappe.ui.form.on("Sales Order Item", "delivery_date", function (frm, cdt, cdn) {
            calculate_sum_by_delivery_date(frm);
        });
        frappe.ui.form.on("Sales Order Item", "qty", function (frm, cdt, cdn) {
            calculate_sum_by_delivery_date(frm);
            calculate_sum_by_country(frm);
            calculate_sum_by_sku(frm);
        });
        frappe.ui.form.on("Sales Order Item", "custom_export_to_country", function (frm, cdt, cdn) {
            calculate_sum_by_country(frm);
        });
        frappe.ui.form.on("Sales Order Item", "custom_sku", function (frm, cdt, cdn) {
            calculate_sum_by_sku(frm);
        });



    },
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
function calculate_sum_by_country(frm) {
    frm.doc.sum_by_country = [];
    let country_totals = {};
    // Lặp qua từng dòng trong Sales Order Items
    $.each(frm.doc.items || [], function (i, item) {
        if (item.custom_export_to_country) {
            let country = item.custom_export_to_country;
            if (country_totals[country]) {
                country_totals[country] += item.qty;
            } else {
                country_totals[country] = item.qty;
            }
        }
    });

    // Thêm dữ liệu vào child table
    $.each(country_totals, function (country, total_qty) {
        let row = frappe.model.add_child(frm.doc, "Sales Order Sum By Delivery Date", "sum_by_country");
        row.country = country;
        row.quantity = Math.round(total_qty);
    });
    frm.refresh_field("sum_by_country");
}
function calculate_sum_by_sku(frm) {
    frm.doc.sum_by_sku = [];
    let sku_totals = {};
    // Lặp qua từng dòng trong Sales Order Items
    $.each(frm.doc.items || [], function (i, item) {
        if (item.custom_sku) {
            let sku = item.custom_sku;
            if (sku_totals[sku]) {
                sku_totals[sku] += item.qty;
            } else {
                sku_totals[sku] = item.qty;

            }
        }
    });

    // Thêm dữ liệu vào child table
    $.each(sku_totals, function (custom_sku, total_qty) {
        let row = frappe.model.add_child(frm.doc, "Sales Order Sum By SKU", "sum_by_sku");
        row.sku = custom_sku;
        row.quantity = Math.round(total_qty);
    });
    frm.refresh_field("sum_by_sku");
}