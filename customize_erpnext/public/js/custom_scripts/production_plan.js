frappe.ui.form.on('Production Plan', {
    custom_include_lost_percent_in_bom: function (frm) {
        // Khi giá trị custom_include_lost_percent_in_bom thay đổi, gọi hàm setup_button
        frm.trigger('setup_button');
    },

    refresh: function (frm) {
        // Khi form được refresh, gọi hàm setup_button
        frm.trigger('setup_button');
        frm.page.buttons.forEach(btn => {
            if (btn.text === "Get Items for Material Request") {
                btn.text("Get Raw Materials for Purchase & Customer Provided");
            }
        });
    },

    setup_button: function (frm) {
        frm.doc.set
        console.log("Setting up button with custom_include_lost_percent_in_bom =", frm.doc.custom_include_lost_percent_in_bom);

        // Đảm bảo rằng button get_items_for_mr tồn tại
        if (!frm.get_field('get_items_for_mr') || !frm.get_field('get_items_for_mr').$input) {
            console.log("Could not find get_items_for_mr button");
            return;
        }

        // Đầu tiên, loại bỏ tất cả event handler hiện tại để tránh duplicate
        frm.get_field('get_items_for_mr').$input.off('click');

        if (frm.doc.custom_include_lost_percent_in_bom) {
            // Nếu custom_include_lost_percent_in_bom = 1, gắn event handler tùy chỉnh
            console.log("Attaching custom handler for get_items_for_mr button");

            frm.get_field('get_items_for_mr').$input.on('click', function () {
                console.log("Custom button handler triggered - Using lost percentage");

                // Gọi API tùy chỉnh với hỗ trợ cho tỷ lệ hao hụt
                frappe.call({
                    method: "customize_erpnext.api.production_plan.get_items_for_material_requests",
                    args: {
                        doc: frm.doc,
                        warehouses: frm.doc.for_warehouse ? [{
                            warehouse: frm.doc.for_warehouse
                        }] : []
                    },
                    callback: function (r) {
                        console.log("Received response from customized function");
                        if (r.message) {
                            frm.set_value("mr_items", []);
                            r.message.forEach(row => {
                                let d = frm.add_child("mr_items");
                                for (let field in row) {
                                    if (field !== "name") {
                                        d[field] = row[field];
                                    }
                                }
                            });
                        }
                        refresh_field("mr_items");
                    }
                });
            });

            console.log("Successfully attached custom click handler to get_items_for_mr button");
        } else {
            // Nếu custom_include_lost_percent_in_bom = 0, sử dụng API tùy chỉnh nhưng không áp dụng hao hụt
            console.log("Attaching modified default handler for get_items_for_mr button");

            frm.get_field('get_items_for_mr').$input.on('click', function () {
                console.log("Modified default button handler triggered - Not using lost percentage");

                // Gọi API tùy chỉnh nhưng không áp dụng hao hụt
                frappe.call({
                    method: "customize_erpnext.api.production_plan.get_items_for_material_requests_default",
                    args: {
                        doc: frm.doc,
                        warehouses: frm.doc.for_warehouse ? [{
                            warehouse: frm.doc.for_warehouse
                        }] : []
                    },
                    callback: function (r) {
                        console.log("Received response from default function with warehouse handling");
                        if (r.message) {
                            frm.set_value("mr_items", []);
                            r.message.forEach(row => {
                                let d = frm.add_child("mr_items");
                                for (let field in row) {
                                    if (field !== "name") {
                                        d[field] = row[field];
                                    }
                                }
                            });
                        }
                        refresh_field("mr_items");
                    }
                });
            });

            console.log("Successfully attached modified default click handler to get_items_for_mr button");
        }
    }
});