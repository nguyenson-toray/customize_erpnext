// material_distribution.js
frappe.ui.form.on('Material Distribution', {
    onload: function (frm) {
        frm.set_df_property('color', 'options', frm.doc.color);

        // Set warehouse to s_warehouse for all materials
        frm.doc.materials?.forEach(function (material) {
            if (frm.doc.from_warehouse && !material.s_warehouse) {
                frappe.model.set_value(material.doctype, material.name, 's_warehouse', frm.doc.from_warehouse);
            }
        });
    },

    refresh: function (frm) {
        // Add custom buttons
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Get Materials'), function () {
                if (!frm.doc.work_orders) {
                    frappe.msgprint(__('Please select Work Orders first by choosing a Color'));
                    return;
                }
                get_materials_from_work_orders(frm);
            });
        }

        // Set source warehouse in child table
        frm.fields_dict['materials'].grid.update_docfield_property(
            's_warehouse', 'read_only', 0
        );

        // Set field properties for materials grid
        frm.fields_dict['materials'].grid.toggle_enable('transfer_qty', false);
        frm.fields_dict['materials'].grid.toggle_enable('qty_as_per_stock_uom', false);

        // Set up warehouse query
        frm.set_query("from_warehouse", function () {
            return {
                filters: [
                    ["Warehouse", "is_group", "=", 0],
                    ["Warehouse", "disabled", "=", 0]
                ]
            };
        });

        // Set up item query in the materials table
        frm.set_query("item_code", "materials", function () {
            return {
                query: "erpnext.controllers.queries.item_query",
                filters: [["Item", "is_stock_item", "=", 1]]
            };
        });
    },

    // When from_warehouse changes, update all items
    from_warehouse: function (frm) {
        if (frm.doc.from_warehouse && frm.doc.materials && frm.doc.materials.length) {
            $.each(frm.doc.materials || [], function (i, d) {
                frappe.model.set_value(d.doctype, d.name, "s_warehouse", frm.doc.from_warehouse);
            });
        }
    },

    color: function (frm) {
        if (frm.doc.color && frm.doc.item_template) {
            // Show dialog with Work Orders
            show_work_orders_dialog(frm);
        }
    },

    item_template: function (frm) {
        if (frm.doc.item_template) {
            // Clear the color field first
            frm.set_value('color', '');
            frm.set_df_property('color', 'options', ''); // Clear options first 
            // Fetch available colors using the server-side method
            frappe.call({
                method: 'custom_features.custom_features.material_distribution.get_colors_for_template',
                args: {
                    item_template: frm.doc.item_template
                },
                freeze: true,
                callback: function (response) {
                    if (response.message && Array.isArray(response.message) && response.message.length > 0) {
                        // Set the options for the Color field
                        frm.set_df_property('color', 'options', response.message.join('\n'));
                        frm.refresh_field('color');
                    } else {
                        frappe.msgprint(__('No color variants found for this template'));
                    }
                }
            });
        }
    }
});

// Handler for child table
frappe.ui.form.on('Material Distribution Detail', {
    item_code: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.item_code) {
            // Get item details
            frappe.call({
                method: "erpnext.stock.utils.get_item_details",
                args: {
                    args: {
                        item_code: row.item_code,
                        warehouse: frm.doc.from_warehouse,
                        doctype: frm.doc.doctype,
                        conversion_rate: 1.0,
                        company: frappe.defaults.get_user_default('company')
                    }
                },
                callback: function (r) {
                    if (r.message) {
                        $.each(r.message, function (k, v) {
                            if (v && k !== 'taxes') {
                                frappe.model.set_value(cdt, cdn, k, v);
                            }
                        });

                        // Set source warehouse from parent
                        if (frm.doc.from_warehouse) {
                            frappe.model.set_value(cdt, cdn, 's_warehouse', frm.doc.from_warehouse);
                        }

                        // Get available qty at source warehouse
                        get_warehouse_details(frm, cdt, cdn);
                    }
                }
            });
        }
    },

    s_warehouse: function (frm, cdt, cdn) {
        // Get available qty when warehouse changes
        get_warehouse_details(frm, cdt, cdn);
    },

    qty: function (frm, cdt, cdn) {
        // Calculate transfer_qty and qty_as_per_stock_uom
        var row = locals[cdt][cdn];
        var transfer_qty = flt(row.qty) * flt(row.conversion_factor);
        frappe.model.set_value(cdt, cdn, 'transfer_qty', transfer_qty);
        frappe.model.set_value(cdt, cdn, 'qty_as_per_stock_uom', transfer_qty);
    },

    uom: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.uom && row.item_code) {
            // Get conversion factor
            return frappe.call({
                method: "erpnext.stock.doctype.stock_entry.stock_entry.get_uom_details",
                args: {
                    item_code: row.item_code,
                    uom: row.uom,
                    qty: row.qty
                },
                callback: function (r) {
                    if (r.message) {
                        frappe.model.set_value(cdt, cdn, r.message);
                    }
                }
            });
        }
    },

    conversion_factor: function (frm, cdt, cdn) {
        // Recalculate transfer_qty when conversion factor changes
        var row = locals[cdt][cdn];
        var transfer_qty = flt(row.qty) * flt(row.conversion_factor);
        frappe.model.set_value(cdt, cdn, 'transfer_qty', transfer_qty);
        frappe.model.set_value(cdt, cdn, 'qty_as_per_stock_uom', transfer_qty);
    },

    serial_no: function (frm, cdt, cdn) {
        // Handle serial numbers like in stock entry
        var d = locals[cdt][cdn];
        if (d.serial_no) {
            // Replace all commas with newlines
            d.serial_no = d.serial_no.replace(/,/g, '\n');

            // Count valid serial numbers
            const valid_serial_nos = d.serial_no.split('\n')
                .filter(s => s.trim());

            // Update qty based on number of serial numbers
            frappe.model.set_value(cdt, cdn, 'qty',
                valid_serial_nos.length / flt(d.conversion_factor || 1));
        }
    },

    // Add button to select batch/serial numbers
    batch_no: function (frm, cdt, cdn) {
        // Handle batch selection logic if needed
    }
});

// Helper functions

// Get warehouse details for a row
function get_warehouse_details(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    if (row.item_code && row.s_warehouse) {
        frappe.call({
            method: "erpnext.stock.doctype.stock_entry.stock_entry.get_warehouse_details",
            args: {
                args: {
                    item_code: row.item_code,
                    warehouse: row.s_warehouse,
                    transfer_qty: row.transfer_qty,
                    qty: row.qty,
                    company: frappe.defaults.get_user_default('company'),
                    voucher_type: frm.doc.doctype,
                    voucher_no: row.name,
                    allow_zero_valuation: 1
                }
            },
            callback: function (r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, 'actual_qty', r.message.actual_qty || 0);
                }
            }
        });
    }
}

// Function to show Work Orders dialog (keep the original implementation)
function show_work_orders_dialog(frm) {
    // Your existing implementation...
}

// Function to get materials from selected Work Orders
function get_materials_from_work_orders(frm) {
    if (!frm.doc.work_orders) {
        frappe.msgprint(__('No Work Orders selected. Please select Color first to choose Work Orders.'));
        return;
    }

    // Parse Work Orders from text field
    var work_order_list = frm.doc.work_orders.split('\n').filter(function (wo) {
        return wo.trim() !== '';
    });

    if (work_order_list.length === 0) {
        frappe.msgprint(__('No valid Work Orders found in the list'));
        return;
    }

    frappe.call({
        method: 'custom_features.custom_features.material_distribution.get_materials_from_work_orders',
        args: {
            work_orders: work_order_list
        },
        freeze: true,
        callback: function (response) {
            if (response.message && response.message.length > 0) {
                // Clear existing materials
                frm.clear_table('materials');

                // Add materials to child table with work order information
                response.message.forEach(function (item) {
                    var row = frm.add_child('materials');
                    row.item_code = item.item_code;
                    row.item_name = item.item_name;
                    row.description = item.description;
                    row.qty = item.qty;
                    row.uom = item.stock_uom;
                    row.stock_uom = item.stock_uom;
                    row.conversion_factor = 1.0;
                    row.transfer_qty = item.qty;
                    row.qty_as_per_stock_uom = item.qty;
                    row.s_warehouse = frm.doc.from_warehouse || item.source_warehouse;

                    // Set work order
                    if (item.work_order) {
                        row.work_order = item.work_order;

                        // Get target warehouse from work order
                        frappe.db.get_value('Work Order', item.work_order, 'wip_warehouse', function (r) {
                            if (r && r.wip_warehouse) {
                                frappe.model.set_value(row.doctype, row.name, 't_warehouse', r.wip_warehouse);
                            }
                        });
                    }

                    // Get actual quantity at source warehouse
                    get_warehouse_details(frm, row.doctype, row.name);
                });

                frm.refresh_field('materials');
                frappe.msgprint(__('Materials fetched from selected Work Orders'));
            } else {
                frappe.msgprint(__('No materials found for the selected Work Orders'));
            }
        }
    });
}