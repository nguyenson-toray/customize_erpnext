// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Entry Multi Work Orders", {
    refresh(frm) {
        frm.set_intro(null);
        frm.set_intro(__("Sau khi Submit, hệ thống sẽ tạo các Stock Entry (Draft) kiểu Material Transfer for Manufacture cho các Work Order tương ứng"), 'orange');

        // Add Get Materials button
        frm.add_custom_button(__('Get Materials'), function () {
            refresh_materials(frm);
        }).addClass('btn-primary');

        // Handle item_template color list population
        if (frm.doc.item_template) {
            // Only run this if item_template is set and color list needs to be populated
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_colors_for_template',
                args: {
                    item_template: frm.doc.item_template
                },
                callback: function (response) {
                    if (response.message && Array.isArray(response.message) && response.message.length > 0) {
                        // Set the options for the Color field
                        frm.set_df_property('color', 'options', response.message.join('\n'));
                        // This will keep the selected color if it exists in the options
                        frm.refresh_field('color');
                    }
                }
            });
        }

        // Add view Stock Entries button if doc is submitted
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('View Stock Entries'), function () {
                frappe.route_options = {
                    "stock_entry_multi_work_orders": frm.doc.name
                };
                frappe.set_route("List", "Stock Entry");
            });
        }

        // Custom handling for materials table - bulk selection
        frm.fields_dict['materials'].grid.wrapper.on('click', '.grid-row-check', function () {
            let grid = frm.fields_dict['materials'].grid;
            let selected = grid.get_selected();

            // Get selected rows data
            let selected_items = [];
            selected.forEach(idx => {
                // Get row and assign correct idx to object
                let item = frm.doc.materials[idx];
                if (item) {
                    // Assign the correct index to each item
                    item.grid_idx = idx;
                    selected_items.push(item);
                }
            });

            // Show qty adjustment dialog if items are selected
            if (selected_items.length > 0) {
                show_qty_adjustment_dialog(frm, selected_items);
            }
        });
    },

    // Get Color After choosing Item Template
    item_template(frm) {
        if (frm.doc.item_template) {
            // Clear the color field first
            frm.set_value('color', '');
            frm.clear_table('work_orders');
            frm.clear_table('materials');
            frm.refresh_fields(['work_orders', 'materials']);

            frm.set_df_property('color', 'options', ''); // Clear options first 
            // Fetch available colors using the server-side method
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_colors_for_template',
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
    },

    // Get Work Order After choosing Color:
    color: function (frm) {
        if (frm.doc.item_template && frm.doc.color) {
            // Clear existing rows
            frm.clear_table('work_orders');
            frm.clear_table('materials');

            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_related_work_orders',
                args: {
                    'item_template': frm.doc.item_template,
                    'color': frm.doc.color
                },
                freeze: true,
                callback: function (response) {
                    if (response.message) {
                        // Add work orders to the table
                        if (response.message.work_orders && Array.isArray(response.message.work_orders)) {
                            response.message.work_orders.forEach(function (wo) {
                                let row = frm.add_child('work_orders');
                                row.work_order = wo.work_order;
                                row.item_code = wo.item_code;
                                row.item_name = wo.item_name;
                                row.item_name_detail = wo.item_name_detail;
                                row.qty_to_manufacture = wo.qty_to_manufacture;
                                row.work_order_status = wo.work_order_status;
                                // Update notification and maintain consistent status
                                if (wo.work_order_status != 'Not Started') {
                                    frappe.show_alert({
                                        message: __(`Work Order ${wo.work_order} đã bắt đầu !!!`),
                                        indicator: 'orange'
                                    });
                                }
                            });
                            frm.refresh_field('work_orders');

                            if (response.message.work_orders.length === 0) {
                                frappe.msgprint(__('No work orders found for the selected item and color.'));
                            }
                        }

                        // We don't automatically load materials anymore - user will click "Get Materials" button
                        frm.refresh_field('materials');
                    }
                }
            });
        }
    },
});

// Event handler cho child table "Stock Entry Multi Work Orders Table WO"
frappe.ui.form.on("Stock Entry Multi Work Orders Table WO", {
    work_orders_add: function (frm, cdt, cdn) {
        refresh_materials(frm);
    },

    work_orders_remove: function (frm, cdt, cdn) {
        refresh_materials(frm);
    }
});

// Event handler for child table "Stock Entry Multi Work Orders Table Material"
frappe.ui.form.on("Stock Entry Multi Work Orders Table Material", {
    // Removed validation for required_qty - now user can modify quantities freely
});

// Function to refresh materials list from work orders
function refresh_materials(frm) {
    console.log("refresh_materials");
    // Get all work orders from the table
    let work_orders = frm.doc.work_orders
        ? frm.doc.work_orders
            .filter(row => row.work_order && row.work_order.trim() !== '')
            .map(row => row.work_order)
        : [];

    // Always clear the materials table
    frm.clear_table('materials');
    frm.refresh_field('materials');

    if (work_orders.length > 0) {
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_materials_for_work_orders',
            args: {
                'work_orders': work_orders
            },
            freeze: true,
            callback: function (response) {
                if (response.message && Array.isArray(response.message)) {
                    // Combine items with the same item_code
                    const combinedData = combineItemsByCode(response.message);

                    // Add materials to the table
                    combinedData.forEach(function (material) {
                        let row = frm.add_child('materials');
                        row.item_code = material.item_code;
                        row.item_name = material.item_name;
                        row.item_name_detail = material.item_name_detail;
                        row.required_qty = material.required_qty;
                        row.qty_available_in_source_warehouse = material.qty_available;
                        row.wip_warehouse = material.wip_warehouse;
                        row.source_warehouse = material.source_warehouse;
                    });

                    frm.refresh_field('materials');
                    frappe.show_alert({
                        message: __('Materials retrieved successfully'),
                        indicator: 'green'
                    });
                } else {
                    frappe.msgprint(__('No materials found for the selected work orders.'));
                }
            }
        });
    } else {
        frappe.msgprint(__('No work orders selected. Please select at least one work order.'));
    }
}

// Function to create multiple Stock Entries - improved error handling and processing
function create_stock_entries(frm) {
    if (!frm.doc.work_orders || frm.doc.work_orders.length === 0) {
        frappe.msgprint(__('No work orders selected'));
        return;
    }

    frappe.confirm(
        __('This will create {0} separate Stock Entries, one for each Work Order. Continue?', [frm.doc.work_orders.length]),
        function () {
            // Display processing message
            frappe.show_progress(__('Creating Stock Entries'), 0, frm.doc.work_orders.length);

            // Get list of work orders
            const work_orders = frm.doc.work_orders.map(row => row.work_order);

            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.create_individual_stock_entries',
                args: {
                    'doc_name': frm.doc.name,
                    'work_orders': work_orders
                },
                freeze: true,
                freeze_message: __('Creating Stock Entries...'),
                callback: function (response) {
                    if (response.message && response.message.length) {
                        let message = __('Created the following Stock Entries:') + '<br><br>';
                        response.message.forEach(entry => {
                            message += `<a href="/app/stock-entry/${entry}" target="_blank">${entry}</a><br>`;
                        });

                        frappe.msgprint({
                            title: __('Stock Entries Created'),
                            indicator: 'green',
                            message: message
                        });

                        // Refresh work order status
                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __('Warning'),
                            indicator: 'orange',
                            message: __('No Stock Entries were created. Check the server error log for details.')
                        });
                    }
                },
                error: function (err) {
                    frappe.msgprint({
                        title: __('Error'),
                        indicator: 'red',
                        message: __('Failed to create Stock Entries: ') + (err.message || 'Unknown error')
                    });
                }
            });
        }
    );
}

/**
 * Simplified quantity adjustment dialog - removed validation for qty reductions
 * @param {Object} frm - Form object
 * @param {Array} selected_items - Selected material items
 */
function show_qty_adjustment_dialog(frm, selected_items) {
    console.log("show_qty_adjustment_dialog");
    if (selected_items.length === 0) return;

    let fields = [];

    selected_items.forEach(item => {
        // Use grid_idx instead of idx
        fields.push({
            fieldtype: 'Float',
            fieldname: `qty_${item.grid_idx}`,
            label: `${item.item_code} - ${item.item_name || ''} (Current: ${item.required_qty})`,
            default: item.required_qty
        });
    });

    let d = new frappe.ui.Dialog({
        title: __('Adjust Quantities'),
        fields: fields,
        primary_action_label: __('Update'),
        primary_action: function () {
            let values = d.get_values();

            // Update quantities in the materials table
            selected_items.forEach(item => {
                // Use grid_idx instead of idx
                let new_qty = values[`qty_${item.grid_idx}`];

                // Update the quantity in the grid
                frappe.model.set_value(item.doctype, item.name, 'required_qty', new_qty);
            });

            frm.refresh_field('materials');
            d.hide();
        }
    });

    d.show();
}

/**
 * Combines items with the same item_code and sums their required_qty values
 * @param {Array} items - Array of item objects
 * @returns {Array} - Array of combined items
 */
const combineItemsByCode = (items) => {
    const groupedItems = {};

    items.forEach(item => {
        const itemCode = item.item_code;

        if (!groupedItems[itemCode]) {
            // First occurrence of this item_code, create new entry
            groupedItems[itemCode] = { ...item };
        } else {
            // Item already exists, sum the required_qty
            groupedItems[itemCode].required_qty = flt(groupedItems[itemCode].required_qty) + flt(item.required_qty);
        }
    });

    // Convert the object back to array
    return Object.values(groupedItems);
}

/**
 * Helper function to safely convert string to float
 * @param {*} val - Value to convert
 * @returns {number} - Float value
 */
function flt(val) {
    return parseFloat(val || 0);
}