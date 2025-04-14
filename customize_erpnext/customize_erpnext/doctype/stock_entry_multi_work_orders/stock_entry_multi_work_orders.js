// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Entry Multi Work Orders", {
    refresh(frm) {
        // Add a custom handler for the delete button
        frm.add_custom_button(__('Refresh Materials'), function () {
            refresh_materials(frm);
        });

        // Add a direct handler for the delete button
        frm.fields_dict['work_orders'].grid.grid_buttons.find('.grid-delete-row').click(function () {
            setTimeout(function () {
                refresh_materials(frm);
            }, 300);
        });

    },
    // Get Color After choosing Item Template
    item_template(frm) {
        if (frm.doc.item_template) {
            // Clear the color field first
            frm.set_value('color', '');
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
                            });
                            frm.refresh_field('work_orders');

                            if (response.message.work_orders.length === 0) {
                                frappe.msgprint(__('No work orders found for the selected item and color.'));
                            }
                        }

                        // Add materials to the table
                        const listMaterialsData = response.message.materials || [];
                        console.log("Work orders to send:", listMaterialsData); // Debug log
                        const combinedData = combineItemsByCode(listMaterialsData);
                        console.log(combinedData); // Debug log
                        if (combinedData && Array.isArray(combinedData)) {
                            combinedData.forEach(function (material) {

                                let row = frm.add_child('materials');
                                row.item_code = material.item_code;
                                row.item_name = material.item_name;
                                row.item_name_detail = material.item_name_detail;
                                row.required_qty = material.required_qty;
                                row.qty_available = material.qty_available;
                                row.wip_warehouse = material.wip_warehouse;
                            });
                            frm.refresh_field('materials');
                        }
                    }
                }
            });
        }
    },

});

// Add a separate event handler for the child table
frappe.ui.form.on("Stock Entry Multi Work Orders Table WO", {
    work_orders: function (frm, cdt, cdn) {
        refresh_materials(frm);
    },

    work_orders_add: function (frm, cdt, cdn) {
        refresh_materials(frm);
    },
    work_orders_remove: function (frm, cdt, cdn) {
        refresh_materials(frm);
    }
});

// Improved refresh_materials function that properly handles work order deletions
function refresh_materials(frm) {
    // Get all work orders from the table
    let work_orders = frm.doc.work_orders
        ? frm.doc.work_orders
            .filter(row => row.work_order && row.work_order.trim() !== '')
            .map(row => row.work_order)
        : [];


    if (work_orders.length > 0) {
        // Clear existing materials table only if there are work orders to replace them
        frm.clear_table('materials');

        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.stock_entry_multi_work_orders.stock_entry_multi_work_orders.get_materials_for_work_orders',
            args: {
                'work_orders': work_orders
            },
            freeze: true,
            callback: function (response) {


                if (response.message && Array.isArray(response.message)) {
                    // Add materials to the table
                    response.message.forEach(function (material) {

                        let row = frm.add_child('materials');
                        row.item_code = material.item_code;
                        row.item_name = material.item_name;
                        row.item_name_detail = material.item_name_detail;
                        row.required_qty = material.required_qty;
                        row.qty_available = material.qty_available;
                        row.wip_warehouse = material.wip_warehouse;
                    });
                    frm.refresh_field('materials');
                }
            }
        });
    } else {
        // Only clear if there are no work orders left
        frm.clear_table('materials');
        frm.refresh_field('materials');
    }
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
            groupedItems[itemCode].required_qty += item.required_qty;
        }
    });

    // Convert the object back to array
    return Object.values(groupedItems);
}