/**
 * Enhancement cho Production Plan để hiển thị rõ ràng hơn việc áp dụng % hao hụt
 */

frappe.ui.form.on('Production Plan', {

    custom_include_lost_percent_in_bom: function (frm) {
        console.log("-----------custom_include_lost_percent_in_bom changed-----------New value:", frm.doc.custom_include_lost_percent_in_bom);
        frm.trigger('setup_button');
        frm.trigger('setup_lost_percentage_indicator');
    },

    refresh: function (frm) {
        console.log("-----------Production Plan refresh-----------");
        frm.trigger('setup_button');
        frm.trigger('setup_lost_percentage_indicator');
    },

    // Thêm indicator để hiển thị trạng thái
    setup_lost_percentage_indicator: function (frm) {
        // Remove existing indicator
        frm.page.clear_indicator();

        if (frm.doc.custom_include_lost_percent_in_bom) {
            frm.page.set_indicator(__('Lost % Applied'), 'green');

            // Add tooltip or help text
            if (!frm.get_field('get_items_for_mr').description) {
                frm.get_field('get_items_for_mr').df.description =
                    __('Click to get items with 3% loss percentage applied to quantities');
                frm.refresh_field('get_items_for_mr');
            }
        } else {
            frm.page.set_indicator(__('Standard Calculation'), 'blue');

            if (frm.get_field('get_items_for_mr').df.description) {
                frm.get_field('get_items_for_mr').df.description =
                    __('Click to get items with standard BOM quantities');
                frm.refresh_field('get_items_for_mr');
            }
        }
    },

    setup_button: function (frm) {
        console.log("-----------setup_button'-----------");
        // ===== THAY ĐỔI LABEL CỦA BUTTON =====
        const newButtonLabel = "Get Raw Materials for Purchase & Customer Provided";

        // Thay đổi text của button
        frm.get_field('get_items_for_mr').$input.text(newButtonLabel);

        // Nếu button có attribute value, cũng cập nhật luôn
        if (frm.get_field('get_items_for_mr').$input.attr('type') === 'button') {
            frm.get_field('get_items_for_mr').$input.val(newButtonLabel);
        }

        // Cập nhật title cho tooltip
        frm.get_field('get_items_for_mr').$input.attr('title', newButtonLabel);

        console.log("Button label updated to:", newButtonLabel);
        setTimeout(function () {
            console.log("Setting up button with custom_include_lost_percent_in_bom =", frm.doc.custom_include_lost_percent_in_bom);

            // Đảm bảo rằng button get_items_for_mr tồn tại
            if (!frm.get_field('get_items_for_mr') || !frm.get_field('get_items_for_mr').$input) {
                console.log("Could not find get_items_for_mr button");
                return;
            }

            // Đầu tiên, loại bỏ tất cả event handler hiện tại để tránh duplicate
            frm.get_field('get_items_for_mr').$input.off('click');

            if (frm.doc.custom_include_lost_percent_in_bom) {
                console.log("Attaching custom handler for get_items_for_mr button");

                frm.get_field('get_items_for_mr').$input.on('click', function () {
                    console.log("Custom button handler triggered - Using lost percentage");

                    // Show loading message
                    frappe.show_alert({
                        message: __('Calculating items with 3% loss percentage...'),
                        indicator: 'blue'
                    }, 3);

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
                                refresh_field("mr_items");

                                // Show success message with details
                                frappe.show_alert({
                                    message: __(`✅ ${r.message.length} items added with 3% loss percentage applied`),
                                    indicator: 'green'
                                }, 5);

                                // Optional: Show calculation summary
                                frm.trigger('show_calculation_summary');
                            }
                        },
                        error: function (err) {
                            frappe.show_alert({
                                message: __('Error calculating items with loss percentage'),
                                indicator: 'red'
                            }, 5);
                        }
                    });
                });

                console.log("Successfully attached custom click handler to get_items_for_mr button");
            } else {
                // Nếu custom_include_lost_percent_in_bom = 0, sử dụng API tùy chỉnh nhưng không áp dụng hao hụt
                console.log("Attaching modified default handler for get_items_for_mr button");

                frm.get_field('get_items_for_mr').$input.on('click', function () {
                    console.log("Modified default button handler triggered - Not using lost percentage");

                    // Show loading message
                    frappe.show_alert({
                        message: __('Calculating items with standard BOM quantities...'),
                        indicator: 'blue'
                    }, 3);
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
                                refresh_field("mr_items");

                                // Show success message
                                frappe.show_alert({
                                    message: __(`✅ ${r.message.length} items added with standard quantities`),
                                    indicator: 'green'
                                }, 5);
                            }
                        },
                        error: function (err) {
                            frappe.show_alert({
                                message: __('Error calculating items'),
                                indicator: 'red'
                            }, 5);
                        }
                    });
                });

                console.log("Successfully attached modified default click handler to get_items_for_mr button");
            }
        }, 100);
        console.log("Button setup completed");
    },

    // Optional: Show calculation summary
    show_calculation_summary: function (frm) {
        if (!frm.doc.mr_items || frm.doc.mr_items.length === 0) return;

        // Count items and total quantity
        const totalItems = frm.doc.mr_items.length;
        const totalQty = frm.doc.mr_items.reduce((sum, item) => sum + (item.quantity || 0), 0);

        // Create summary message
        const summary = `
            <div style="font-size: 12px; color: #666; margin-top: 10px;">
                <strong>Calculation Summary:</strong><br>
                • Total Items: ${totalItems}<br>
                • Total Quantity: ${totalQty.toFixed(2)}<br>
                • Loss Percentage Applied: ${frm.doc.custom_include_lost_percent_in_bom ? '3%' : 'None'}<br>
                • Method: ${frm.doc.custom_include_lost_percent_in_bom ? 'Custom with Loss' : 'Standard BOM'}
            </div>
        `;

        // Add to form if not exists
        if (!frm.fields_dict.mr_items.$wrapper.find('.calculation-summary').length) {
            frm.fields_dict.mr_items.$wrapper.append(summary);
        }
    }
});