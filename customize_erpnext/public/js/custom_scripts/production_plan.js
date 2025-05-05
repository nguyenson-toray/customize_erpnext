frappe.ui.form.on('Production Plan', {
    refresh: function (frm) {
        if (frm.doc.custom_include_lost_percent_in_bom) {
            // Add a delay to ensure the form is fully loaded
            setTimeout(function () {
                // Override the get_items_for_mr button click event
                if (frm.get_field('get_items_for_mr') && frm.get_field('get_items_for_mr').$input) {
                    frm.get_field('get_items_for_mr').$input.off('click');
                    frm.get_field('get_items_for_mr').$input.on('click', function () {
                        console.log("Button Get Raw Materials for Purchase clicked - Override working");

                        if (!frm.doc.for_warehouse) {
                            frm.trigger("toggle_for_warehouse");
                            frappe.throw(__("Select the Warehouse"));
                        }

                        // Call our customized function instead of the standard one
                        console.log("Calling customize_erpnext.api.production_plan.get_items_for_material_requests");
                        frappe.call({
                            method: "customize_erpnext.api.production_plan.get_items_for_material_requests",
                            args: {
                                doc: frm.doc,
                                warehouses: [{
                                    warehouse: frm.doc.for_warehouse
                                }]
                            },
                            callback: function (r) {
                                console.log("Received response from server", r);
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
                    console.log("Could not find get_items_for_mr button");
                }
            }, 1000); // 1-second delay to ensure DOM is ready
        }
    }
});